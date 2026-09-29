---
name: ruler-remeasure
description: Use when a new Claude Code version ships, when ruler's timing or attach behaviour is in doubt, before changing when a hook checks, or when a design/measurements.md fact needs a fresh date and version — repeating the compaction measurement in a real interactive session with tmux.
---

# Repeat the ruler measurement interactively

`claude -p` and the interactive TUI report reloaded files at different moments, so a
fact measured with `-p` is not yet a fact about ruler. Run the session for real, in
tmux, in a throwaway project. Everything below is a check against the transcript and
ruler's log — never against what the model says: a small model asked "how often is
this in your context?" guesses.

## Set up

Work under your scratchpad, not in the repo. The project needs a marker per file so
a count is unambiguous:

```sh
mkdir -p proj/.claude/rules && cd proj && git init -q .
printf '# T\nMarker-CLAUDE: PINEAPPLE-1\n@notes.md\n' > CLAUDE.md
printf 'Marker-IMPORT: PINEAPPLE-2\n' > notes.md
printf 'Marker-RULE: PINEAPPLE-3\n' > .claude/rules/always.md
printf -- '---\npaths:\n  - "*.py"\n---\nMarker-PATHRULE: PINEAPPLE-4\n' > .claude/rules/py.md
tmux new-session -d -s rt -x 200 -y 50 "claude --plugin-dir <ruler checkout> --model haiku"
```

Expected before any compaction: markers 1–3 known, 4 not.

## Drive it

```sh
tmux capture-pane -t rt -p | grep -v '^$' | tail -20    # look after every step
```

- First start shows a trust dialog for the directory: `tmux send-keys -t rt Down Enter`
  (the directory is yours).
- Send text and Enter as **two** `send-keys` calls with a `sleep 1` between, and use
  `C-m`: a single `"text" Enter` leaves the text in the input box unsent.
- Sequence: a short prompt → `/compact` (wait 40–50 s) → two more prompts → `/exit`.
  Look at the pane for ruler's `PreCompact … completed successfully` block after `/compact`.

## Read the result

Inspect before `/exit` (SessionEnd deletes the log):

```sh
ls ~/.claude/plugins/data/ruler-inline/pending     # empty = check done
cut -c1-120 ~/.claude/plugins/data/ruler-inline/sessions/*.jsonl
cd proj && <ruler checkout>/.claude/skills/ruler-remeasure/scripts/timeline.py
```

Run `timeline.py` (execute, don't read) from the project directory. It lists prompts,
Claude Code's own `instructions` attachments and every `RULER ATTACH`.

Healthy: after the compaction the log has a `loaded` line with `load_reason: compact`
for every core file, `instructions` follows the next prompt, `ruler attachments: 0`,
`pending/` empty, data directory empty after `/exit`.

Bug: `RULER ATTACH` although the log shows all files reloaded. Then compare the prompt
timestamp with the attachment: about the length of `GRACE` means the check ran before
Claude Code reported the files.

## Variants

- **Forced gap.** Copy the checkout, make its `InstructionsLoaded` handler skip
  `load_reason == "compact"`, and load the copy with `--plugin-dir`. Expect ruler to
  attach the affected files once, at the second event, and not the `include` import.
- **Auto-compaction mid-turn.** Start with
  `CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000 CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=40` and give
  prompts that read large files until it fires. Expected: check at the second
  `PostToolBatch`.

## Finish

`tmux send-keys -t rt "/exit"`, `C-m`, then `tmux kill-session -t rt`. Write the result
into `docs/design/measurements.md` as the next *Messung N* with today's date and the
version from the pane header (`claude --version`), in the same commit as any code
change it caused. If the result contradicts `docs/design/mechanism.md`, one of them is
a bug — fix the mechanism text too.
