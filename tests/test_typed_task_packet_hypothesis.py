from hypothesis import given, strategies as st

from orchestration.typed_task_packet import build_request_preflight, build_typed_task_packet


@given(
    objective=st.text(min_size=1, max_size=400),
    tools=st.lists(st.text(min_size=1, max_size=20), min_size=0, max_size=8),
    request_len=st.integers(min_value=0, max_value=6000),
)
def test_typed_task_packet_preflight_shape_is_stable(
    objective: str,
    tools: list[str],
    request_len: int,
) -> None:
    packet = build_typed_task_packet(
        packet_type="generic",
        objective=objective,
        allowed_tools=tools,
    )
    report = build_request_preflight(
        packet=packet,
        original_request="q" * request_len,
        rendered_handoff="handoff",
        task_type="single_lane",
    )

    assert packet["packet_type"] == "generic"
    assert report["state"] in {"ok", "warn", "blocked"}
    assert isinstance(report["blocked"], bool)
    assert report["metrics"]["original_request_chars"] == request_len
    assert report["metrics"]["packet_chars"] >= 0
    assert report["caps"]["provider_token_limit"] >= 512
