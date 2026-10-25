#!/usr/bin/env bash
set -euo pipefail

CONFIG_DIR="${HOME}/.gemini/config"
PLUGINS_DIR="${CONFIG_DIR}/plugins/auto-review"
SKILLS_DIR="${CONFIG_DIR}/skills/auto-review"
BIN_LINK="${HOME}/.local/bin/agy-review"
HOOKS_FILE="${CONFIG_DIR}/hooks.json"
STATE_FILE="${CONFIG_DIR}/auto-review.json"

PURGE="${1:-}"

echo "==> Uninstalling agy-auto-review..."

# 1. Unregister Stop hook from hooks.json
if [ -f "${HOOKS_FILE}" ]; then
    python3 - <<EOF
import json, os

hooks_path = "${HOOKS_FILE}"
try:
    with open(hooks_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "hooks" in data:
        orig_count = len(data["hooks"])
        data["hooks"] = [
            h for h in data["hooks"]
            if not ("review_hook.py" in h.get("command", "") or "auto-review" in h.get("command", ""))
        ]
        if len(data["hooks"]) < orig_count:
            with open(hooks_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            print("Removed Stop hook from ~/.gemini/config/hooks.json")
        else:
            print("No auto-review hook found in ~/.gemini/config/hooks.json")
except Exception as e:
    print(f"Warning: Could not update hooks.json: {e}")
EOF
fi

# 2. Remove CLI symlink
if [ -L "${BIN_LINK}" ] || [ -f "${BIN_LINK}" ]; then
    rm -f "${BIN_LINK}"
    echo "Removed ${BIN_LINK}"
fi

# 3. Remove plugin and skill folders
if [ -d "${PLUGINS_DIR}" ]; then
    rm -rf "${PLUGINS_DIR}"
    echo "Removed ${PLUGINS_DIR}"
fi

SKILL_NAMES=("auto-review" "agy-review" "review-loop" "review-status" "review-reset" "review-now" "review-off" "review-once")
for s in "${SKILL_NAMES[@]}"; do
    if [ -d "${CONFIG_DIR}/skills/${s}" ]; then
        rm -rf "${CONFIG_DIR}/skills/${s}"
        echo "Removed ${CONFIG_DIR}/skills/${s}"
    fi
done

# 4. Optional purge of state file
if [ "${PURGE}" = "--purge" ] && [ -f "${STATE_FILE}" ]; then
    rm -f "${STATE_FILE}"
    echo "Purged state file ${STATE_FILE}"
elif [ -f "${STATE_FILE}" ]; then
    echo "Preserved configuration state in ${STATE_FILE} (pass --purge to delete)"
fi

echo "✓ agy-auto-review uninstalled successfully."
