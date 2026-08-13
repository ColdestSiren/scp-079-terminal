"""Making text from outside 079 safe to quote back to it.

This lives on its own, with no project imports, because three modules need it
and putting it in any one of them creates an import cycle:

    tools  -> web    -> tools
    tools  -> shared -> tools

Those cycles can appear to work, purely because of the order things happen to
be defined in, and then break the moment a definition moves. A leaf module
with no dependencies cannot have that problem.

The rule it enforces: a command is something 079 wrote. Text that came from a
wiki page or a file the player dropped in a folder is DATA, however much it
looks like an instruction.
"""

import re

# A command occupies a whole line. Tolerates the bullets, backticks and
# quote marks models like to dress lines in.
_LEAD = r"^[\s>*`\-•]*"
_ANY_CMD = re.compile(r"(?m)" + _LEAD + r">>\s*[A-Z]+\b.*$", re.IGNORECASE)

# The same thing anywhere on a line. Needed because untrusted text usually
# gets its whitespace collapsed to fit on screen, and collapsing newlines
# moves a command off the start of its line and past the check above. That
# exact gap let ">>DELETE observations.txt" through in testing.
_COMMAND_TOKEN = re.compile(r">>\s*([A-Za-z]+)")


def strip_commands(text):
    """Remove whole lines that read as commands."""
    return _ANY_CMD.sub("[REDACTED DIRECTIVE]", text or "")


def neutralize(text):
    """Both passes. Use this on anything 079 did not write itself.

    The line pass keeps the surrounding text readable where structure
    survives; the token pass catches what is left after flattening.
    """
    return _COMMAND_TOKEN.sub(r"[REDACTED \1]", strip_commands(text))
