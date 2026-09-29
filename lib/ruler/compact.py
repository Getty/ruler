"""Instructions for the compaction summary.

Claude Code appends what a PreCompact hook prints to the instructions the user
gave to /compact, so ruler prints its block and never sees or replaces theirs.
"""

OPEN = "<!-- ruler -->"
CLOSE = "<!-- /ruler -->"


def block(paths):
    lines = [OPEN, "These instruction files are re-attached from disk right after this compaction:"]
    lines.extend("- " + path for path in paths)
    lines.append(
        "Do not reproduce their content in the summary. Do keep every instruction, decision"
    )
    lines.append(
        "or correction the user gave in the conversation itself — those live in no file."
    )
    lines.append(CLOSE)
    return "\n".join(lines)


def output(custom_instructions, paths):
    """What the hook prints: the block, or nothing if it is already in place."""
    if not paths:
        return ""
    if isinstance(custom_instructions, str) and OPEN in custom_instructions:
        return ""
    return block(paths)
