# ruler

A Claude Code plugin that keeps your project instructions in context across
compactions.

Claude Code re-reads `CLAUDE.md` and the rules without `paths:` from disk after a
compaction. In practice some of them are sometimes missing afterwards, and the
summary that replaces the conversation tends to carry a copy of their content —
one that goes stale as soon as you edit the file. ruler does two things about
that:

- **Before a compaction** it tells the summary which instruction files come back
  from disk anyway, so that their content stays out of it.
- **After a compaction** it checks which of those files Claude Code reported as
  reloaded, and attaches the ones that did not come back, read fresh from disk.

When everything came back, ruler adds nothing.

## What is covered

**The core**: the instruction files Claude Code loads when a session starts.

- `CLAUDE.md`, `.claude/CLAUDE.md` and `CLAUDE.local.md` in the working directory
  and every directory above it
- `~/.claude/CLAUDE.md`
- rules without `paths:` in `.claude/rules/` and `~/.claude/rules/`
- everything these files pull in with `@import`

**Not covered, on purpose**: rules with `paths:`, a `CLAUDE.md` in a
subdirectory, skills. Claude Code loads these when it reads a matching file, and
loads them again the same way after a compaction. Attaching them always would
defeat their purpose. If one of them has to survive every compaction, make it
core: remove `paths:`, or move the text into the project's `CLAUDE.md`.

## Install

```
/plugin marketplace add Getty/marketplace
/plugin install ruler@getty
```

Or load it from a checkout, without a marketplace:

```sh
claude --plugin-dir /path/to/ruler
```

It needs `python3` on `PATH` and nothing else. Without it, ruler does nothing.

## Keep the core small

Only the core is guaranteed to survive a compaction, and it costs tokens in every
context, before and after.

- Keep `CLAUDE.md` short: only what applies in *every* situation.
- Put material for one part of the code into a rule with `paths:`, a `CLAUDE.md`
  in that subdirectory, or a skill. It loads when needed, and again after a
  compaction.
- `@import` does not make the core smaller. Imported files load at once and
  count as core.
- Files that do not fit are not attached. A hook may add 10,000 characters to the
  context; ruler attaches whole files while they fit and asks Claude to read the
  rest with the Read tool.

## How it works

| Hook | What ruler does |
|---|---|
| `InstructionsLoaded` | Appends one line per loaded file to a log for the session. |
| `PreCompact` | Prints the list of core files and the request not to copy them into the summary. Claude Code appends this to your own `/compact` instructions. |
| `SessionStart` (`compact`) | Marks the session as compacted. |
| `UserPromptSubmit`, `PostToolBatch` | For a marked session: compares the core with what was reloaded, attaches what is missing, removes the mark. For every other session they return at once, without starting Python. |
| `SessionStart` (`startup`) | Removes logs older than seven days. |
| `SessionEnd` | Removes the log of the session. |

Claude Code reports the reloaded files only after the first hook that follows a
compaction has returned. ruler therefore checks at the second one: the next
prompt, or the second batch of tool calls. If a file is really missing at that
point, one prompt (after `/compact`) or two requests to the model (compaction in
the middle of a turn) have run without it.

ruler writes only below `${CLAUDE_PLUGIN_DATA}`, opens no network connection, and
every hook ends with exit code 0, whatever happens.

## Limits

- ruler knows what Claude Code reports through `InstructionsLoaded`. A file that
  is reported as reloaded but is not in the context goes unnoticed.
- That a `PreCompact` hook can add to the instructions for the summary is
  observed behaviour of Claude Code 2.1.284, not documented. Should it stop
  working, the summary may copy instruction files again; the check after the
  compaction does not depend on it.
- After a compaction you see ruler's list of files in the message that reports
  the compaction. Claude Code shows the output of every `PreCompact` hook there.
- Measured with `claude -p`. Interactive sessions use the same hooks but have
  not been measured separately.

[docs/design.md](docs/design.md) has the reasoning and the measurements, in
German.

## Tests

```sh
python3 -m unittest discover -s t -v
```

The fixtures in `t/fixtures/` are hook payloads recorded from real sessions.

## License

Artistic License 2.0, see [LICENSE](LICENSE).
