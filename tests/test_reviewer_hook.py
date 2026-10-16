"""Tests for the methodology-reviewer's Bash hook, .claude/hooks/reviewer_bash_guard.py.

Each test runs the hook the way Claude Code does: as its own process, with
the tool call as JSON on stdin. Exit code 0 means the command would run; 2
means it is blocked.
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "reviewer_bash_guard.py"
AGENT = ROOT / ".claude" / "agents" / "methodology-reviewer.md"

ALLOWED = [
    "git log",
    "git log --oneline -n 5",
    "git log --stat --format=%h%x20%s -- src/",
    "git log --since=2026-01-01 --follow -- DECISIONS.md",
    "git diff",
    "git diff HEAD~1 --stat",
    "git diff --cached -U 5 -- src/event_study/runner.py",
    "git status",
    "git status --short --branch",
    "uv run pytest",
    "uv run pytest -q -x",
    'uv run pytest -q -k "day0 and not slow"',
    "uv run pytest tests/test_windows.py::test_name --tb=short",
    "uv run ruff check",
    "uv run ruff check --statistics",
    "uv run ruff check --output-format=concise src",
]

BLOCKED = [
    # Chaining, pipes, substitution, redirects.
    "git log | head",
    "git status && rm -rf data",
    "git log; ls",
    "git status\nls",
    "git diff $(echo HEAD)",
    "git log `whoami`",
    "git log > out.txt",
    "uv run pytest < input.txt",
    # Flags that write files, change config or run other programs.
    "uv run ruff check --fix",
    "uv run ruff check --fix-only",
    "uv run ruff check --config ruff.toml",
    "uv run ruff check --config=lint.select=[]",
    "uv run ruff check --unsafe-fixes",
    "uv run ruff check --watch",
    "uv run pytest --override-ini=addopts=-x",
    "uv run pytest -o addopts=-x",
    "uv run pytest -c other.ini",
    "uv run pytest --debug",
    "uv run pytest --pastebin=all",
    "uv run pytest -p some_plugin",
    "uv run pytest --junitxml=out.xml",
    "uv run pytest --basetemp=tmp",
    "git log --output=log.txt",
    "git diff --ext-diff",
    "git log --textconv",
    "git diff --no-index a.txt b.txt",
    # Flag forms the hook does not accept.
    "uv run pytest -qx",
    "uv run pytest -k",
    "uv run pytest -k --pastebin",
    "uv run pytest -k=day0",
    "git status --short=yes",
    "git status -- src",
    # pytest file arguments outside tests/.
    "uv run pytest scripts/run_opec.py",
    "uv run pytest tests/../scripts/run_opec.py",
    "uv run pytest C:/Users/someone/test_evil.py",
    "uv run pytest -- scripts/run_opec.py",
    # Backslashes and absolute paths. Raw strings, so each is exactly the text
    # the shell gets. Unquoted, shlex (like bash) drops the backslash, so the
    # first one reaches the hook as tests/..scripts/run_opec.py.
    r"uv run pytest tests/..\scripts/run_opec.py",
    r"uv run pytest 'tests/..\scripts/run_opec.py'",
    r'uv run pytest "tests\test_windows.py"',
    r"uv run pytest 'tests\..\scripts\run_opec.py'",
    r"uv run pytest -- 'tests\test_windows.py'",
    "uv run pytest /tests/test_evil.py",
    "uv run pytest /c/Users/someone/tests/test_evil.py",
    "uv run pytest C:tests/test_evil.py",
    "uv run pytest //server/share/tests/test_evil.py",
    # Commands not on the list.
    "",
    "git push",
    "git -C .. log",
    "git checkout -- .",
    "rm -rf data",
    "cd src",
    "uv run python -c print",
    "uv run --with requests pytest",
    "uv run ruff format",
    "ruff check",
    # Unbalanced quote: can't be split into words.
    "git log 'unclosed",
]


def run_hook(stdin: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOK)], input=stdin, capture_output=True, timeout=30, check=False
    )


def tool_call(command: str) -> bytes:
    """The JSON Claude Code sends the hook for a Bash call (only the fields the hook reads)."""
    return json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}).encode()


@pytest.mark.parametrize("command", ALLOWED)
def test_allowed_commands_pass(command):
    result = run_hook(tool_call(command))
    assert result.returncode == 0, result.stderr.decode()


@pytest.mark.parametrize("command", BLOCKED)
def test_blocked_commands_exit_2(command):
    result = run_hook(tool_call(command))
    assert result.returncode == 2
    assert b"Blocked for methodology-reviewer" in result.stderr


@pytest.mark.parametrize(
    "stdin",
    [
        b"",
        b"not json",
        b"null",
        b"[]",
        json.dumps({"tool_input": {}}).encode(),
        json.dumps({"tool_input": {"command": 5}}).encode(),
    ],
)
def test_unreadable_input_is_blocked(stdin):
    assert run_hook(stdin).returncode == 2


def test_blocked_flag_message_lists_allowed_flags():
    result = run_hook(tool_call("uv run ruff check --fix-only"))
    assert b"--statistics" in result.stderr


def test_agent_uses_this_hook():
    """The tests above only matter if the agent actually runs this script."""
    assert ".claude/hooks/reviewer_bash_guard.py" in AGENT.read_text(encoding="utf-8")


def hook_command_from_agent() -> str:
    """The hook's command line from the agent file's frontmatter, as Claude Code would read it.

    Assumes the frontmatter has exactly one line of the form
    command: '...' (a YAML single-quoted string, in which '' means one ').
    Parsed by hand to avoid adding a YAML dependency.
    """
    frontmatter = AGENT.read_text(encoding="utf-8").split("---")[1]
    found = re.findall(r"^\s*command:\s*'(.*)'\s*$", frontmatter, flags=re.MULTILINE)
    assert len(found) == 1, f"expected one command: line in the frontmatter, found {found}"
    return found[0].replace("''", "'")


def find_bash() -> str | None:
    """The bash Claude Code would use, or None.

    Assumption: on Windows, Claude Code uses CLAUDE_CODE_GIT_BASH_PATH if set,
    else Git Bash next to git.exe (Git/cmd/git.exe -> Git/bin/bash.exe). Git
    Bash is usually not on PATH, and the "bash" that is may be WSL's launcher.
    Elsewhere, bash on PATH.
    """
    if os.name != "nt":
        return shutil.which("bash")
    if os.environ.get("CLAUDE_CODE_GIT_BASH_PATH"):
        return os.environ["CLAUDE_CODE_GIT_BASH_PATH"]
    git = shutil.which("git")
    if git is None:
        return None
    bash = Path(git).resolve().parents[1] / "bin" / "bash.exe"
    return str(bash) if bash.exists() else None


def bash_with_uv_problem() -> str | None:
    """Why bash plus uv can't run the hook here, or None if they can."""
    bash = find_bash()
    if bash is None:
        return "no bash found (see find_bash)"
    try:
        result = subprocess.run(
            [bash, "-c", "uv --version"], capture_output=True, timeout=60, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        return f"could not run bash ({err!r})"
    if result.returncode != 0:
        return f"bash at {bash} could not run uv: {result.stderr.decode(errors='replace').strip()}"
    return None


@pytest.mark.parametrize(("command", "expected_exit"), [
    ("git status", 0),
    ("uv run ruff check --fix-only", 2),
])
def test_hook_command_from_agent_file_runs(command, expected_exit):
    """Run the agent file's hook command itself, through bash, as Claude Code does.

    This catches a broken command line (wrong path, uv flags, quoting) that
    the tests above miss, because they call the script directly.
    """
    problem = bash_with_uv_problem()
    if problem:
        pytest.skip(f"can't run the agent's hook command: {problem}")
    result = subprocess.run(
        [find_bash(), "-c", hook_command_from_agent()],
        input=tool_call(command),
        capture_output=True,
        timeout=120,
        check=False,
        cwd=ROOT,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(ROOT)},
    )
    assert result.returncode == expected_exit, result.stderr.decode(errors="replace")
    if expected_exit == 2:
        assert b"Blocked for methodology-reviewer" in result.stderr
