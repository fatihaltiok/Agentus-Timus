from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from orchestration.improvement_task_compiler import compile_improvement_task


@given(
    verified_paths=st.lists(
        st.sampled_from(
            [
                "main_dispatcher.py",
                "server/mcp_server.py",
                "orchestration/meta_orchestration.py",
                "tools/email_tool/tool.py",
            ]
        ),
        max_size=4,
        unique=True,
    ),
    event_type=st.sampled_from(["dispatcher_meta_fallback", "send_email_failed", "challenge_reblocked", "context_misread_suspected"]),
)
@settings(max_examples=40)
def test_hypothesis_verified_paths_are_preferred_when_present(verified_paths, event_type):
    result = compile_improvement_task(
        {
            "candidate_id": "hypo:path",
            "category": "runtime",
            "problem": "Problem",
            "proposed_action": "Aktion",
            "priority_score": 0.7,
            "verified_paths": verified_paths,
            "event_type": event_type,
        }
    )
    if verified_paths:
        assert result["target_files"] == verified_paths[:4]
    else:
        assert len(result["target_files"]) <= 4
