# agy-auto-review

> Automated code review loop and quota-resilient verification mod for Antigravity (CLI & Desktop).

`agy-auto-review` runs an independent reviewer session (`gemini-3.8-flash`, high effort) whenever an agent completes its coding turn in a git repository. If blocking findings are detected (`CHANGES_REQUIRED`), the agent loop is re-entered with structured feedback until all checks pass and the implementation is `APPROVED`.

---

## Features

- **Automated Verification Loop**: Intercepts turn completion (`Stop` lifecycle hook) and feeds back actionable review findings until approved.
- **Skill Discovery**: Automatically detects and strictly adheres to project-specific review standards in `.agents/skills/` (e.g. `review-change`, `review-test`).
- **Quota Auto-Rotation**: Integrates with [`agy-auth`](https://github.com/fikrilal/agy-auth) to seamlessly switch CLI accounts when 5-hour Gemini credits are exhausted, retrying automatically.
- **Desktop & CLI Unified**: Works identically in the terminal (`agy`) and Antigravity Desktop app.
- **Smart Turn Detection**: Never triggers on pure discussion/chat turns; only activates when the agent actively modifies repository code.
- **Zero Drift**: Automatically git-excludes generated review logs (`.agents/review-latest.md`) and short-circuits re-reviews on clean approvals.
- **Zero External Dependencies**: Pure Python standard library.

---

## Quickstart

### 1. One-Line Installation (No Git Clone Required)

Run directly in your terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/fikrilal/agy-auto-review/main/install.sh | bash
```

*Or install from local source:*
```bash
git clone https://github.com/fikrilal/agy-auto-review.git
cd agy-auto-review && ./install.sh
```

### 2. Auto-Updates

Check for and install updates at any time:

```bash
agy-review update
```

*(You can also run `agy-review update --check` to only check for new versions, or pass `--force` to reinstall).*

### 3. Usage & Slash Commands

Use either terminal commands or chat slash commands:

| Command | Slash Command | Description |
|---|---|---|
| `agy-review status` | `/review-status` | Display current mode, review cycles, active account, and repo status |
| `agy-review on [n]` | `/review-loop` | Enable continuous review loop (default up to 10 cycles) |
| `agy-review once` | `/review-once` | Arm review for 1 cycle after next coding turn |
| `agy-review off` | `/review-off` | Disable automatic reviews |
| `agy-review now` | `/review-now` | Run Antigravity reviewer immediately on current workspace |
| `agy-review reset` | `/review-reset` | Reset reviewer session and cycle count |
| `agy-review rotate` | — | Manually rotate to next Antigravity account with quota |
| `agy-review update` | — | Pull latest updates from GitHub |

### 4. Running Tests

```bash
make test
```

### 5. Uninstallation

One-line uninstall without cloning:

```bash
curl -fsSL https://raw.githubusercontent.com/fikrilal/agy-auto-review/main/uninstall.sh | bash
```
*(Pass `--purge` to delete stored configuration state in `~/.gemini/config/auto-review.json`)*

---

## Documentation

- **[Engineering Proposal](docs/proposals/2026-10-25_agy-auto-review-proposal.md)**: Full architecture, state machine, sequence diagrams, and open-source specifications.
- **Plugin Manifest**: [`plugin.json`](plugin.json)
- **Agent Skill Definition**: [`skills/auto-review/SKILL.md`](skills/auto-review/SKILL.md)

---

## License

[MIT](LICENSE)
