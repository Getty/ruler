import os
import tempfile
import unittest

import helper
from ruler import core

P = helper.PROJECT
R = helper.RECORDED


def loaded(path, reason, parent=None):
    entry = {"event": "loaded", "file_path": path, "load_reason": reason}
    if parent:
        entry["parent_file_path"] = parent
    return entry


class DeriveTest(unittest.TestCase):
    def test_startup(self):
        self.assertEqual(
            sorted(core.derive(helper.entries("startup"))),
            sorted(
                [
                    R + "/CLAUDE.md",
                    R + "/.claude/rules/parent-rule.md",
                    P + "/CLAUDE.md",
                    P + "/CLAUDE.local.md",
                    P + "/docs/imported.md",
                    P + "/.claude/rules/core-rule.md",
                    P + "/.claude/rules/deep/deep-rule.md",
                ]
            ),
        )

    def test_lazy_loads_are_never_core(self):
        for name in ("manual-compact", "auto-compact"):
            self.assertEqual(
                sorted(core.derive(helper.entries(name))),
                sorted([P + "/CLAUDE.md", P + "/docs/imported.md", P + "/.claude/rules/core-rule.md"]),
            )

    def test_include_recorded_before_its_parent(self):
        recorded = helper.entries("auto-compact")
        self.assertEqual(recorded[0]["load_reason"], "include")
        self.assertIn(P + "/docs/imported.md", core.derive(recorded))

    def test_include_chain(self):
        log = [
            loaded("/c.md", "include", "/b.md"),
            loaded("/b.md", "include", "/a.md"),
            loaded("/a.md", "session_start"),
        ]
        self.assertEqual(core.derive(log), ["/a.md", "/b.md", "/c.md"])

    def test_include_of_a_lazy_file(self):
        log = [
            loaded("/a.md", "session_start"),
            loaded("/sub/CLAUDE.md", "nested_traversal"),
            loaded("/sub/more.md", "include", "/sub/CLAUDE.md"),
            loaded("/rule.md", "path_glob_match"),
        ]
        self.assertEqual(core.derive(log), ["/a.md"])

    def test_compact_adds_a_file_created_during_the_session(self):
        log = [
            loaded("/a.md", "session_start"),
            {"event": "compact"},
            loaded("/a.md", "compact"),
            loaded("/new-rule.md", "compact"),
        ]
        self.assertEqual(core.derive(log), ["/a.md", "/new-rule.md"])

    def test_repeated_loads(self):
        recorded = helper.entries("resume-manual-compact")
        self.assertEqual(len(core.loads(recorded)), 6)
        self.assertEqual(len(core.derive(recorded)), 3)

    def test_other_entries(self):
        self.assertEqual(core.derive([{"event": "precompact"}, {"event": "loaded"}, {}]), [])


class DiscoverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        self.home = os.path.join(self.root, "home")
        os.makedirs(self.home)

    def tearDown(self):
        self.tmp.cleanup()

    def discover(self, cwd):
        found = core.discover(os.path.join(self.root, cwd), self.home)
        return [os.path.relpath(p, self.root) for p in found if p.startswith(self.root)]

    def test_matches_what_claude_code_loaded_at_session_start(self):
        helper.tree(os.path.join(self.root, "work"), helper.PROBE)
        reported = [os.path.relpath(p, R) for p in core.derive(helper.entries("startup"))]
        found = [os.path.relpath(p, "work") for p in self.discover("work/probe")]
        self.assertEqual(sorted(found), sorted(reported))

    def test_order(self):
        helper.tree(os.path.join(self.root, "work"), helper.PROBE)
        helper.tree(self.home, {".claude/CLAUDE.md": "user\n", ".claude/rules/mine.md": "mine\n"})
        self.assertEqual(
            self.discover("work/probe"),
            [
                "home/.claude/CLAUDE.md",
                "home/.claude/rules/mine.md",
                "work/CLAUDE.md",
                "work/.claude/rules/parent-rule.md",
                "work/probe/CLAUDE.md",
                "work/probe/docs/imported.md",
                "work/probe/.claude/rules/core-rule.md",
                "work/probe/.claude/rules/deep/deep-rule.md",
                "work/probe/CLAUDE.local.md",
            ],
        )

    def test_dot_claude_claude_md(self):
        helper.tree(self.root, {"p/.claude/CLAUDE.md": "x\n"})
        self.assertEqual(self.discover("p"), ["p/.claude/CLAUDE.md"])

    def test_session_in_the_home_directory(self):
        helper.tree(self.home, {".claude/CLAUDE.md": "user\n"})
        self.assertEqual(self.discover("home"), ["home/.claude/CLAUDE.md"])

    def test_imports(self):
        helper.tree(
            self.root,
            {
                "p/CLAUDE.md": "See @README for more and @docs/git.md.\n"
                "Not `@docs/span.md`, not mail@docs/mail.md, not @missing.md\n"
                "```\n@docs/fenced.md\n```\n"
                "- @~/mine.md\n- @" + os.path.join(self.root, "abs.md") + "\n",
                "p/README": "readme\n",
                "p/docs/git.md": "@more/deeper.md\n",
                "p/docs/more/deeper.md": "deeper\n",
                "p/docs/span.md": "x\n",
                "p/docs/mail.md": "x\n",
                "p/docs/fenced.md": "x\n",
                "home/mine.md": "x\n",
                "abs.md": "x\n",
            },
        )
        self.assertEqual(
            self.discover("p"),
            ["p/CLAUDE.md", "p/README", "p/docs/git.md", "p/docs/more/deeper.md", "home/mine.md", "abs.md"],
        )

    def test_import_depth(self):
        files = {"p/CLAUDE.md": "@1.md\n"}
        for hop in range(1, 7):
            files["p/%d.md" % hop] = "@%d.md\n" % (hop + 1)
        helper.tree(self.root, files)
        self.assertEqual(self.discover("p"), ["p/CLAUDE.md", "p/1.md", "p/2.md", "p/3.md", "p/4.md"])

    def test_import_cycle(self):
        helper.tree(self.root, {"p/CLAUDE.md": "@a.md\n", "p/a.md": "@CLAUDE.md\n@a.md\n"})
        self.assertEqual(self.discover("p"), ["p/CLAUDE.md", "p/a.md"])

    def test_rules_behind_a_symlink_cycle(self):
        helper.tree(self.root, {"p/.claude/rules/a.md": "a\n", "p/.claude/rules/notes.txt": "x\n"})
        os.symlink(os.path.join(self.root, "p/.claude/rules"), os.path.join(self.root, "p/.claude/rules/loop"))
        self.assertEqual(self.discover("p"), ["p/.claude/rules/a.md"])

    def test_nothing_there(self):
        self.assertEqual(self.discover("nowhere"), [])


class FrontmatterTest(unittest.TestCase):
    def test_has_paths(self):
        self.assertTrue(core.has_paths('---\npaths:\n  - "src/**"\n---\nbody\n'))
        self.assertTrue(core.has_paths('---\ndescription: x\npaths: "a, b"\n---\nbody\n'))
        self.assertFalse(core.has_paths("---\ndescription: x\n---\npaths: no\n"))
        self.assertFalse(core.has_paths("paths: no\n"))
        self.assertFalse(core.has_paths("---\npaths: never closed\n"))
        self.assertFalse(core.has_paths(""))

    def test_split(self):
        self.assertEqual(core.split_frontmatter("---\na: b\n---\n\nbody\n"), ("a: b", "body\n"))
        self.assertEqual(core.split_frontmatter("body\n---\n"), (None, "body\n---\n"))


class OfTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self.tmp.name)
        helper.tree(self.root, {"p/CLAUDE.md": "x\n", "p/.claude/rules/r.md": "r\n"})
        self.cwd = os.path.join(self.root, "p")

    def tearDown(self):
        self.tmp.cleanup()

    def test_log_with_session_start_wins(self):
        log = [loaded("/a.md", "session_start")]
        self.assertEqual(core.of(log, self.cwd, self.root), ["/a.md"])

    def test_empty_log_falls_back_to_disk(self):
        self.assertEqual(
            core.of([], self.cwd, self.root),
            [self.cwd + "/CLAUDE.md", self.cwd + "/.claude/rules/r.md"],
        )

    def test_log_without_session_start_is_completed_from_disk(self):
        log = [{"event": "compact"}, loaded(self.cwd + "/CLAUDE.md", "compact"), loaded("/new.md", "compact")]
        self.assertEqual(
            core.of(log, self.cwd, self.root),
            [self.cwd + "/CLAUDE.md", self.cwd + "/.claude/rules/r.md", "/new.md"],
        )

    def test_no_cwd(self):
        self.assertEqual(core.of([], None, self.root), [])


if __name__ == "__main__":
    unittest.main()
