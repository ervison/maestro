"""Tests for the gaps server - parser and server round-trip."""
from __future__ import annotations


GAP_MARKDOWN = """\
# Gaps

[GAP] What is the target audience? (B2C or B2B?)
[GAP] What is the expected monthly active user count?
[GAP] Is SSO required?
"""


def test_parse_gaps_returns_gap_items():
    from maestro.sdlc.gaps_server import parse_gaps

    items = parse_gaps(GAP_MARKDOWN)
    assert len(items) == 3
    assert items[0].question == "What is the target audience? (B2C or B2B?)"
    assert len(items[0].options) >= 2
    assert items[0].recommended_index == 0


def test_parse_gaps_empty_content():
    from maestro.sdlc.gaps_server import parse_gaps

    items = parse_gaps("# Gaps\n\nNo gaps found.\n")
    assert items == []


def test_parse_gaps_no_gap_tag():
    from maestro.sdlc.gaps_server import parse_gaps

    items = parse_gaps("# Gaps\n\nSome text without GAP markers.\n")
    assert items == []
