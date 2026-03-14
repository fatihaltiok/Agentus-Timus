from __future__ import annotations

from orchestration.conversation_recall_eval import (
    ConversationRecallEvalCase,
    evaluate_conversation_recall_case,
    summarize_conversation_recall_evals,
)


def test_evaluate_conversation_recall_case_hits_top1():
    case = ConversationRecallEvalCase(
        query="Wie war nochmal dein Plan fuer Visual?",
        recalled_items=[
            {"text": "Frueher habe ich den Visual-Pfad zuerst haerten wollen."},
            {"text": "Allgemeiner Ops-Status war kritisch."},
        ],
        expected_markers=["visual-pfad", "haerten"],
        forbidden_markers=["ops-status"],
        label="visual-plan",
    )

    result = evaluate_conversation_recall_case(case)

    assert result["hit_at_1"] is True
    assert result["best_rank"] == 1
    assert result["wrong_top1"] is False
    assert result["score"] == 1.0


def test_evaluate_conversation_recall_case_detects_wrong_top1():
    case = ConversationRecallEvalCase(
        query="Woran lag nochmal der PDF-Fehler?",
        recalled_items=[
            {"text": "Allgemeiner Systemstatus war warn."},
            {"text": "Der PDF-Fehler lag am fehlenden attachment_path und der Report war nicht gebaut."},
        ],
        expected_markers=["attachment_path", "report war nicht gebaut"],
        forbidden_markers=["systemstatus"],
        label="pdf-error",
    )

    result = evaluate_conversation_recall_case(case)

    assert result["hit_at_1"] is False
    assert result["hit_at_3"] is True
    assert result["best_rank"] == 2
    assert result["wrong_top1"] is True


def test_summarize_conversation_recall_evals_aggregates_metrics():
    cases = [
        ConversationRecallEvalCase(
            query="Wie war nochmal dein Plan fuer Visual?",
            recalled_items=[{"text": "Visual-Pfad zuerst haerten."}],
            expected_markers=["visual-pfad"],
            forbidden_markers=[],
            label="visual",
        ),
        ConversationRecallEvalCase(
            query="Woran lag nochmal der PDF-Fehler?",
            recalled_items=[
                {"text": "Allgemeiner Systemstatus."},
                {"text": "PDF-Fehler: attachment_path fehlte."},
            ],
            expected_markers=["attachment_path"],
            forbidden_markers=["systemstatus"],
            label="pdf",
        ),
    ]

    summary = summarize_conversation_recall_evals(cases)

    assert summary["total_cases"] == 2
    assert summary["hit_rate_at_1"] == 0.5
    assert summary["hit_rate_at_3"] == 1.0
    assert summary["wrong_top1_rate"] == 0.5
    assert summary["avg_score"] > 0.0
    assert len(summary["results"]) == 2
