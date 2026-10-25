#!/usr/bin/env python3
"""
Core engine for Antigravity CLI Auto-Review, matching CommandCode's agy-review mod.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple

STATE_FILE = os.path.expanduser("~/.gemini/config/auto-review.json")
DEFAULT_MODEL = "gemini-3.8-flash"
DEFAULT_EFFORT = "high"
DEFAULT_MAX_REVIEWS = 10
REVIEWER_TIMEOUT_SEC = 20 * 60  # 20 minutes
MAX_FINDINGS_CHARS = 12000

AGY_BIN = (
    os.path.expanduser("~/.local/bin/agy")
    if os.path.exists(os.path.expanduser("~/.local/bin/agy"))
    else (shutil.which("agy") or "agy")
)

FINGERPRINT_SCRIPTS = [
    ".commandcode/mods/review-fingerprint.sh",
    ".agents/mods/review-fingerprint.sh",
    ".agents/scripts/review-fingerprint.sh",
]


def load_state() -> Dict[str, Any]:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {
        "enabled": True,
        "mode": "loop",  # "off", "once", "loop"
        "maxReviews": DEFAULT_MAX_REVIEWS,  # Default 10 max cycles
        "model": DEFAULT_MODEL,
        "effort": DEFAULT_EFFORT,
        "conversationId": None,
        "lastReviewedFingerprint": None,
        "reviewCount": 0,
    }


def save_state(state: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    temp_file = f"{STATE_FILE}.tmp.{os.getpid()}"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
    os.replace(temp_file, STATE_FILE)


def find_review_skills(repo_root: str) -> List[str]:
    """Finds review skills in the codebase, prioritizing .agents/skills."""
    candidate_dirs = [
        os.path.join(repo_root, ".agents", "skills"),
        os.path.join(repo_root, ".agent", "skills"),
        os.path.join(repo_root, "_agents", "skills"),
        os.path.join(repo_root, "_agent", "skills"),
        os.path.join(repo_root, ".commandcode", "skills"),
        os.path.join(repo_root, ".pi", "skills"),
    ]

    all_found: List[Tuple[str, str]] = []  # (skill_name, relative_path)
    for s_dir in candidate_dirs:
        if not os.path.isdir(s_dir):
            continue
        try:
            for entry in sorted(os.scandir(s_dir), key=lambda e: e.name):
                if entry.is_dir():
                    skill_file = os.path.join(entry.path, "SKILL.md")
                    if os.path.isfile(skill_file):
                        rel = os.path.relpath(skill_file, repo_root)
                        all_found.append((entry.name, rel))
                elif entry.is_file() and entry.name.endswith(".md"):
                    name = os.path.splitext(entry.name)[0]
                    rel = os.path.relpath(entry.path, repo_root)
                    all_found.append((name, rel))
        except Exception:
            pass

    # Deduplicate by skill name, keeping first discovered
    seen_names = set()
    deduped: List[str] = []
    for name, rel in all_found:
        if name not in seen_names:
            seen_names.add(name)
            deduped.append(rel)

    # Filter to review-focused skills if any match, otherwise return all detected skills
    review_skills = [s for s in deduped if "review" in s.lower()]
    return review_skills if review_skills else deduped


def capture_workspace(repo_root: str) -> Dict[str, Any]:
    """Captures git working tree snapshot and fingerprint."""
    # 1. Check custom fingerprint script
    for fp_script in FINGERPRINT_SCRIPTS:
        fp_path = os.path.join(repo_root, fp_script)
        if os.path.isfile(fp_path):
            try:
                proc = subprocess.run(
                    ["bash", fp_script],
                    cwd=repo_root,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode == 3:
                    head_res = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=repo_root,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    head = head_res.stdout.strip() if head_res.returncode == 0 else "HEAD"
                    return {
                        "root": repo_root,
                        "head": head,
                        "fingerprint": "clean",
                        "dirty": False,
                        "fingerprint_script": fp_script,
                    }
                matches = re.findall(r"([0-9a-f]{64})", proc.stdout, re.IGNORECASE)
                if matches:
                    head_res = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=repo_root,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    head = head_res.stdout.strip() if head_res.returncode == 0 else "HEAD"
                    return {
                        "root": repo_root,
                        "head": head,
                        "fingerprint": matches[-1].lower(),
                        "dirty": True,
                        "fingerprint_script": fp_script,
                    }
            except Exception:
                pass

    # 2. Standard git diff & untracked hashing
    head_res = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if head_res.returncode != 0:
        raise RuntimeError("Git repository has no initial commit or HEAD is invalid.")
    head = head_res.stdout.strip()

    diff_res = subprocess.run(
        ["git", "diff", "--binary", "--no-ext-diff", "HEAD", "--"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )

    untracked_res = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", "-z"],
        cwd=repo_root,
        capture_output=True,
        check=False,
    )

    untracked_files = [
        f for f in untracked_res.stdout.split(b"\0")
        if f and not f.endswith(b"review-latest.md") and not f.endswith(b"review.md")
    ]
    untracked_files.sort()

    untracked_hashes: List[bytes] = []
    for ufile in untracked_files:
        hres = subprocess.run(
            ["git", "hash-object", "--", ufile],
            cwd=repo_root,
            capture_output=True,
            check=False,
        )
        uhash = hres.stdout.strip() if hres.returncode == 0 else b"<unreadable>"
        untracked_hashes.append(ufile + b"\0" + uhash)

    hasher = hashlib.sha256()
    hasher.update(head.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(diff_res.stdout)
    hasher.update(b"\0")
    hasher.update(b"\0".join(untracked_hashes))
    fingerprint = hasher.hexdigest()

    is_dirty = len(diff_res.stdout) > 0 or len(untracked_files) > 0

    return {
        "root": repo_root,
        "head": head,
        "fingerprint": fingerprint,
        "dirty": is_dirty,
        "fingerprint_script": None,
    }


def build_prompt(round_number: number, use_resume: bool, repo_root: str, skills: List[str], fp_script: Optional[str]) -> str:
    lines: List[str] = []
    if use_resume:
        lines.extend([
            f"This is review round {round_number} of the same change. The working tree changed since your previous review.",
            "Re-read the current uncommitted working-tree diff versus HEAD (tracked diffs plus untracked files), re-verify each of your previous findings against the new code, and review the new changes.",
            "Do not restate resolved findings except to confirm they are resolved. Report only what still applies plus anything new.",
        ])
    else:
        lines.append("You are the automated reviewer session for the uncommitted changes in this repository.")
        if skills:
            lines.append(f"Read and strictly follow these project review skills: {', '.join(skills)}")
        lines.append(
            "Target: the uncommitted working-tree changes versus HEAD (tracked diffs plus untracked files). The '$ARGUMENTS' placeholder inside any skill file is not a prompt variable for you; the target is the change described in this message."
        )

    lines.extend([
        "You are strictly read-only: do not modify, stage, commit, or revert anything.",
        "Run necessary verification commands if available (e.g. tests, lint, analyze via bash).",
        "Findings of severity Critical/High/Medium/Low block approval.",
        "End your final message with exactly one verdict line on its own line — either `VERDICT: APPROVED` or `VERDICT: CHANGES_REQUIRED` — followed by your severity-ordered findings (file:line, what breaks, why it matters, minimal fix). Use APPROVED only when no blocking finding remains. The orchestrator machine-reads this verdict; do not omit or rephrase it.",
    ])

    if fp_script:
        lines.append(
            f"Final step before you write your verdict: run `bash {fp_script}` from the repository root and make the very last line of your message exactly `REVIEWED-TREE: <its stdout>` (if the script prints nothing — the working tree is clean — write `REVIEWED-TREE: clean`). The orchestrator binds your verdict to that exact revision."
        )

    return "\n".join(lines)


def parse_envelope(raw: str) -> Optional[Dict[str, Any]]:
    trimmed = raw.strip()
    if not trimmed:
        return None
    candidates = [trimmed] + [line.strip() for line in reversed(trimmed.splitlines()) if line.strip()]
    for cand in candidates:
        if cand.startswith("{") and cand.endswith("}"):
            try:
                parsed = json.loads(cand)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
    return None


def parse_verdict(text: str) -> Optional[str]:
    matches = list(re.finditer(r"VERDICT:\s*(APPROVED|CHANGES_REQUIRED)", text, re.IGNORECASE))
    if matches:
        return matches[-1].group(1).upper()
    return None


def clip_text(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[:limit]}\n…[truncated]"


def send_desktop_notification(title: str, message: str, urgency: str = "normal") -> None:
    """Sends a system desktop notification via notify-send on Linux."""
    try:
        subprocess.run(
            ["notify-send", "-u", urgency, "-a", "Antigravity Reviewer", title, message],
            capture_output=True,
            check=False,
            timeout=2,
        )
    except Exception:
        pass


def ensure_git_exclude(repo_root: str, pattern: str = ".agents/review-latest.md") -> None:
    exclude_file = os.path.join(repo_root, ".git", "info", "exclude")
    if os.path.isfile(exclude_file):
        try:
            with open(exclude_file, "r", encoding="utf-8") as f:
                content = f.read()
            if pattern not in content:
                with open(exclude_file, "a", encoding="utf-8") as f:
                    f.write(f"\n{pattern}\n")
        except Exception:
            pass


def save_review_report(
    repo_root: str,
    artifact_dir: Optional[str],
    round_number: int,
    verdict: str,
    text: str,
    model: str,
    effort: str,
    tree_hash: str,
) -> str:
    """Saves the reviewer output to .agents/review-latest.md and artifactDirectoryPath/review.md."""
    # Ensure git ignores this generated file so it does not alter git status or fingerprints
    ensure_git_exclude(repo_root, ".agents/review-latest.md")
    ensure_git_exclude(repo_root, "review-latest.md")
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    report = (
        f"# Antigravity Review Report\n\n"
        f"- **Verdict**: `{verdict}`\n"
        f"- **Round**: {round_number}\n"
        f"- **Timestamp**: {now_str}\n"
        f"- **Reviewer Model**: {model} (effort: {effort})\n"
        f"- **Reviewed Revision**: `{tree_hash}`\n\n"
        f"---\n\n"
        f"{text}\n"
    )

    out_dir = os.path.join(repo_root, ".agents")
    if not os.path.isdir(out_dir):
        out_dir = repo_root
    report_path = os.path.join(out_dir, "review-latest.md")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
    except Exception:
        pass

    if artifact_dir and os.path.isdir(artifact_dir):
        try:
            art_path = os.path.join(artifact_dir, "review.md")
            with open(art_path, "w", encoding="utf-8") as f:
                f.write(report)
        except Exception:
            pass

    return report_path


def rotate_cli_account() -> Tuple[bool, str]:
    """Attempts to auto-rotate to another account with quota using agy-auth."""
    agy_auth_bin = (
        os.path.expanduser("~/.local/bin/agy-auth")
        if os.path.exists(os.path.expanduser("~/.local/bin/agy-auth"))
        else (shutil.which("agy-auth") or "agy-auth")
    )
    if not shutil.which(agy_auth_bin) and not os.path.exists(agy_auth_bin):
        return False, "agy-auth binary not found"

    try:
        proc = subprocess.run(
            [agy_auth_bin, "rotate", "--target=cli", "--force", "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if proc.returncode == 0:
            try:
                res = json.loads(proc.stdout)
                data = res.get("data", res)
                if data.get("rotated"):
                    acct = (
                        data.get("account", {}).get("email")
                        or data.get("account", {}).get("alias")
                        or data.get("account", {}).get("id")
                        or "healthy account"
                    )
                    return True, f"Rotated CLI account to {acct}"
                return False, data.get("reason", "no rotation performed")
            except Exception:
                return True, "Rotated CLI account successfully"
        else:
            err = proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}"
            return False, f"agy-auth rotate failed: {err}"
    except Exception as e:
        return False, str(e)


def get_active_account_info() -> Optional[str]:
    """Returns the email/alias of the currently active agy-auth account, if available."""
    agy_auth_bin = (
        os.path.expanduser("~/.local/bin/agy-auth")
        if os.path.exists(os.path.expanduser("~/.local/bin/agy-auth"))
        else (shutil.which("agy-auth") or "agy-auth")
    )
    if not shutil.which(agy_auth_bin) and not os.path.exists(agy_auth_bin):
        return None
    try:
        proc = subprocess.run(
            [agy_auth_bin, "list", "--json"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if proc.returncode == 0:
            res = json.loads(proc.stdout)
            curr = res.get("data", {}).get("current", {})
            email = curr.get("email") or curr.get("id")
            alias = curr.get("alias")
            if email:
                rem = curr.get("usage", {}).get("five_hour", {}).get("remaining_percent")
                rem_str = f" ({rem}% 5h quota)" if rem is not None else ""
                return f"{email}{' [' + alias + ']' if alias else ''}{rem_str}"
    except Exception:
        pass
    return None


def run_reviewer_turn(
    repo_root: str,
    round_number: int,
    existing_convo_id: Optional[str],
    model: str = DEFAULT_MODEL,
    effort: str = DEFAULT_EFFORT,
    fp_script: Optional[str] = None,
    _already_rotated: bool = False,
) -> Dict[str, Any]:
    skills = find_review_skills(repo_root)
    use_resume = bool(existing_convo_id)
    prompt = build_prompt(round_number, use_resume, repo_root, skills, fp_script)

    args = [
        AGY_BIN,
        "--model", model,
        "--effort", effort,
        "--output-format", "json",
        "--disable-slash-commands",
        "--dangerously-skip-permissions",
    ]
    if existing_convo_id:
        args.extend(["--conversation", existing_convo_id])
    args.append(f"-p={prompt}")

    env = os.environ.copy()
    env["AGY_REVIEWER"] = "1"

    try:
        proc = subprocess.run(
            args,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=REVIEWER_TIMEOUT_SEC,
            env=env,
            check=False,
        )

        envelope = parse_envelope(proc.stdout)
        clean_text = (envelope.get("response") if envelope else proc.stdout) or ""
        clean_text = clean_text.strip()
        verdict = parse_verdict(clean_text)

        if not verdict:
            raw_err = (
                (envelope.get("error") if envelope else "")
                or proc.stderr
                or proc.stdout
                or clean_text
                or ""
            )
            is_quota_exhausted = any(
                phrase in raw_err.lower()
                for phrase in [
                    "credits balance is too low",
                    "balance is too low",
                    "credit balance",
                    "quota",
                    "rate limit",
                    "resource_exhausted",
                    "too low to continue",
                ]
            )
            if is_quota_exhausted and not _already_rotated:
                rotated, rotate_msg = rotate_cli_account()
                if rotated:
                    send_desktop_notification(
                        "Antigravity Reviewer: Quota Rotated",
                        f"{rotate_msg}. Retrying reviewer turn...",
                    )
                    # Clear stored conversation ID in state since account changed
                    state = load_state()
                    state["conversationId"] = None
                    save_state(state)
                    # Retry review with fresh conversation on the rotated account
                    return run_reviewer_turn(
                        repo_root=repo_root,
                        round_number=round_number,
                        existing_convo_id=None,
                        model=model,
                        effort=effort,
                        fp_script=fp_script,
                        _already_rotated=True,
                    )

            err_detail = clip_text((envelope.get("error") if envelope else proc.stderr) or clean_text, 500)
            return {
                "ok": False,
                "verdict": None,
                "text": clean_text,
                "conversationId": None,
                "error": f"Antigravity reviewer exited (code {proc.returncode}) without verdict: {err_detail}",
            }

        convo_id = (envelope.get("conversation_id") if envelope else None) or existing_convo_id
        return {
            "ok": True,
            "verdict": verdict,
            "text": clean_text,
            "conversationId": convo_id,
            "error": None,
        }

    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "verdict": None,
            "text": "",
            "conversationId": None,
            "error": "Antigravity reviewer timed out after 20 minutes.",
        }
    except Exception as e:
        return {
            "ok": False,
            "verdict": None,
            "text": "",
            "conversationId": None,
            "error": str(e),
        }
