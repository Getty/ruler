"""The core: the instruction files Claude Code loads at session start."""

import os
import re

MAX_IMPORT_HOPS = 4
MAX_FILE_SIZE = 4 * 1024 * 1024

_FENCE = re.compile(r"^\s*(```|~~~)")
_SPAN = re.compile(r"`[^`\n]*`")
_IMPORT = re.compile(r"(?:^|(?<=\s))@((?:\\ |[^\s])+)")
_PATHS = re.compile(r"^paths\s*:", re.MULTILINE)


def loads(entries):
    return [e for e in entries if e.get("event") == "loaded" and e.get("file_path")]


def has_session_start(entries):
    return any(e.get("load_reason") == "session_start" for e in loads(entries))


def derive(entries):
    """Core files from the log, in the order they first appear.

    Hooks write concurrently, so an include can precede its parent in the log.
    """
    found = loads(entries)
    core = []
    seen = set()
    for entry in found:
        if entry.get("load_reason") in ("session_start", "compact"):
            _add(core, seen, entry["file_path"])
    changed = True
    while changed:
        changed = False
        for entry in found:
            if entry.get("load_reason") != "include":
                continue
            parent = entry.get("parent_file_path")
            if parent and key(parent) in seen and key(entry["file_path"]) not in seen:
                _add(core, seen, entry["file_path"])
                changed = True
    return core


def discover(cwd, home=None):
    """Core files from disk, for a session whose start ruler has not seen."""
    home = os.path.expanduser("~") if home is None else home
    core = []
    seen = set()
    user = os.path.join(home, ".claude")
    roots = [os.path.join(user, "CLAUDE.md")] + _rules(os.path.join(user, "rules"))
    for directory in _ancestors(cwd):
        roots.append(os.path.join(directory, "CLAUDE.md"))
        roots.append(os.path.join(directory, ".claude", "CLAUDE.md"))
        roots.extend(_rules(os.path.join(directory, ".claude", "rules")))
        roots.append(os.path.join(directory, "CLAUDE.local.md"))
    for path in roots:
        _collect(path, home, core, seen, 0)
    return core


def of(entries, cwd, home=None):
    """The core of a session: from the log, completed from disk if the start is missing."""
    core = derive(entries)
    if has_session_start(entries):
        return core
    merged = discover(cwd, home) if cwd else []
    seen = {key(path) for path in merged}
    for path in core:
        _add(merged, seen, path)
    return merged


def has_paths(text):
    front = split_frontmatter(text)[0]
    return front is not None and bool(_PATHS.search(front))


def split_frontmatter(text):
    """Returns (yaml, body); yaml is None without leading --- markers."""
    lines = text.split("\n")
    if lines and lines[0].strip() == "---":
        for index in range(1, len(lines)):
            if lines[index].strip() == "---":
                return "\n".join(lines[1:index]), "\n".join(lines[index + 1:]).lstrip("\n")
    return None, text


def imports(text, base, home):
    """Paths named by @imports outside code spans and fenced code blocks."""
    found = []
    fenced = False
    for line in split_frontmatter(text)[1].split("\n"):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        for match in _IMPORT.finditer(_SPAN.sub(" ", line)):
            found.append(_resolve(match.group(1).replace("\\ ", " "), base, home))
    return found


def read_text(path):
    """Returns the text of an instruction file, or None if it cannot be loaded."""
    try:
        if not os.path.isfile(path) or os.path.getsize(path) > MAX_FILE_SIZE:
            return None
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None


def _collect(path, home, core, seen, hops):
    if key(path) in seen:
        return
    text = read_text(path)
    if text is None:
        return
    _add(core, seen, path)
    if hops >= MAX_IMPORT_HOPS:
        return
    for target in imports(text, os.path.dirname(path), home):
        for candidate in (target, target.rstrip(".,;:!?)")):
            if os.path.isfile(candidate):
                _collect(candidate, home, core, seen, hops + 1)
                break


def _rules(directory):
    """Rules without paths: below a rules directory, symlinks followed, sorted."""
    found = []
    visited = set()
    for root, dirs, files in os.walk(directory, followlinks=True):
        real = os.path.realpath(root)
        if real in visited:
            dirs[:] = []
            continue
        visited.add(real)
        dirs.sort()
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            text = read_text(path)
            if text is not None and not has_paths(text):
                found.append(path)
    return found


def _ancestors(cwd):
    """Directories from the filesystem root down to cwd."""
    directory = os.path.abspath(cwd)
    chain = [directory]
    while True:
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        chain.append(parent)
        directory = parent
    chain.reverse()
    return chain


def _resolve(target, base, home):
    if target == "~" or target.startswith("~/"):
        target = os.path.join(home, target[2:])
    return os.path.normpath(os.path.join(base, target))


def key(path):
    """What makes two paths the same file: on Windows case and slash direction
    do not count (Claude Code reports C:\\x\\CLAUDE.md, an @import may name
    c:/x/claude.md). On Linux and macOS the path itself."""
    return os.path.normcase(path)


def _add(core, seen, path):
    if key(path) not in seen:
        seen.add(key(path))
        core.append(path)
