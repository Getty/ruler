import os
import tempfile
import unittest

import helper
from ruler import core, restore

P = helper.PROJECT
CORE = [P + "/CLAUDE.md", P + "/docs/imported.md", P + "/.claude/rules/core-rule.md"]


def cut(entries, keep):
    """The log up to the last compaction, plus the first loads after it."""
    last = max(i for i, e in enumerate(entries) if e.get("event") == "compact")
    return entries[: last + 1 + keep]


class MissingTest(unittest.TestCase):
    def test_everything_came_back(self):
        for name in ("manual-compact", "auto-compact"):
            recorded = helper.entries(name)
            self.assertEqual(restore.missing(recorded, core.derive(recorded)), [])

    def test_imports_come_back_as_include(self):
        recorded = helper.entries("manual-compact")
        last = max(i for i, e in enumerate(recorded) if e.get("event") == "compact")
        reasons = {e["file_path"]: e["load_reason"] for e in recorded[last + 1:]}
        self.assertEqual(reasons[P + "/docs/imported.md"], "include")
        self.assertEqual(reasons[P + "/CLAUDE.md"], "compact")

    def test_nothing_came_back(self):
        recorded = cut(helper.entries("manual-compact"), 0)
        self.assertEqual(sorted(restore.missing(recorded, CORE)), sorted(CORE))

    def test_one_file_did_not_come_back(self):
        recorded = [
            e for e in helper.entries("auto-compact")
            if not (e.get("load_reason") == "compact" and e["file_path"].endswith("core-rule.md"))
        ]
        self.assertEqual(restore.missing(recorded, core.derive(recorded)), [P + "/.claude/rules/core-rule.md"])

    def test_loads_before_the_compaction_do_not_count(self):
        recorded = helper.entries("auto-compact")
        first = min(i for i, e in enumerate(recorded) if e.get("event") == "compact")
        self.assertEqual(sorted(restore.missing(recorded[: first + 1], CORE)), sorted(CORE))

    def test_only_the_last_compaction_counts(self):
        log = [
            {"event": "loaded", "file_path": "/a.md", "load_reason": "session_start"},
            {"event": "compact"},
            {"event": "loaded", "file_path": "/a.md", "load_reason": "compact"},
            {"event": "compact"},
        ]
        self.assertEqual(restore.missing(log, ["/a.md"]), ["/a.md"])

    def test_no_compaction(self):
        recorded = helper.entries("startup")
        self.assertEqual(restore.missing(recorded, core.derive(recorded)), [])


class BuildTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, content):
        helper.tree(self.root, {name: content})
        return os.path.join(self.root, name)

    def test_format(self):
        a = self.write("CLAUDE.md", "# probe\n\nMarker.\n")
        b = self.write("rule.md", "rule\n")
        self.assertEqual(
            restore.build([a, b]),
            "Project instructions from %s (re-attached by ruler after compaction):\n\n# probe\n\nMarker.\n\n"
            "Project instructions from %s (re-attached by ruler after compaction):\n\nrule" % (a, b),
        )

    def test_read_fresh_from_disk(self):
        a = self.write("CLAUDE.md", "old\n")
        self.write("CLAUDE.md", "new\n")
        self.assertTrue(restore.build([a]).endswith("\n\nnew"))

    def test_deleted_file_is_skipped(self):
        a = self.write("CLAUDE.md", "here\n")
        gone = os.path.join(self.root, "gone.md")
        self.assertEqual(restore.build([gone, a]), restore.render(a, "here"))
        self.assertEqual(restore.build([gone]), "")

    def test_frontmatter_is_left_out(self):
        a = self.write("rule.md", "---\ndescription: x\n---\n\nbody\n")
        self.assertEqual(restore.build([a]), restore.render(a, "body"))

    def test_nothing_missing(self):
        self.assertEqual(restore.build([]), "")

    def test_whole_files_while_they_fit(self):
        a = self.write("a.md", "a" * 4000)
        b = self.write("b.md", "b" * 4000)
        c = self.write("c.md", "c" * 4000)
        d = self.write("d.md", "d\n")
        context = restore.build([a, b, c, d])
        self.assertLessEqual(restore.size(context), restore.LIMIT)
        self.assertIn("a" * 4000, context)
        self.assertIn("b" * 4000, context)
        self.assertNotIn("ccc", context)
        self.assertTrue(
            context.endswith("Read these files now before continuing:\n- %s\n- %s" % (c, d))
        )

    def test_a_file_larger_than_the_limit(self):
        a = self.write("a.md", "a" * 20000)
        self.assertEqual(restore.build([a]), restore.REST + "\n- " + a)

    def test_limit_counts_utf16_units(self):
        self.assertEqual(restore.size("aä\U0001f600"), 4)
        a = self.write("a.md", "\U0001f600" * 4990)
        self.assertLessEqual(restore.size(restore.build([a])), restore.LIMIT)
        self.assertNotIn("\U0001f600", restore.build([a]))

    def test_limit_holds_for_the_list_of_names(self):
        paths = [self.write("%s/%03d.md" % ("d" * 100, n), "x" * 9000) for n in range(200)]
        context = restore.build(paths)
        self.assertLessEqual(restore.size(context), restore.LIMIT)
        self.assertIn(paths[0], context)


if __name__ == "__main__":
    unittest.main()
