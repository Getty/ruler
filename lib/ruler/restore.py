"""What is missing after a compaction, and the context that brings it back."""

from . import core

# Cap of additionalContext per hook output, code.claude.com/docs/en/hooks, 2026-09-29.
LIMIT = 10000

REST = "These project instruction files are not in context after the compaction. Read these files now before continuing:"


def reloaded(entries):
    """Files loaded since the last completed compaction."""
    last = -1
    for index, entry in enumerate(entries):
        if entry.get("event") == "compact":
            last = index
    return {core.key(entry["file_path"]) for entry in core.loads(entries[last + 1:])}


def missing(entries, files):
    back = reloaded(entries)
    return [path for path in files if core.key(path) not in back]


def render(path, text):
    return "Project instructions from %s (re-attached by ruler after compaction):\n\n%s" % (
        path,
        text.strip("\n"),
    )


def build(paths, limit=LIMIT, read=core.read_text):
    """Context for the missing files, read fresh from disk.

    Whole files go in while they fit; the rest is named for the Read tool.
    """
    parts = []
    rest = []
    for path in paths:
        text = read(path)
        if text is None:
            continue
        parts.append((path, render(path, core.split_frontmatter(text)[1])))
    while True:
        context = _join([chunk for _, chunk in parts], rest)
        if size(context) <= limit or not parts:
            break
        rest.insert(0, parts.pop()[0])
    while size(context) > limit and rest:
        rest.pop()
        context = _join([], rest)
    return context


def size(text):
    """Length as Claude Code counts it: UTF-16 code units."""
    return len(text.encode("utf-16-le")) // 2


def _join(chunks, rest):
    chunks = list(chunks)
    if rest:
        chunks.append("\n".join([REST] + ["- " + path for path in rest]))
    return "\n\n".join(chunks)
