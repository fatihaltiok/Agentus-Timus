"""CrossHair + Hypothesis contracts for shell-tool argv helpers."""

import deal
from hypothesis import given, settings
from hypothesis import strategies as st

from tools.shell_tool.tool import _safe_shlex_split, _shell_argv, _systemctl_argv


@deal.pre(lambda command: bool(command.strip()))
@deal.post(lambda r: len(r) == 3 and r[1] == "-lc")
def _contract_shell_argv(command: str) -> list[str]:
    return _shell_argv(command)


@deal.pre(lambda unit: bool(unit.strip()))
@deal.post(lambda r: len(r) >= 4 and r[-2] == "status")
def _contract_systemctl_status_argv(unit: str) -> list[str]:
    return _systemctl_argv("status", unit)


@deal.post(lambda r: isinstance(r, list))
def _contract_safe_split(raw: str) -> list[str]:
    return _safe_shlex_split(raw)


@given(st.text(min_size=1, max_size=80).filter(lambda s: bool(s.strip())))
@settings(max_examples=80)
def test_hypothesis_shell_argv_shape(command: str) -> None:
    argv = _contract_shell_argv(command)
    assert argv[1] == "-lc"
    assert argv[2] == command


@given(st.text(min_size=1, max_size=40).filter(lambda s: bool(s.strip()) and " " not in s))
@settings(max_examples=80)
def test_hypothesis_systemctl_status_argv_shape(unit: str) -> None:
    argv = _contract_systemctl_status_argv(unit)
    assert argv[:3] == ["sudo", "-n", "/usr/bin/systemctl"]
    assert argv[-2:] == ["status", unit]


@given(st.text(max_size=80))
@settings(max_examples=80)
def test_hypothesis_safe_split_never_crashes(raw: str) -> None:
    result = _contract_safe_split(raw)
    assert isinstance(result, list)
