"""Per-session event log and pending marker, both under the plugin data directory."""

import json
import os
import re
import time

MAX_AGE = 7 * 24 * 3600

_ID = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def valid_id(session_id):
    return isinstance(session_id, str) and bool(_ID.match(session_id))


def log_path(data, session_id):
    return os.path.join(data, "sessions", session_id + ".jsonl")


def pending_path(data, session_id):
    return os.path.join(data, "pending", session_id)


def append(data, session_id, entry):
    """Appends one line with a single write, so concurrent hooks never interleave."""
    path = log_path(data, session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    line = json.dumps(entry, separators=(",", ":")) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)


def read(data, session_id):
    """Returns the entries of a session. A missing log is empty; an unreadable one raises."""
    try:
        with open(log_path(data, session_id), encoding="utf-8") as fh:
            lines = fh.readlines()
    except FileNotFoundError:
        return []
    entries = []
    for line in lines:
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def get_pending(data, session_id):
    """Returns the state of the pending marker, or None if there is none."""
    try:
        with open(pending_path(data, session_id), encoding="utf-8") as fh:
            text = fh.read().strip()
    except FileNotFoundError:
        return None
    try:
        return int(text)
    except ValueError:
        return 0


def set_pending(data, session_id, state):
    path = pending_path(data, session_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.%d.tmp" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("%d\n" % state)
    os.replace(tmp, path)


def clear_pending(data, session_id):
    _remove(pending_path(data, session_id))


def cleanup(data, session_id):
    _remove(log_path(data, session_id))
    clear_pending(data, session_id)


def prune(data, now=None, max_age=MAX_AGE):
    """Removes logs and markers of sessions that ended without SessionEnd."""
    now = time.time() if now is None else now
    for sub in ("sessions", "pending"):
        directory = os.path.join(data, sub)
        try:
            names = os.listdir(directory)
        except OSError:
            continue
        for name in names:
            path = os.path.join(directory, name)
            try:
                if now - os.stat(path).st_mtime > max_age:
                    os.remove(path)
            except OSError:
                continue


def _remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
