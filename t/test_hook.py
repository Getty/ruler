import io
import json
import os
import tempfile
import unittest

import helper
from ruler import compact, hook, log

SESSION = {
    "manual-compact": "44444444-4444-4444-8444-444444444444",
    "auto-compact": "77777777-7777-4777-8777-777777777777",
}


class HookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.data = os.path.join(self.root, "data")
        self.home = os.path.join(self.root, "home")
        self.work = os.path.join(self.root, "work")
        self.project = os.path.join(self.work, "probe")
        os.makedirs(self.home)
        files = dict(helper.PROBE)
        # The compaction fixtures were recorded before these files existed.
        for name in ("CLAUDE.md", ".claude/rules/parent-rule.md", "probe/CLAUDE.local.md",
                     "probe/.claude/rules/deep/deep-rule.md", "probe/.claude/rules/scoped-two.md"):
            del files[name]
        helper.tree(self.work, files)
        self.grace, hook.GRACE = hook.GRACE, 0.2

    def tearDown(self):
        hook.GRACE = self.grace
        self.tmp.cleanup()

    def core(self):
        return [
            self.project + "/CLAUDE.md",
            self.project + "/docs/imported.md",
            self.project + "/.claude/rules/core-rule.md",
        ]

    def replay(self, name, drop=None, until=None):
        sequence = helper.payloads(name, self.work)
        if drop:
            sequence = [p for p in sequence if not drop(p)]
        if until:
            sequence = sequence[: [until(p) for p in sequence].index(True)]
        return helper.replay(sequence, self.data, self.home)

    def context(self, printed, event):
        self.assertEqual([name for name, _ in printed], ["PreCompact", event])
        output = json.loads(printed[1][1])
        self.assertEqual(list(output), ["hookSpecificOutput"])
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], event)
        return output["hookSpecificOutput"]["additionalContext"]


class RecordedSessionTest(HookTest):
    def test_pre_compact_names_the_core(self):
        for name in SESSION:
            printed = self.replay(name)
            self.assertEqual(printed[0][0], "PreCompact")
            self.assertEqual(sorted(printed[0][1].split("\n")[2:5]), sorted("- " + p for p in self.core()))
            self.assertTrue(printed[0][1].startswith(compact.OPEN + "\n"))
            self.assertTrue(printed[0][1].endswith(compact.CLOSE + "\n"))

    def test_nothing_is_attached_when_everything_came_back(self):
        for name in SESSION:
            self.assertEqual([event for event, _ in self.replay(name)], ["PreCompact"])

    def test_session_end_leaves_nothing_behind(self):
        for name in SESSION:
            self.replay(name)
            self.assertEqual(os.listdir(os.path.join(self.data, "sessions")), [])
            self.assertEqual(os.listdir(os.path.join(self.data, "pending")), [])

    def test_log_before_session_end(self):
        self.replay("auto-compact", until=lambda p: p["hook_event_name"] == "SessionEnd")
        entries = log.read(self.data, SESSION["auto-compact"])
        self.assertEqual(
            [e["event"] for e in entries],
            ["loaded"] * 3 + ["precompact", "compact"] + ["loaded"] * 5,
        )
        self.assertEqual(entries[3]["trigger"], "auto")
        self.assertIsNone(log.get_pending(self.data, SESSION["auto-compact"]))

    def test_first_batch_after_a_compaction_only_moves_the_marker(self):
        batches = []

        def second_batch(payload):
            batches.append(payload["hook_event_name"] == "PostToolBatch")
            return sum(batches) == 5

        printed = self.replay("auto-compact", until=second_batch)
        self.assertEqual([event for event, _ in printed], ["PreCompact"])
        self.assertEqual(log.get_pending(self.data, SESSION["auto-compact"]), 1)

    def test_rule_missing_after_auto_compaction(self):
        printed = self.replay(
            "auto-compact",
            drop=lambda p: p.get("load_reason") == "compact" and p["file_path"].endswith("core-rule.md"),
        )
        self.assertEqual(
            self.context(printed, "PostToolBatch"),
            "Project instructions from %s/.claude/rules/core-rule.md "
            "(re-attached by ruler after compaction):\n\n"
            "# core rule\n\nRule without paths. Marker: CORE-RULE-CHARLIE." % self.project,
        )

    def test_everything_missing_after_auto_compaction(self):
        printed = self.replay(
            "auto-compact",
            drop=lambda p: p.get("load_reason") in ("compact", "include") and "prompt_id" in p,
        )
        context = self.context(printed, "PostToolBatch")
        for marker in ("CORE-ROOT-ALPHA", "CORE-IMPORT-BRAVO", "CORE-RULE-CHARLIE"):
            self.assertEqual(context.count(marker), 1)
        for marker in ("SCOPED-RULE-DELTA", "NESTED-ECHO"):
            self.assertNotIn(marker, context)

    def test_import_missing_after_manual_compaction(self):
        seen = []

        def second_include(payload):
            seen.append(payload.get("load_reason") == "include")
            return seen[-1] and sum(seen) == 2

        printed = self.replay("manual-compact", drop=second_include)
        self.assertEqual(
            self.context(printed, "UserPromptSubmit"),
            "Project instructions from %s/docs/imported.md "
            "(re-attached by ruler after compaction):\n\n"
            "# imported\n\nImported from CLAUDE.md. Marker: CORE-IMPORT-BRAVO." % self.project,
        )

    def test_attached_once(self):
        printed = self.replay("manual-compact", drop=lambda p: p.get("load_reason") == "compact")
        self.assertEqual([event for event, _ in printed], ["PreCompact", "UserPromptSubmit"])

    def test_changed_file_is_attached_as_it_is_now(self):
        helper.tree(self.project, {"CLAUDE.md": "changed during the session\n"})
        printed = self.replay(
            "manual-compact",
            drop=lambda p: p.get("load_reason") == "compact" and p["file_path"].endswith("probe/CLAUDE.md"),
        )
        self.assertTrue(self.context(printed, "UserPromptSubmit").endswith("\n\nchanged during the session"))

    def test_deleted_file_is_skipped(self):
        os.remove(self.project + "/.claude/rules/core-rule.md")
        printed = self.replay("manual-compact", drop=lambda p: p.get("load_reason") == "compact")
        context = self.context(printed, "UserPromptSubmit")
        self.assertIn("CORE-ROOT-ALPHA", context)
        self.assertNotIn("core-rule.md", context)

    def test_installed_in_the_middle_of_a_session(self):
        printed = self.replay(
            "manual-compact",
            drop=lambda p: p.get("load_reason") in ("session_start", "include") or (
                p.get("load_reason") == "compact" and p["file_path"].endswith("core-rule.md")
            ),
        )
        self.assertEqual(sorted(printed[0][1].split("\n")[2:5]), sorted("- " + p for p in self.core()))
        context = self.context(printed, "UserPromptSubmit")
        self.assertIn("CORE-RULE-CHARLIE", context)
        self.assertIn("CORE-IMPORT-BRAVO", context)
        self.assertNotIn("CORE-ROOT-ALPHA", context)

    def test_resumed_session(self):
        printed = self.replay("resume-manual-compact")
        self.assertEqual([event for event, _ in printed], ["PreCompact"])
        self.assertNotIn("keep the file names", printed[0][1])


class SingleHookTest(HookTest):
    sid = "abc"

    def payload(self, event, **fields):
        return dict({"session_id": self.sid, "cwd": self.project, "hook_event_name": event}, **fields)

    def run_hook(self, event, **fields):
        return helper.run(self.payload(event, **fields), self.data, self.home)

    def test_compaction_that_did_not_happen(self):
        self.run_hook("InstructionsLoaded", file_path=self.core()[0], load_reason="session_start")
        self.assertNotEqual(self.run_hook("PreCompact", trigger="manual", custom_instructions=None), "")
        self.assertIsNone(log.get_pending(self.data, self.sid))
        self.assertEqual(self.run_hook("UserPromptSubmit", prompt="x"), "")

    def test_first_prompt_after_a_compaction_only_moves_the_marker(self):
        # Interactive, Claude Code 2.1.285: the reloaded files are reported only after
        # the UserPromptSubmit hook has returned, so checking there always runs into the wait.
        self.run_hook("SessionStart", source="compact")
        self.assertEqual(log.get_pending(self.data, self.sid), 0)
        self.assertEqual(self.run_hook("UserPromptSubmit", prompt="x"), "")
        self.assertEqual(log.get_pending(self.data, self.sid), 1)
        context = json.loads(self.run_hook("UserPromptSubmit", prompt="y"))["hookSpecificOutput"]
        self.assertIn("CORE-ROOT-ALPHA", context["additionalContext"])
        self.assertIsNone(log.get_pending(self.data, self.sid))

    def test_prompt_then_batch_checks_at_the_batch(self):
        self.run_hook("SessionStart", source="compact")
        self.assertEqual(self.run_hook("UserPromptSubmit", prompt="x"), "")
        output = json.loads(self.run_hook("PostToolBatch", tool_calls=[]))
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "PostToolBatch")

    def test_unreadable_log_attaches_the_whole_core(self):
        os.makedirs(log.log_path(self.data, self.sid))
        log.set_pending(self.data, self.sid, 1)
        output = json.loads(self.run_hook("PostToolBatch", tool_calls=[]))
        context = output["hookSpecificOutput"]["additionalContext"]
        for marker in ("CORE-ROOT-ALPHA", "CORE-IMPORT-BRAVO", "CORE-RULE-CHARLIE"):
            self.assertEqual(context.count(marker), 1)
        self.assertIsNone(log.get_pending(self.data, self.sid))

    def test_unreadable_log_and_no_core(self):
        os.makedirs(log.log_path(self.data, self.sid))
        log.set_pending(self.data, self.sid, 1)
        self.assertEqual(self.run_hook("UserPromptSubmit", cwd=self.home), "")

    def test_pre_compact_with_an_empty_core(self):
        self.assertEqual(self.run_hook("PreCompact", trigger="auto", custom_instructions=None, cwd=self.home), "")

    def test_pre_compact_with_the_block_in_place(self):
        block = compact.block(self.core())
        self.assertEqual(self.run_hook("PreCompact", trigger="manual", custom_instructions=block), "")

    def test_subagent_is_ignored(self):
        self.run_hook("InstructionsLoaded", file_path="/a.md", load_reason="session_start", agent_id="a1")
        self.run_hook("SessionStart", source="compact", agent_id="a1")
        self.assertFalse(os.path.exists(self.data))

    def test_event_named_by_the_starter_only(self):
        log.set_pending(self.data, self.sid, 1)
        payload = {"session_id": self.sid, "cwd": self.project}
        out = io.StringIO()
        environ = {"CLAUDE_PLUGIN_DATA": self.data, "HOME": self.home}
        self.assertEqual(hook.main(["UserPromptSubmit"], io.StringIO(json.dumps(payload)), out, environ), 0)
        output = json.loads(out.getvalue())["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "UserPromptSubmit")
        self.assertIn("CORE-ROOT-ALPHA", output["additionalContext"])

    def test_session_of_another_pending_marker(self):
        log.set_pending(self.data, "other", 0)
        self.assertEqual(self.run_hook("UserPromptSubmit", prompt="x"), "")
        self.assertEqual(log.get_pending(self.data, "other"), 0)

    def test_startup_prunes(self):
        log.append(self.data, "old", {"event": "compact"})
        path = log.log_path(self.data, "old")
        os.utime(path, (0, 0))
        self.run_hook("SessionStart", source="startup")
        self.assertFalse(os.path.exists(path))

    def test_resume_and_clear_do_nothing(self):
        for source in ("resume", "clear", "fork"):
            self.assertEqual(self.run_hook("SessionStart", source=source), "")
        self.assertFalse(os.path.exists(self.data))


class FailOpenTest(HookTest):
    def test_bad_input(self):
        for text in ("", "not json", "[1, 2]", '"text"', "{}", '{"hook_event_name": "PreCompact"}',
                     '{"hook_event_name": "PreCompact", "session_id": "../../x"}',
                     '{"hook_event_name": "Unknown", "session_id": "abc"}',
                     '{"hook_event_name": "PostToolBatch", "session_id": "abc"}',
                     '{"hook_event_name": "InstructionsLoaded", "session_id": "abc"}'):
            self.assertEqual(helper.run(text, self.data, self.home), "")
        self.assertFalse(os.path.exists(os.path.join(self.data, "sessions")))

    def test_no_data_directory(self):
        for environ in ({}, {"CLAUDE_PLUGIN_DATA": ""}):
            out = io.StringIO()
            text = json.dumps({"hook_event_name": "PreCompact", "session_id": "abc", "cwd": self.project})
            self.assertEqual(hook.main([], io.StringIO(text), out, environ), 0)
            self.assertEqual(out.getvalue(), "")

    def test_data_directory_that_cannot_be_written(self):
        blocked = os.path.join(self.root, "blocked")
        with open(blocked, "w") as fh:
            fh.write("a file, not a directory\n")
        for event, fields in (
            ("InstructionsLoaded", {"file_path": "/a.md", "load_reason": "session_start"}),
            ("SessionStart", {"source": "compact"}),
            ("SessionStart", {"source": "startup"}),
            ("UserPromptSubmit", {}),
            ("PostToolBatch", {}),
            ("SessionEnd", {}),
        ):
            payload = dict({"session_id": "abc", "cwd": self.project, "hook_event_name": event}, **fields)
            self.assertEqual(helper.run(payload, blocked, self.home), "")

    def test_pre_compact_still_speaks_without_a_writable_log(self):
        blocked = os.path.join(self.root, "blocked")
        with open(blocked, "w") as fh:
            fh.write("a file, not a directory\n")
        payload = {"session_id": "abc", "cwd": self.project, "hook_event_name": "PreCompact",
                   "trigger": "auto", "custom_instructions": None}
        self.assertIn("- " + self.core()[0], helper.run(payload, blocked, self.home))

    def test_stdin_that_fails(self):
        class Broken:
            def read(self):
                raise OSError("gone")

        self.assertEqual(hook.main([], Broken(), None, {"CLAUDE_PLUGIN_DATA": self.data}), 0)


if __name__ == "__main__":
    unittest.main()
