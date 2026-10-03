"""Entry point of every hook. Whatever happens, the exit code is 0."""

import json
import os
import sys
import time

from . import compact, core, log, restore

# InstructionsLoaded hooks run concurrently with the hook that checks; this is
# how long the check waits for their lines.
GRACE = 1.0
STEP = 0.05


def main(argv=None, stdin=None, stdout=None, environ=None):
    try:
        _run(
            sys.argv[1:] if argv is None else argv,
            sys.stdin if stdin is None else stdin,
            sys.stdout if stdout is None else stdout,
            os.environ if environ is None else environ,
        )
    except BaseException:
        pass
    return 0


def _run(argv, stdin, stdout, environ):
    data = environ.get("CLAUDE_PLUGIN_DATA")
    if not data:
        return
    payload = json.loads(stdin.read())
    if not isinstance(payload, dict):
        return
    event = payload.get("hook_event_name") or (argv[0] if argv else None)
    session_id = payload.get("session_id")
    handler = HANDLERS.get(event)
    if handler is None or not log.valid_id(session_id):
        return
    payload["hook_event_name"] = event
    # A subagent shares the session id but has a context of its own.
    if payload.get("agent_id"):
        return
    handler(payload, data, session_id, stdout, environ)


def instructions_loaded(payload, data, session_id, stdout, environ):
    entry = {
        "event": "loaded",
        "t": round(time.time(), 3),
        "file_path": payload.get("file_path"),
        "load_reason": payload.get("load_reason"),
        "memory_type": payload.get("memory_type"),
    }
    if payload.get("parent_file_path"):
        entry["parent_file_path"] = payload["parent_file_path"]
    if entry["file_path"]:
        log.append(data, session_id, entry)


def pre_compact(payload, data, session_id, stdout, environ):
    try:
        log.append(
            data,
            session_id,
            {"event": "precompact", "t": round(time.time(), 3), "trigger": payload.get("trigger")},
        )
    except OSError:
        pass
    files = _core(data, session_id, payload, environ)
    text = compact.output(payload.get("custom_instructions"), files)
    if text:
        stdout.write(text + "\n")


def session_start(payload, data, session_id, stdout, environ):
    source = payload.get("source")
    if source == "startup":
        log.prune(data)
    elif source == "compact":
        log.append(data, session_id, {"event": "compact", "t": round(time.time(), 3)})
        log.set_pending(data, session_id, 0)


def check(payload, data, session_id, stdout, environ):
    state = log.get_pending(data, session_id)
    if state is None:
        return
    event = payload["hook_event_name"]
    if state == 0:
        # Claude Code reports the reloaded files only after the hook that follows the
        # compaction has returned (measured for both events), so the first one only
        # moves the marker.
        log.set_pending(data, session_id, 1)
        return
    files = _missing(data, session_id, payload, environ)
    log.clear_pending(data, session_id)
    context = restore.build(files) if files else ""
    if context:
        json.dump(
            {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}},
            stdout,
        )
        stdout.write("\n")


def session_end(payload, data, session_id, stdout, environ):
    log.cleanup(data, session_id)


def _home(environ):
    # Windows without Git Bash starts hooks with no HOME at all.
    return environ.get("HOME") or os.path.expanduser("~")


def _core(data, session_id, payload, environ):
    try:
        entries = log.read(data, session_id)
    except (OSError, UnicodeError):
        entries = []
    return core.of(entries, payload.get("cwd"), _home(environ))


def _missing(data, session_id, payload, environ):
    deadline = time.monotonic() + GRACE
    while True:
        try:
            entries = log.read(data, session_id)
        except (OSError, UnicodeError):
            # The check cannot be evaluated: better twice than not at all.
            return core.discover(payload.get("cwd") or os.getcwd(), _home(environ))
        files = restore.missing(entries, core.of(entries, payload.get("cwd"), _home(environ)))
        if not files or time.monotonic() >= deadline:
            return files
        time.sleep(STEP)


HANDLERS = {
    "InstructionsLoaded": instructions_loaded,
    "PreCompact": pre_compact,
    "SessionStart": session_start,
    "PostToolBatch": check,
    "UserPromptSubmit": check,
    "SessionEnd": session_end,
}


if __name__ == "__main__":
    sys.exit(main())
