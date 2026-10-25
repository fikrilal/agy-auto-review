#!/usr/bin/env python3
"""
Lifecycle Stop hook for Antigravity CLI Auto-Review.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

# Ensure this script's directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auto_review_core import (
    clip_text,
    capture_workspace,
    load_state,
    run_reviewer_turn,
    save_review_report,
    save_state,
    send_desktop_notification,
    MAX_FINDINGS_CHARS,
)


def allow_stop() -> None:
    print(json.dumps({"decision": "allow"}))
    sys.exit(0)


def continue_turn(reason: str) -> None:
    print(json.dumps({"decision": "continue", "reason": reason}))
    sys.exit(0)


def feedback_prompt(text: str, review_number: int, max_reviews: Any, model: str) -> str:
    cycle_info = f"round {review_number}/{max_reviews}" if (isinstance(max_reviews, int) and max_reviews > 0) else f"round {review_number}"
    findings = clip_text(text, MAX_FINDINGS_CHARS)
    return (
        f"Antigravity review ({model}) {cycle_info}: CHANGES_REQUIRED\n\n"
        f"{findings}\n\n"
        f"Address every blocking finding. Once done, the review loop will automatically verify your fixes."
    )


def main() -> None:
    # 1. Guard against recursive reviewer execution
    if os.environ.get("AGY_REVIEWER") == "1" or os.environ.get("PI_REVIEWER") == "1" or os.environ.get("CMD_REVIEWER") == "1":
        allow_stop()

    # 2. Read stdin
    try:
        raw_input = sys.stdin.read()
        payload = json.loads(raw_input) if raw_input.strip() else {}
    except Exception:
        payload = {}

    termination_reason = payload.get("terminationReason", "")
    # Only review when the agent naturally terminates its tool loop
    if termination_reason != "NO_TOOL_CALL":
        allow_stop()

    # 3. Check review state
    state = load_state()
    mode = state.get("mode", "off")
    if not state.get("enabled", False) or mode == "off":
        allow_stop()

    # If the previous model turn just announced the approval, stop immediately!
    if state.get("announcedApproval"):
        state["announcedApproval"] = False
        save_state(state)
        allow_stop()

    # 4. Resolve workspace directory
    workspace_paths = payload.get("workspacePaths", [])
    cwd = workspace_paths[0] if (workspace_paths and os.path.isdir(workspace_paths[0])) else os.getcwd()

    # Determine git repo root
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            allow_stop()
        repo_root = res.stdout.strip()
    except Exception:
        allow_stop()

    # 5. Capture workspace snapshot and dirty check
    try:
        snapshot = capture_workspace(repo_root)
    except Exception:
        allow_stop()

    if not snapshot["dirty"]:
        allow_stop()

    current_fp = snapshot["fingerprint"]

    # Check if this exact working tree was already approved
    if state.get("approvedFingerprint") == current_fp:
        allow_stop()

    # Check if last verdict was APPROVED and the code has not changed since
    if state.get("lastVerdict") == "APPROVED" and state.get("lastReviewedFingerprint") == current_fp:
        allow_stop()

    last_fp = state.get("lastReviewedFingerprint")
    if current_fp == last_fp:
        # Code did not change since last review feedback; avoid infinite loop
        allow_stop()

    review_count = state.get("reviewCount", 0)
    max_reviews = state.get("maxReviews")
    if isinstance(max_reviews, int) and review_count >= max_reviews:
        state["mode"] = "off"
        state["enabled"] = False
        save_state(state)
        allow_stop()

    model = state.get("model", "gemini-3.8-flash")
    effort = state.get("effort", "high")
    existing_convo_id = state.get("conversationId")
    artifact_dir = payload.get("artifactDirectoryPath")

    # 6. Run reviewer turn
    result = run_reviewer_turn(
        repo_root=repo_root,
        round_number=review_count + 1,
        existing_convo_id=existing_convo_id,
        model=model,
        effort=effort,
        fp_script=snapshot.get("fingerprint_script"),
    )

    # Retry on a fresh conversation once if resume produced no verdict
    if not result["ok"] and existing_convo_id:
        result = run_reviewer_turn(
            repo_root=repo_root,
            round_number=review_count + 1,
            existing_convo_id=None,
            model=model,
            effort=effort,
            fp_script=snapshot.get("fingerprint_script"),
        )

    # 7. Evaluate verdict
    if result["ok"]:
        review_count += 1
        state["reviewCount"] = review_count
        state["lastReviewedFingerprint"] = current_fp
        if result.get("conversationId"):
            state["conversationId"] = result["conversationId"]

        verdict = result.get("verdict")
        state["lastVerdict"] = verdict

        # Always save the full reviewer findings/report to disk
        report_path = save_review_report(
            repo_root=repo_root,
            artifact_dir=artifact_dir,
            round_number=review_count,
            verdict=verdict or "UNKNOWN",
            text=result["text"],
            model=model,
            effort=effort,
            tree_hash=current_fp,
        )

        if verdict == "APPROVED":
            state["approvedFingerprint"] = current_fp
            state["announcedApproval"] = True  # Instructs next Stop hook to immediately terminate
            if mode == "once":
                state["mode"] = "off"
                state["enabled"] = False
            save_state(state)

            # Send desktop notification
            send_desktop_notification(
                "✓ Antigravity Reviewer: APPROVED",
                f"Round {review_count}: All checks passed with 0 blocking findings.",
            )

            # Re-enter the turn once so the agent explicitly outputs the approval announcement in chat
            approval_msg = (
                f"Antigravity Reviewer ({model}) Round {review_count}: VERDICT: APPROVED ✓\n\n"
                f"All checks, contracts, and criteria passed with 0 blocking findings.\n"
                f"Full review report logged to: {report_path}\n\n"
                f"Conclude your turn by explicitly presenting the final approval verdict (VERDICT: APPROVED ✓) and summarizing the reviewer's confirmation for the user."
            )
            continue_turn(approval_msg)

        elif verdict == "CHANGES_REQUIRED":
            if mode == "once":
                state["mode"] = "off"
                state["enabled"] = False
            save_state(state)

            # Send desktop notification
            send_desktop_notification(
                "✗ Antigravity Reviewer: CHANGES REQUIRED",
                f"Round {review_count}: Findings require fixes. Feeding back to agent...",
                urgency="critical",
            )

            reason = feedback_prompt(result["text"], review_count, max_reviews, model)
            continue_turn(reason)

    # If reviewer encountered an error or gave no verdict, release the gate safely
    allow_stop()


if __name__ == "__main__":
    main()
