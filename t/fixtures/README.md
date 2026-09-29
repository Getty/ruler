# Fixtures

Hook payloads recorded on 2026-09-29 with Claude Code 2.1.284 (`claude -p`,
model `claude-haiku-4-5`), in a throwaway project holding a `CLAUDE.md` with one
`@import`, a rule without `paths:`, a rule with `paths:` and a nested
`sub/CLAUDE.md`. One line per hook call, ordered by the time the hook process
started:

```json
{"t_ms": 0.0, "payload": { ...stdin of the hook, verbatim... }}
```

`t_ms` is the start of the hook process relative to the first one in the file.
`hook_ran_ms` is present where the recording hook slept on purpose, to show
whether Claude Code waits for it.

Shortened, and marked as such in place: the file content in `tool_response` of
`PostToolUse` and `PostToolBatch`. Everything else is as recorded.

| File | Session |
|---|---|
| `startup.jsonl` | Start and one prompt. Adds a `CLAUDE.md` and a rule in the parent directory, a `CLAUDE.local.md` and a rule in a subdirectory of `.claude/rules/`. |
| `resume-manual-compact.jsonl` | `--resume`, then `/compact keep the file names`, then exit. |
| `manual-compact.jsonl` | Two file reads, `/compact`, two more prompts. |
| `auto-compact.jsonl` | Auto-compaction in the middle of a turn, then a batch of three parallel reads. Recording hook slept 0.7 s in `UserPromptSubmit`, `PostToolUse` and `PostToolBatch`. |
