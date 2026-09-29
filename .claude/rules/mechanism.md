---
paths:
  - "lib/**"
  - "hooks/**"
---

# Changing hook behaviour

Read [docs/design/mechanism.md](../../docs/design/mechanism.md) before you change
what a hook does, when it checks, or what it writes. It is German.

- The check runs at the *second* event after a compaction (`PostToolBatch` or
  `UserPromptSubmit`); the first only moves the marker. Claude Code reports the
  reloaded files after the hook has returned — checking earlier duplicates the core.
- Every path exits 0; ruler writes only below `${CLAUDE_PLUGIN_DATA}`.
- A change to when or what ruler attaches needs a measurement first
  (design/measurements.md, skill `ruler-remeasure`), and goes into the design in the
  same commit.
