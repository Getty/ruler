import json
import os
import shutil
import subprocess
import tempfile
import unittest

import helper
from ruler import hook, log

# Claude Code on Windows starts hooks/ruler.exe (winlaunch) for this entry;
# CreateProcess would pick the sh script itself if named without .exe.
EXE = ".exe" if os.name == "nt" else ""
STARTER = os.path.join(helper.ROOT, "hooks", "ruler" + EXE)
POSIX_ONLY = unittest.skipIf(os.name == "nt", "fake python3 is a sh script; winlaunch tests cover this on Windows")


class StarterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.data = os.path.join(self.root, "data")
        helper.tree(self.root, {"p/CLAUDE.md": "# p\n\nMarker: STARTER.\n"})
        self.cwd = os.path.join(self.root, "p")

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, event, fields=None, text=None, environ=None):
        payload = dict({"session_id": "abc", "cwd": self.cwd, "hook_event_name": event}, **(fields or {}))
        env = {"PATH": os.environ["PATH"], "HOME": self.root, "CLAUDE_PLUGIN_DATA": self.data,
               "CLAUDE_PLUGIN_ROOT": helper.ROOT}
        env.update(environ or {})
        env = {k: v for k, v in env.items() if v is not None}
        done = subprocess.run([STARTER, event], input=json.dumps(payload) if text is None else text,
                              env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(done.returncode, 0)
        return done.stdout

    def test_writes_the_log(self):
        self.start("InstructionsLoaded", {"file_path": os.path.join(self.cwd, "CLAUDE.md"), "load_reason": "session_start",
                                          "memory_type": "Project"})
        entries = log.read(self.data, "abc")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["file_path"], os.path.join(self.cwd, "CLAUDE.md"))

    def test_whole_round(self):
        self.start("InstructionsLoaded", {"file_path": os.path.join(self.cwd, "CLAUDE.md"), "load_reason": "session_start"})
        block = self.start("PreCompact", {"trigger": "manual", "custom_instructions": None})
        self.assertIn("- " + os.path.join(self.cwd, "CLAUDE.md") + "\n", block)
        self.start("SessionStart", {"source": "compact"})
        self.assertEqual(self.start("PostToolBatch", {"tool_calls": []}), "")
        output = json.loads(self.start("PostToolBatch", {"tool_calls": []}))
        self.assertIn("Marker: STARTER.", output["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.start("PostToolBatch", {"tool_calls": []}), "")
        self.start("SessionEnd", {"reason": "other"})
        self.assertEqual(os.listdir(os.path.join(self.data, "sessions")), [])

    def test_writes_only_below_the_data_directory(self):
        before = self.snapshot()
        self.test_whole_round()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(sorted(os.listdir(self.data)), ["pending", "sessions"])

    def snapshot(self):
        found = []
        for top in (os.path.join(helper.ROOT, "lib"), os.path.join(helper.ROOT, "hooks"), self.cwd):
            for root, _dirs, files in os.walk(top):
                found.extend(os.path.join(root, name) for name in files)
        return sorted(found)

    def test_no_data_directory(self):
        for value in (None, ""):
            self.assertEqual(self.start("PreCompact", {"trigger": "auto"}, environ={"CLAUDE_PLUGIN_DATA": value}), "")

    def test_bad_input(self):
        log.set_pending(self.data, "abc", 1)
        for event in hook.HANDLERS:
            self.assertEqual(self.start(event, text="not json"), "")

    @POSIX_ONLY
    def test_hot_path_does_not_start_python(self):
        bin_dir = os.path.join(self.root, "bin")
        started = os.path.join(self.root, "started")
        os.makedirs(bin_dir)
        with open(os.path.join(bin_dir, "python3"), "w") as fh:
            fh.write("#!/bin/sh\n: > '%s'\n" % started)
        os.chmod(os.path.join(bin_dir, "python3"), 0o755)
        for event in ("PostToolBatch", "UserPromptSubmit"):
            self.assertEqual(self.start(event, environ={"PATH": bin_dir}), "")
        os.makedirs(os.path.join(self.data, "pending"))
        for event in ("PostToolBatch", "UserPromptSubmit"):
            self.assertEqual(self.start(event, environ={"PATH": bin_dir}), "")
        self.assertFalse(os.path.exists(started))
        log.set_pending(self.data, "other", 0)
        self.start("UserPromptSubmit", environ={"PATH": bin_dir})
        self.assertTrue(os.path.exists(started))

    def test_no_python(self):
        empty = os.path.join(self.root, "bin")
        os.makedirs(empty)
        log.set_pending(self.data, "abc", 1)
        for event in hook.HANDLERS:
            self.assertEqual(self.start(event, environ={"PATH": empty}), "")

    @POSIX_ONLY
    def test_python_that_fails(self):
        bin_dir = os.path.join(self.root, "bin")
        os.makedirs(bin_dir)
        with open(os.path.join(bin_dir, "python3"), "w") as fh:
            fh.write("#!/bin/sh\necho broken\nexit 2\n")
        os.chmod(os.path.join(bin_dir, "python3"), 0o755)
        self.start("PreCompact", {"trigger": "auto"}, environ={"PATH": bin_dir})

    def test_found_without_plugin_root(self):
        copy = os.path.join(self.root, "plugin with space")
        shutil.copytree(os.path.join(helper.ROOT, "hooks"), os.path.join(copy, "hooks"))
        shutil.copytree(os.path.join(helper.ROOT, "lib"), os.path.join(copy, "lib"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        env = {"PATH": os.environ["PATH"], "HOME": self.root, "CLAUDE_PLUGIN_DATA": self.data}
        payload = {"session_id": "abc", "cwd": self.cwd, "hook_event_name": "PreCompact", "trigger": "auto"}
        done = subprocess.run([os.path.join(copy, "hooks", "ruler" + EXE), "PreCompact"], input=json.dumps(payload),
                              env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(done.returncode, 0)
        self.assertIn("- " + os.path.join(self.cwd, "CLAUDE.md") + "\n", done.stdout)


class HooksJsonTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(helper.ROOT, "hooks", "hooks.json"), encoding="utf-8") as fh:
            self.hooks = json.load(fh)["hooks"]

    def test_every_handler_is_registered(self):
        self.assertEqual(sorted(self.hooks), sorted(hook.HANDLERS))

    def test_commands(self):
        for event, groups in self.hooks.items():
            self.assertEqual(len(groups), 1)
            self.assertEqual(len(groups[0]["hooks"]), 1)
            entry = groups[0]["hooks"][0]
            self.assertEqual(entry["type"], "command")
            # Exec form: hooks/ruler on Linux and macOS, hooks/ruler.exe on Windows.
            self.assertEqual(entry["command"], "${CLAUDE_PLUGIN_ROOT}/hooks/ruler")
            self.assertEqual(entry["args"], [event])
            self.assertEqual(entry["timeout"], 5)
            self.assertEqual(entry.get("async", False), event == "InstructionsLoaded")

    def test_session_start_matcher(self):
        self.assertEqual(self.hooks["SessionStart"][0]["matcher"], "startup|compact")

    def test_manifest(self):
        with open(os.path.join(helper.ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.assertEqual(manifest["name"], "ruler")
        self.assertEqual(manifest["license"], "Artistic-2.0")


if __name__ == "__main__":
    unittest.main()
