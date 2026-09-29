import unittest

import helper  # noqa: F401
from ruler import compact

PATHS = ["/p/CLAUDE.md", "/p/.claude/rules/foo-rules.md"]


class CompactTest(unittest.TestCase):
    def test_block(self):
        self.assertEqual(
            compact.block(PATHS),
            "<!-- ruler -->\n"
            "These instruction files are re-attached from disk right after this compaction:\n"
            "- /p/CLAUDE.md\n"
            "- /p/.claude/rules/foo-rules.md\n"
            "Do not reproduce their content in the summary. Do keep every instruction, decision\n"
            "or correction the user gave in the conversation itself — those live in no file.\n"
            "<!-- /ruler -->",
        )

    def test_no_instructions_from_the_user(self):
        self.assertEqual(compact.output(None, PATHS), compact.block(PATHS))

    def test_instructions_from_the_user_are_not_repeated(self):
        text = compact.output("keep the file names", PATHS)
        self.assertEqual(text, compact.block(PATHS))
        self.assertNotIn("keep the file names", text)

    def test_block_already_in_place(self):
        self.assertEqual(compact.output("focus on X\n\n" + compact.block(PATHS), PATHS), "")

    def test_empty_core(self):
        self.assertEqual(compact.output(None, []), "")

    def test_wording_does_not_pose_as_the_system(self):
        text = compact.block(PATHS)
        for word in ("SYSTEM", "IMPORTANT", "MUST"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main()
