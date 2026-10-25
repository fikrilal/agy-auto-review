---
name: review-loop
description: Arm continuous automated code review loop until approved (default: 10 cycles).
---

# Review Loop

Arms the automated Antigravity code review loop.

## Workflow

If the user specified a cycle limit (e.g. `5`), run `agy-review on <limit>` via `run_command`.
Otherwise, run `agy-review on` via `run_command`.
Report to the user that the review loop is armed.
