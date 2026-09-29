#!/usr/bin/env python3
"""Print ruler's event log readably: time, event, load_reason/trigger, file name.

usage: log.py [log.jsonl ...]   (default: every log under the ruler data directory)
"""
import glob
import json
import os
import sys

paths = sys.argv[1:] or glob.glob(os.path.expanduser("~/.claude/plugins/data/ruler-inline/sessions/*.jsonl"))
if not paths:
    sys.exit("no ruler log (SessionEnd removes it: read it before /exit)")
for path in paths:
    print(os.path.basename(path))
    for line in open(path):
        e = json.loads(line)
        print("  %10.3f %-10s %-16s %s" % (e["t"] % 1000, e["event"], e.get("load_reason") or e.get("trigger") or "",
                                            os.path.basename(e.get("file_path") or "")))
