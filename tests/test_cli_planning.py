"""Tests for the `maestro planning` CLI surface."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from maestro.cli import main


def test_planning_subcommand_exists() -> None:
    with patch("sys.argv", ["maestro", "planning", "check", "--help"]):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0


def test_planning_check_command_exits_zero_when_consistent() -> None:
    with patch("sys.argv", ["maestro", "planning", "check"]):
        with pytest.raises(SystemExit) as exc_info:
            main()

    assert exc_info.value.code == 0


def test_planning_check_exits_nonzero_when_inconsistent() -> None:
    from maestro.planning import ConsistencyCheckResult

    with patch("maestro.planning.check_planning_consistency",
               return_value=ConsistencyCheckResult(errors=["drift error"])):
        with patch("sys.argv", ["maestro", "planning", "check"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

    assert exc_info.value.code != 0


def test_planning_check_root_flag_passes_path() -> None:
    from maestro.planning import ConsistencyCheckResult

    with patch("maestro.planning.check_planning_consistency",
               return_value=ConsistencyCheckResult(errors=[])) as mock_check:
        with patch("sys.argv", ["maestro", "planning", "check", "--root", "/tmp/fake"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

    assert exc_info.value.code == 0
    called_arg = str(mock_check.call_args[0][0])
    assert "/tmp/fake" in called_arg

