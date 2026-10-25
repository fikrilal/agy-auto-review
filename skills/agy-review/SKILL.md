---
name: agy-review
description: Manage Antigravity automated code review settings, status, cycle counts, and manual review triggers.
---

# Antigravity Reviewer Control

Inspect or control the automated code review loop.

## Workflow

If the user passed arguments:
- `on [cycles]`: Run `agy-review on [cycles]` via `run_command`
- `off`: Run `agy-review off` via `run_command`
- `reset`: Run `agy-review reset` via `run_command`
- `rotate`: Run `agy-review rotate` via `run_command`
- `now`: Run `agy-review now` via `run_command`
- Otherwise, run `agy-review status` via `run_command` and display the formatted status.
