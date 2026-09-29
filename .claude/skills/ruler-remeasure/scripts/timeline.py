#!/usr/bin/env python3
"""Print what happened around a compaction in a session transcript.

usage: timeline.py [transcript.jsonl]   (default: newest transcript of the cwd's project)

One line per prompt, hook attachment, instructions attachment and compaction, with
the time. A `hook_additional_context` that carries "re-attached by ruler" is ruler
attaching files; the `instructions` attachments are Claude Code's own reload.
"""
import glob
import json
import os
import sys


def newest():
    slug = os.getcwd().replace("/", "-").replace(".", "-").replace("_", "-")
    files = glob.glob(os.path.expanduser("~/.claude/projects/%s/*.jsonl" % slug))
    if not files:
        sys.exit("no transcript for " + os.getcwd())
    return max(files, key=os.path.getmtime)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else newest()
    attached = 0
    for line in open(path):
        d = json.loads(line)
        a = d.get("attachment") or {}
        kind = a.get("type")
        text = ""
        if d.get("type") == "user" and not d.get("isMeta"):
            c = (d.get("message") or {}).get("content")
            text = c if isinstance(c, str) else json.dumps(c)
            if text.startswith("This session is being continued"):
                label = "COMPACTED"
            else:
                label = "prompt"
        elif kind == "hook_additional_context":
            text = " ".join(a.get("content") or [])
            ours = "re-attached by ruler" in text
            attached += ours
            label = "RULER ATTACH" if ours else "hook context"
            label += " " + str(a.get("hookEvent"))
        elif kind == "instructions":
            label = "instructions"
            text = ", ".join(os.path.basename(f.get("path", "")) for f in a.get("files", []))
        else:
            continue
        print(d.get("timestamp", "")[11:23], label.ljust(28), text[:90].replace("\n", " "))
    print("ruler attachments:", attached)


main()
