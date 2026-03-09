"""CrossHair + Hypothesis contracts for phase-2 launcher hardening helpers."""

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from tools.application_launcher.tool import _split_launch_command
from tools.visual_browser_tool.tool import _get_windows_taskkill_command


@deal.pre(lambda pid: pid > 0)
@deal.post(lambda r: len(r) == 5 and r[0] == "taskkill")
def _contract_taskkill_command(pid: int) -> list[str]:
    return _get_windows_taskkill_command(pid)


@deal.pre(lambda command: bool(command.strip()) and command.count('"') % 2 == 0)
@deal.post(lambda r: isinstance(r, list) and len(r) >= 1)
def _contract_split_launch_command(command: str) -> list[str]:
    return _split_launch_command(command)


@given(st.integers(min_value=1, max_value=100_000))
@settings(max_examples=80)
def test_hypothesis_taskkill_command_shape(pid: int) -> None:
    command = _contract_taskkill_command(pid)
    assert command == ["taskkill", "/PID", str(pid), "/T", "/F"]


@given(
    st.lists(
        st.text(
            alphabet=st.characters(blacklist_characters='"'),
            min_size=1,
            max_size=12,
        ).filter(lambda s: bool(s.strip())),
        min_size=1,
        max_size=5,
    )
)
@settings(max_examples=80)
def test_hypothesis_split_launch_command_produces_parts(parts: list[str]) -> None:
    command = " ".join(parts)
    split = _contract_split_launch_command(command)
    assert len(split) >= 1
