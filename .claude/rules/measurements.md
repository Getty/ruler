---
paths:
  - "t/**"
  - "docs/design/measurements.md"
---

# Tests and measurements

Fixtures in `t/fixtures/` are recorded hook payloads (see `t/fixtures/README.md`);
never edit them by hand. Behaviour that depends on Claude Code — event order,
timing, size limits — is a *measurement*: it carries its date and version in
[docs/design/measurements.md](../../docs/design/measurements.md).

`claude -p` and the interactive session differ in when reloaded files are reported
(Messung 7). A new fixture or a change of timing assumptions is checked in an
interactive session too; the skill `ruler-remeasure` says how.
