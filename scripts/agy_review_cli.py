#!/usr/bin/env python3
"""
CLI controller for Antigravity Auto-Review, matching CommandCode's agy-review mod.
"""

from __future__ import annotations

import os
import subprocess
import sys

# Ensure this script's directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from auto_review_core import (
    capture_workspace,
    check_for_update,
    find_review_skills,
    get_active_account_info,
    get_installed_version,
    load_state,
    perform_update,
    rotate_cli_account,
    run_reviewer_turn,
    save_state,
    DEFAULT_MODEL,
    DEFAULT_EFFORT,
    DEFAULT_MAX_REVIEWS,
)


def print_status(cwd: str) -> None:
    state = load_state()
    mode = state.get("mode", "off").upper()
    enabled = state.get("enabled", False)
    count = state.get("reviewCount", 0)
    max_rev = state.get("maxReviews")
    model = state.get("model", DEFAULT_MODEL)
    effort = state.get("effort", DEFAULT_EFFORT)
    convo_id = state.get("conversationId")

    cycles = (
        f"{count}/{max_rev}"
        if (isinstance(max_rev, int) and max_rev > 0)
        else (f"{count} (continuous review until APPROVED)" if mode == "LOOP" else f"{count}")
    )

    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode == 0:
            repo_root = res.stdout.strip()
            snapshot = capture_workspace(repo_root)
            tree_status = "DIRTY (uncommitted changes detected)" if snapshot["dirty"] else "CLEAN"
            skills = find_review_skills(repo_root)
            skills_str = ", ".join(skills) if skills else "None (default review instructions)"
        else:
            repo_root = "Not a git repository"
            tree_status = "N/A"
            skills_str = "N/A"
    except Exception as e:
        repo_root = f"Error: {e}"
        tree_status = "UNKNOWN"
        skills_str = "UNKNOWN"

    last_verdict = state.get("lastVerdict") or "None"
    report_file = None
    if res.returncode == 0:
        candidate_report = os.path.join(repo_root, ".agents", "review-latest.md")
        if os.path.exists(candidate_report):
            report_file = candidate_report

    active_acct = get_active_account_info()
    version = get_installed_version()
    up_avail, _, remote_ver = check_for_update(force=False)
    if up_avail and remote_ver:
        ver_display = f"{version[:7] if len(version) >= 7 else version} (UPDATE AVAILABLE: {remote_ver[:7]} — run 'agy-review update')"
    else:
        ver_display = version[:7] if len(version) >= 7 else version

    print("• Antigravity Auto-Review Status:")
    print(f"  - Version:         {ver_display}")
    print(f"  - Mode:            {mode} ({'ENABLED' if enabled else 'DISABLED'})")
    print(f"  - Cycles:          {cycles}")
    if active_acct:
        print(f"  - Active Account:  {active_acct}")
    print(f"  - Last Verdict:    {last_verdict}")
    print(f"  - Reviewer Model:  {model} (effort: {effort})")
    print(f"  - Active ReviewId: {convo_id or 'None (fresh start)'}")
    print(f"  - Repository:      {repo_root}")
    print(f"  - Working Tree:    {tree_status}")
    print(f"  - Detected Skills: {skills_str}")
    if report_file:
        print(f"  - Latest Report:   {report_file}")


def run_now(cwd: str) -> None:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            print("Error: Current directory is not inside a git repository.")
            sys.exit(1)
        repo_root = res.stdout.strip()
    except Exception as e:
        print(f"Error checking git repository: {e}")
        sys.exit(1)

    state = load_state()
    snapshot = capture_workspace(repo_root)
    if not snapshot["dirty"]:
        print("Working tree is clean — nothing to review.")
        sys.exit(0)

    skills = find_review_skills(repo_root)
    print(f"Starting Antigravity review on {repo_root}...")
    if skills:
        print(f"Detected review skills: {', '.join(skills)}")

    model = state.get("model", DEFAULT_MODEL)
    effort = state.get("effort", DEFAULT_EFFORT)
    existing_convo_id = state.get("conversationId")

    result = run_reviewer_turn(
        repo_root=repo_root,
        round_number=state.get("reviewCount", 0) + 1,
        existing_convo_id=existing_convo_id,
        model=model,
        effort=effort,
        fp_script=snapshot.get("fingerprint_script"),
    )

    if not result["ok"] and existing_convo_id:
        # Retry once on fresh conversation
        result = run_reviewer_turn(
            repo_root=repo_root,
            round_number=state.get("reviewCount", 0) + 1,
            existing_convo_id=None,
            model=model,
            effort=effort,
            fp_script=snapshot.get("fingerprint_script"),
        )

    if not result["ok"]:
        print(f"Review failed: {result['error']}")
        sys.exit(1)

    verdict = result.get("verdict")
    print(f"\n==================== REVIEW RESULT ====================")
    print(f"VERDICT: {verdict}")
    print(f"=======================================================\n")
    print(result["text"])

    if result.get("conversationId"):
        state["conversationId"] = result["conversationId"]
    state["reviewCount"] = state.get("reviewCount", 0) + 1
    state["lastReviewedFingerprint"] = snapshot["fingerprint"]
    save_state(state)


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0].lower() if args else "status"
    cwd = os.getcwd()

    state = load_state()

    if cmd in ("on", "enable", "start", "loop"):
        max_rev = DEFAULT_MAX_REVIEWS
        if len(args) > 1:
            try:
                val = int(args[1])
                if val > 0:
                    max_rev = val
            except ValueError:
                pass
        state["enabled"] = True
        state["mode"] = "loop"
        state["maxReviews"] = max_rev
        save_state(state)
        limit_desc = f"up to {max_rev} cycles"
        print(f"✓ Antigravity Auto-Review armed: {limit_desc}.")

    elif cmd == "once":
        state["enabled"] = True
        state["mode"] = "once"
        state["maxReviews"] = 1
        save_state(state)
        print("✓ Antigravity Auto-Review armed for 1 review cycle on next stop.")

    elif cmd in ("off", "disable", "stop"):
        state["enabled"] = False
        state["mode"] = "off"
        save_state(state)
        print("Automatic Antigravity review is OFF.")

    elif cmd == "reset":
        state["conversationId"] = None
        state["lastReviewedFingerprint"] = None
        state["approvedFingerprint"] = None
        state["lastVerdict"] = None
        state["reviewCount"] = 0
        state["model"] = DEFAULT_MODEL
        state["effort"] = DEFAULT_EFFORT
        save_state(state)
        print("✓ Antigravity reviewer session reset. Next review will start fresh.")

    elif cmd == "rotate":
        rotated, msg = rotate_cli_account()
        if rotated:
            print(f"✓ {msg}")
            state["conversationId"] = None
            save_state(state)
        else:
            print(f"⚠ Could not rotate account: {msg}")

    elif cmd == "update":
        force = ("--force" in args) or ("-f" in args)
        check_only = ("--check" in args) or ("-c" in args)
        print("Checking for updates from GitHub...")
        up_avail, local_v, remote_v = check_for_update(force=True)
        local_disp = local_v[:7] if len(local_v) >= 7 else local_v
        remote_disp = remote_v[:7] if (remote_v and len(remote_v) >= 7) else (remote_v or "unknown")

        if check_only:
            if up_avail and remote_v:
                print(f"💡 Update available: {local_disp} -> {remote_disp}. Run 'agy-review update' to install.")
            else:
                print(f"agy-auto-review is up to date ({local_disp}).")
            return

        if not up_avail and not force:
            print(f"agy-auto-review is already up to date ({local_disp}). Pass --force to reinstall.")
            return

        print(f"Updating agy-auto-review to {remote_disp}...")
        ok, msg = perform_update()
        if ok:
            print(f"✓ {msg}")
        else:
            print(f"✗ Update failed: {msg}")
            sys.exit(1)

    elif cmd == "status":
        print_status(cwd)

    elif cmd == "now":
        run_now(cwd)

    elif cmd in ("help", "--help", "-h"):
        print("Usage: agy-review [command] [args]")
        print("")
        print("Commands:")
        print("  on [max-cycles]   Enable auto-review loop (continuous until APPROVED by default)")
        print("  once              Run auto-review once after the next coding turn")
        print("  off               Disable auto-review")
        print("  status            Show current review mode, cycle count, and repo status")
        print("  now               Run Antigravity reviewer immediately on current workspace")
        print("  reset             Reset review conversation history and cycle count")
        print("  rotate            Rotate to next available Antigravity account with quota")
        print("  update [--force]  Update agy-auto-review to latest version from GitHub")
        print("  help              Show this help message")

    else:
        print(f"Unknown command: '{cmd}'. Run 'agy-review help' for usage.")
        sys.exit(1)


if __name__ == "__main__":
    main()
