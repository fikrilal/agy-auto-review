#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${HOME}/.gemini/config"
PLUGINS_DIR="${CONFIG_DIR}/plugins/auto-review"
BIN_DIR="${HOME}/.local/bin"

echo "==> Installing agy-auto-review..."

# 1. Create target directories
mkdir -p "${PLUGINS_DIR}/scripts"
mkdir -p "${PLUGINS_DIR}/skills"
mkdir -p "${CONFIG_DIR}/skills"
mkdir -p "${BIN_DIR}"

# 2. Copy files
cp "${SCRIPT_DIR}/plugin.json" "${PLUGINS_DIR}/plugin.json"
cp "${SCRIPT_DIR}/scripts/"*.py "${PLUGINS_DIR}/scripts/"

# Copy all skills into both plugin skills and root global skills
for sdir in "${SCRIPT_DIR}/skills/"*; do
    if [ -d "${sdir}" ]; then
        sname="$(basename "${sdir}")"
        mkdir -p "${PLUGINS_DIR}/skills/${sname}"
        mkdir -p "${CONFIG_DIR}/skills/${sname}"
        cp -r "${sdir}/"* "${PLUGINS_DIR}/skills/${sname}/"
        cp -r "${sdir}/"* "${CONFIG_DIR}/skills/${sname}/"
    fi
done

# Make scripts executable
chmod +x "${PLUGINS_DIR}/scripts/"*.py

# 3. Symlink agy-review CLI
ln -sf "${PLUGINS_DIR}/scripts/agy_review_cli.py" "${BIN_DIR}/agy-review"

# 4. Register lifecycle hook in hooks.json
HOOKS_FILE="${CONFIG_DIR}/hooks.json"
python3 - <<EOF
import json, os

hooks_path = "${HOOKS_FILE}"
hook_command = "${PLUGINS_DIR}/scripts/review_hook.py"

data = {"hooks": []}
if os.path.exists(hooks_path):
    try:
        with open(hooks_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
            if isinstance(loaded, dict) and "hooks" in loaded:
                data = loaded
    except Exception:
        pass

# Check if hook already registered
exists = any(
    h.get("event") == "Stop" and h.get("command") == hook_command
    for h in data.get("hooks", [])
)

if not exists:
    data["hooks"].append({
        "event": "Stop",
        "command": hook_command
    })
    with open(hooks_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print("Registered Stop hook in ~/.gemini/config/hooks.json")
else:
    print("Stop hook already registered in ~/.gemini/config/hooks.json")
EOF

echo "✓ agy-auto-review installed successfully!"
echo "Run 'agy-review status' to check configuration."
