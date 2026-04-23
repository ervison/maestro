"""Tests for the `maestro planning` CLI surface."""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_planning_subcommand_exists() -> None:
    with patch("sys.argv", ["maestro", "planning", "check", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            from maestro.cli import main

            main()

    assert exc_info.value.code == 0


def test_planning_check_command_exits_zero_when_consistent() -> None:
    with patch("sys.argv", ["maestro", "planning", "check"]):
        with pytest.raises(SystemExit) as exc_info:
            from maestro.cli import main

            main()

    assert exc_info.value.code == 0
