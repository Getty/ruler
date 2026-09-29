# ruler — CLAUDE.md

Claude Code plugin for the Getty marketplace. It keeps the **core** — the
instruction files Claude Code loads at session start — in context across every
compaction, and keeps copies of them out of the compaction summary.

**[docs/design.md](docs/design.md) is the spec.** Read it in full before
changing behaviour, adding a hook, writing a test or judging whether something
is in scope. It is written in German: *Kern* = core, *Baustein* = building
block, *Stufe* = stage.

## Status

2026-09-29: stages 0 to 3 are done, stage 4 but for one point: acceptance with
`claude -p`, the README and the marketplace entry (`ruler@getty`) are there,
acceptance in an interactive session is open. Update this paragraph when a
stage completes.

## Rules

- **Measured, not remembered.** Hook payload shapes, event order and size
  limits come from a recorded payload in `t/fixtures/` or from the current docs
  at code.claude.com/docs — they change between Claude Code versions. Every
  such fact in the design carries its date and Claude Code version.
- **Fail open.** Every hook path exits 0. ruler uses documented hooks only,
  writes only under `${CLAUDE_PLUGIN_DATA}`, and starts neither network
  connections nor subprocesses. Details: design, *Fehlerverhalten*.
- **The design stays true.** Findings go into `docs/design.md` in the same
  change as the code they affect; where code and design disagree, one of them
  is a bug.
- Python 3, stdlib only. Tests: `python3 -m unittest discover -s t -v`.
- The design is German; code, comments, README, commit messages and every text
  ruler puts in front of the model are English.
- Conventional commits, `--signoff`.

## This file is core

It is loaded into every context and ruler re-attaches it after every
compaction, so it holds only what applies to every task. Material for one part
of the code goes into `.claude/rules/*.md` with `paths:`; reasoning and
evidence go into the design.
