"""Tests for the methodology-reviewer's Bash hook, .claude/hooks/reviewer_bash_guard.py.

Each test runs the hook the way Claude Code does: as its own process, with
the tool call as JSON on stdin. Exit code 0 means the command would run; 2
means it is blocked.
"""

import json
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
