# agy-auto-review

> Automated code review loop and quota-resilient verification mod for Antigravity (CLI & Desktop).

`agy-auto-review` runs an independent reviewer session (`gemini-3.8-flash`, high effort) whenever an agent completes its turn in a git repository. If blocking findings are found (`CHANGES_REQUIRED`), the agent execution loop is re-entered with structured feedback until all checks pass and the implementation is `APPROVED`.

---

## Features

- **Automated Verification Loop**: Intercepts turn termination (`Stop` lifecycle hook) and feeds back actionable review findings until approved.
- **Skill Discovery**: Automatically detects and strictly adheres to project-specific review standards in `.agents/skills/` (e.g. `review-change`, `review-test`).
- **Quota Auto-Rotation**: Integrates with [`agy-auth`](https://github.com/fikrilal/agy-auth) to seamlessly switch CLI accounts when 5-hour Gemini credits are exhausted, retrying automatically.
- **Desktop & CLI Unified**: Works identically in the terminal (`agy`) and Antigravity Desktop app.
- **Zero Drift**: Automatically git-excludes generated review logs (`.agents/review-latest.md`) and short-circuits re-reviews on clean approvals.
- **Zero Python Dependencies**: Written entirely in Python standard library.

---

## Documentation

- **[Engineering Proposal](docs/proposals/2026-10-25_agy-auto-review-proposal.md)**: Full architecture, state machine, sequence diagrams, and open-source specifications.
- **Plugin Manifest**: [`plugin.json`](plugin.json)
- **Agent Skill Definition**: [`skills/auto-review/SKILL.md`](skills/auto-review/SKILL.md)

---

## License

[MIT](LICENSE)
