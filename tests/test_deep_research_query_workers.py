from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_query_worker_augments_variants_and_records_metadata(monkeypatch):
    from orchestration.ephemeral_workers import WorkerResult
    from tools.deep_research.tool import DeepResearchSession, _augment_query_variants_with_worker

    monkeypatch.setenv("DR_WORKER_QUERY_VARIANTS_ENABLED", "true")

    async def _fake_run_worker(*args, **kwargs):
        return WorkerResult(
            worker_type="query_variants",
            status="ok",
            payload={
                "query_variants": [
                    "Chinese LLMs DeepSeek Qwen agent capabilities tool use function calling benchmark",
                ],
                "notes": ["focus on tool use and benchmark evidence"],
            },
            provider="openai",
            model="gpt-5.4-mini",
            duration_ms=12,
            max_tokens=800,
        )

    monkeypatch.setattr("tools.deep_research.tool.run_worker", _fake_run_worker)

    session = DeepResearchSession(
        "Chinese LLMs DeepSeek Qwen agent capabilities",
        focus_areas=["tool use", "benchmarks"],
    )

    variants = await _augment_query_variants_with_worker(
        session,
        session_id="research_test_session",
        max_queries=12,
    )

    assert any("function calling" in query.lower() for query in variants)
    worker_meta = session.research_metadata["query_variant_worker"]
    assert worker_meta["status"] == "ok"
    assert worker_meta["accepted_variants"] >= 1
    assert worker_meta["fallback_used"] is False


@pytest.mark.asyncio
async def test_query_worker_rejects_off_topic_variants(monkeypatch):
    from orchestration.ephemeral_workers import WorkerResult
    from tools.deep_research.tool import DeepResearchSession, _augment_query_variants_with_worker

    monkeypatch.setenv("DR_WORKER_QUERY_VARIANTS_ENABLED", "true")

    async def _fake_run_worker(*args, **kwargs):
        return WorkerResult(
            worker_type="query_variants",
            status="ok",
            payload={
                "query_variants": [
                    "Make.com automation jobs contact support",
                    "Chinese LLMs DeepSeek Qwen tool use multi-agent benchmark",
                ]
            },
            provider="openai",
            model="gpt-5.4-mini",
            duration_ms=9,
            max_tokens=800,
        )

    monkeypatch.setattr("tools.deep_research.tool.run_worker", _fake_run_worker)

    session = DeepResearchSession(
        "Chinese LLMs DeepSeek Qwen agent capabilities",
        focus_areas=["tool use", "benchmarks"],
    )

    variants = await _augment_query_variants_with_worker(
        session,
        session_id="research_test_session",
        max_queries=12,
    )

    assert not any("make.com" in query.lower() for query in variants)
    worker_meta = session.research_metadata["query_variant_worker"]
    assert worker_meta["accepted_variants"] >= 1
    assert worker_meta["rejected_variants"] >= 1


@pytest.mark.asyncio
async def test_query_worker_failure_keeps_baseline_variants(monkeypatch):
    from orchestration.ephemeral_workers import WorkerResult
    from tools.deep_research.tool import (
        DeepResearchSession,
        _augment_query_variants_with_worker,
        _ensure_research_plan,
    )

    monkeypatch.setenv("DR_WORKER_QUERY_VARIANTS_ENABLED", "true")

    async def _fake_run_worker(*args, **kwargs):
        return WorkerResult(
            worker_type="query_variants",
            status="error",
            error="quota",
            provider="openai",
            model="gpt-5.4-mini",
            duration_ms=7,
            max_tokens=800,
            fallback_used=True,
        )

    monkeypatch.setattr("tools.deep_research.tool.run_worker", _fake_run_worker)

    session = DeepResearchSession(
        "Chinese LLMs DeepSeek Qwen agent capabilities",
        focus_areas=["tool use", "benchmarks"],
    )
    baseline = list(_ensure_research_plan(session).query_variants)

    variants = await _augment_query_variants_with_worker(
        session,
        session_id="research_test_session",
        max_queries=12,
    )

    assert variants == baseline
    worker_meta = session.research_metadata["query_variant_worker"]
    assert worker_meta["status"] == "error"
    assert worker_meta["fallback_used"] is True


@pytest.mark.asyncio
async def test_query_worker_skips_when_no_capacity(monkeypatch):
    from tools.deep_research.tool import DeepResearchSession, _augment_query_variants_with_worker, _ensure_research_plan

    monkeypatch.setenv("DR_WORKER_QUERY_VARIANTS_ENABLED", "true")

    session = DeepResearchSession(
        "Chinese LLMs DeepSeek Qwen agent capabilities",
        focus_areas=["tool use", "benchmarks"],
    )
    baseline = list(_ensure_research_plan(session).query_variants)

    variants = await _augment_query_variants_with_worker(
        session,
        session_id="research_test_session",
        max_queries=len(baseline),
    )

    assert variants == baseline
    worker_meta = session.research_metadata["query_variant_worker"]
    assert worker_meta["status"] == "skipped_no_capacity"
    assert worker_meta["fallback_used"] is False
