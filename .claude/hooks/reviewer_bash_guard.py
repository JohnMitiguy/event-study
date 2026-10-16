"""PreToolUse hook for the methodology-reviewer subagent: allow only a few read-only commands.

Claude Code runs this before every Bash call the reviewer makes and sends the
tool call as JSON on stdin. Exit 0 lets the command run; exit 2 blocks it and
shows the message on stderr to the reviewer.

Allowed: git log, git diff, git status, uv run pytest and uv run ruff check,
each with only the flags listed in ALLOWED. Everything else is blocked: other
commands, other flags, chaining, pipes, redirects and substitution. Because
this is an allowlist, flags like --fix-only, --config, --override-ini, --debug
and --pastebin are blocked without being named.

Assumptions:
- Commands with none of BLOCKED_CHARS in them are split into words by
  shlex.split the same way bash splits them.
- Short flags are matched whole, so combined flags like -qx are blocked;
  write -q -x.
- A flag that takes a value takes it as --flag=value (long flags only) or as
  the next word. The value may not start with "-", so a blocked flag can't
  hide as a value.
- pytest file arguments must be under tests/ with no "..", because pytest
  imports and runs any .py file it is given.
- If this script crashes, it blocks (fails closed). If it can't start at all
  (uv or Python missing), Claude Code lets the command run: the hook is a
  backstop and fails open.

Tests: tests/test_reviewer_hook.py.
"""

import json
import shlex
import sys

BLOCKED_CHARS = ";&|<>`$()\n\r"

PYTEST = ("uv", "run", "pytest")

# For each allowed command: flag -> True if the flag takes a value.
# "--" means the command accepts "--", after which every word is a file argument.
ALLOWED = {
    ("git", "log"): {
        "--oneline": False,
        "--stat": False,
        "--name-only": False,
        "--name-status": False,
        "-p": False,
        "--patch": False,
        "-n": True,
        "--max-count": True,
        "--format": True,
        "--pretty": True,
        "--since": True,
        "--until": True,
        "--follow": False,
        "--": False,
    },
    ("git", "diff"): {
        "--stat": False,
        "--name-only": False,
        "--name-status": False,
        "--cached": False,
        "--staged": False,
        "-U": True,
        "--unified": True,
        "--": False,
    },
    ("git", "status"): {
        "-s": False,
        "--short": False,
        "--porcelain": False,
        "-b": False,
        "--branch": False,
    },
    PYTEST: {
        "-q": False,
        "-v": False,
        "-x": False,
        "-k": True,
        "--tb": True,
        "--": False,
    },
    ("uv", "run", "ruff", "check"): {
        "-q": False,
        "--quiet": False,
        "--statistics": False,
        "--output-format": True,
        "--select": True,
    },
}


class Blocked(Exception):
    """The command is not allowed; the message says why."""


def read_command(raw: bytes) -> str:
    """The Bash command from the hook's JSON input, or Blocked if it isn't there."""
    try:
        command = json.loads(raw)["tool_input"]["command"]
    except (ValueError, KeyError, TypeError):
        raise Blocked("could not read the command") from None
    if not isinstance(command, str):
        raise Blocked("could not read the command")
    return command


def check(command: str) -> None:
    """Raise Blocked if command is not one of the allowed commands with allowed flags."""
    if any(ch in command for ch in BLOCKED_CHARS):
        raise Blocked("no chaining, pipes, redirects or substitution")
    try:
        words = shlex.split(command)
    except ValueError:
        raise Blocked("could not parse the command") from None
    for prefix in ALLOWED:
        if tuple(words[: len(prefix)]) == prefix:
            check_args(prefix, words[len(prefix) :])
            return
    raise Blocked("command not on the list")


def check_args(prefix: tuple[str, ...], args: list[str]) -> None:
    """Raise Blocked if any word after the command is a flag or file argument it may not take."""
    flags = ALLOWED[prefix]
    i = 0
    while i < len(args):
        word = args[i]
        if word == "--" and "--" in flags:
            for path in args[i + 1 :]:
                check_file_arg(prefix, path)
            return
        if word.startswith("-"):
            i = check_flag(prefix, args, i)
        else:
            check_file_arg(prefix, word)
        i += 1


def check_flag(prefix: tuple[str, ...], args: list[str], i: int) -> int:
    """Check the flag at args[i]; return the index of its last word (i, or i + 1 if it took the next word)."""
    flags = ALLOWED[prefix]
    word = args[i]
    # Only long flags split on "=": pytest reads -k=foo as -k with the value "=foo".
    if word.startswith("--"):
        name, eq, value = word.partition("=")
    else:
        name, eq, value = word, "", ""
    if name not in flags:
        allowed = ", ".join(f for f in flags if f != "--") or "none"
        raise Blocked(f"flag {word} is not allowed for {' '.join(prefix)} (allowed flags: {allowed})")
    takes_value = flags[name]
    if eq and not takes_value:
        raise Blocked(f"flag {name} does not take a value")
    if takes_value and not eq:
        i += 1
        if i >= len(args):
            raise Blocked(f"flag {name} needs a value")
        value = args[i]
    if takes_value and value.startswith("-"):
        raise Blocked(f"the value of {name} may not start with '-' ({value})")
    return i


def check_file_arg(prefix: tuple[str, ...], word: str) -> None:
    """Raise Blocked if a pytest file argument is outside tests/. Other commands take any."""
    if prefix != PYTEST:
        return
    # tests/test_x.py::test_name -> tests/test_x.py
    parts = word.split("::")[0].split("/")
    if parts[0] != "tests" or ".." in parts:
        raise Blocked(f"pytest file arguments must be under tests/ ({word})")


def block(why: str) -> None:
    print(
        f"Blocked for methodology-reviewer: {why}. Allowed: git log, git diff, git status, "
        "uv run pytest, uv run ruff check, one at a time from the project root, with only "
        "their listed flags.",
        file=sys.stderr,
    )
    sys.exit(2)


def main() -> None:
    try:
        check(read_command(sys.stdin.buffer.read()))
    except Blocked as err:
        block(str(err))
    except Exception as err:  # noqa: BLE001 -- a crash must block, not let the command through.
        block(f"the hook crashed ({err!r})")


if __name__ == "__main__":
    main()
