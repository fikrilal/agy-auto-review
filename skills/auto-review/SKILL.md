---
name: auto-review
description: Control and monitor the automated Antigravity code review loop. Triggers when the user asks to turn auto review on or off, check review status, run a review, or uses slash commands like /review-loop, /auto-review, /review-on, /review-off, /review-status, /review-now.
---

# Antigravity Auto-Review Control

Controls the automated review loop triggered whenever the agent finishes making changes in a repository.

## Commands

Use the `run_command` tool to manage auto-review:

- **Turn On (Default: Loop with 10 max cycles)**:
  `agy-review on`
- **Turn On with Custom Max Cycles**:
  `agy-review on 5`
- **Turn On for 1 Cycle**:
  `agy-review once`
- **Turn Off**:
  `agy-review off`
- **Check Status**:
  `agy-review status`
- **Reset Session / Counts**:
  `agy-review reset`
- **Rotate Account Quota**:
  `agy-review rotate`
- **Run Review Immediately**:
  `agy-review now`

## How it works

When active, Antigravity CLI runs a background reviewer session (`gemini-3.8-flash`, high effort) whenever coding changes are made.
The reviewer automatically discovers and follows review skills in `.agents/skills` (e.g., `review-change`, `review-test`).
If changes are required, the agent execution loop is automatically re-entered with findings until approved.
If the active account runs out of AI credit/quota, it automatically invokes `agy-auth rotate --target=cli` to switch to the healthiest account and retries the review turn seamlessly.
