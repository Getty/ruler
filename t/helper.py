"""Shared by all tests: import path, fixtures, a replay of recorded sessions."""

import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "lib"))

from ruler import hook  # noqa: E402

FIXTURES = os.path.join(ROOT, "t", "fixtures")

# Where the recorded project lived; the parent directory held instructions too.
RECORDED = (
    "/tmp/claude-1000/-home-getty-dev-ruler/"
    "dba53873-9445-4999-b543-ce545bff5829/scratchpad"
)
PROJECT = RECORDED + "/probe"


def payloads(name, root=None):
    """The payloads of a fixture, optionally moved to another directory."""
    found = []
    with open(os.path.join(FIXTURES, name + ".jsonl"), encoding="utf-8") as fh:
        for line in fh:
            if root is not None:
                line = line.replace(RECORDED, root)
            found.append(json.loads(line)["payload"])
    return found


def entries(name, root=None):
    """The log ruler writes for a fixture."""
    found = []
    for payload in payloads(name, root):
        event = payload["hook_event_name"]
        if event == "InstructionsLoaded":
            found.append(dict(payload, event="loaded"))
        elif event == "SessionStart" and payload["source"] == "compact":
            found.append({"event": "compact"})
    return found


def run(payload, data, home=None):
    """Runs one hook and returns what it printed."""
    out = io.StringIO()
    environ = {"CLAUDE_PLUGIN_DATA": data, "HOME": home or data}
    text = payload if isinstance(payload, str) else json.dumps(payload)
    code = hook.main([], io.StringIO(text), out, environ)
    assert code == 0
    return out.getvalue()


def replay(sequence, data, home=None):
    """Runs a recorded session through the hooks, in recorded order.

    InstructionsLoaded hooks run on their own, so a hook that waits sees the
    ones recorded right behind it arrive: the wait is replayed by delivering them.
    """
    queue = list(sequence)
    printed = []

    def arrive(_seconds=None):
        while queue and queue[0]["hook_event_name"] == "InstructionsLoaded":
            run(queue.pop(0), data, home)

    sleep, hook.time.sleep = hook.time.sleep, arrive
    try:
        while queue:
            payload = queue.pop(0)
            text = run(payload, data, home)
            if text:
                printed.append((payload["hook_event_name"], text))
    finally:
        hook.time.sleep = sleep
    return printed


def tree(root, files):
    """Writes files, given as relative path -> content, below root."""
    for name, content in files.items():
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)


# The recorded project, as it was on disk for startup.jsonl.
PROBE = {
    "CLAUDE.md": "# parent\n\nMarker: PARENT-ROOT-GOLF.\n",
    ".claude/rules/parent-rule.md": "# parent rule\n\nMarker: PARENT-RULE-FOXTROT.\n",
    "probe/CLAUDE.md": "# probe\n\nThrowaway project for recording hook payloads. Marker: CORE-ROOT-ALPHA.\n\n@docs/imported.md\n",
    "probe/CLAUDE.local.md": "# local\n\nMarker: LOCAL-HOTEL.\n",
    "probe/docs/imported.md": "# imported\n\nImported from CLAUDE.md. Marker: CORE-IMPORT-BRAVO.\n",
    "probe/.claude/rules/core-rule.md": "# core rule\n\nRule without paths. Marker: CORE-RULE-CHARLIE.\n",
    "probe/.claude/rules/deep/deep-rule.md": "# deep rule\n\nMarker: DEEP-RULE-INDIA.\n",
    "probe/.claude/rules/scoped-rule.md": '---\npaths:\n  - "src/**"\n---\n\n# scoped rule\n\nRule with paths. Marker: SCOPED-RULE-DELTA.\n',
    "probe/.claude/rules/scoped-two.md": '---\npaths: "sub/**, docs/**"\n---\n\n# scoped two\n\nMarker: SCOPED-TWO-JULIET.\n',
    "probe/sub/CLAUDE.md": "# sub\n\nNested CLAUDE.md. Marker: NESTED-ECHO.\n",
    "probe/src/a.txt": "alpha file\n",
    "probe/sub/b.txt": "bravo file\n",
}
