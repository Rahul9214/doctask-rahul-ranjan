from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import UploadFile
from helpers import ingest_corpus, make_examine, make_understand
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.attributes import flag_modified
from starlette.datastructures import Headers

from app.errors import NotFoundError, ValidationError
from app.examine_graph import CANONICAL_STAGES
from app.models import (
    Contradiction,
    ExaminationRun,
    Fact,
    Finding,
    FindingContradictionEvidence,
    FindingFactEvidence,
    SourceBlock,
)
from app.ruleset import RULES, RULESET_VERSION
from app.services import Phase02Service
from app.storage import LocalFileStorage
from app.understand_graph import utcnow as understand_utcnow


@pytest.mark.integration
async def test_aurora_examine_has_grounded_pass_fail_warning_unknown(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    examine = make_examine(phase02)
    analysis = await examine.understand.create_run(corpus.id)
    run = await examine.create_run(corpus.id, analysis.id)
    findings = await examine.list_findings(corpus.id, run.id)
    responses = await examine.list_finding_responses(corpus.id, run.id)
    by_rule = {item.rule_id: item for item in findings}
    by_response = {item.rule_id: item for item in responses}
    summary = await examine.get_summary(corpus.id, run.id)

    assert run.status == "completed"
    assert run.ruleset_version == RULESET_VERSION
    assert run.findings_status == "populated"
    assert {item.rule_id for item in findings} == {rule.rule_id for rule in RULES}
    assert all(item.rule_version == "1" for item in findings)

    contradiction = by_response["spa.milestone.production-readiness"]
    assert contradiction.outcome == "fail"
    assert contradiction.evidence_kind == "grounded_facts"
    assert len(contradiction.fact_ids) == 2
    assert contradiction.contradiction_ids
    assert len(contradiction.citations) == 2
    quotes = {item.exact_quote for item in contradiction.citations}
    joined = " ".join(quotes)
    assert "2026-10-30" in joined
    assert "2026-11-14" in joined

    open_conflict = by_response["spa.contradiction.open"]
    assert open_conflict.outcome == "pass"
    assert open_conflict.evidence_kind == "process_attestation"
    assert open_conflict.fact_ids == []
    assert open_conflict.contradiction_ids == []
    assert open_conflict.citations == []
    assert not (set(contradiction.contradiction_ids) & set(open_conflict.contradiction_ids))

    sponsor = by_response["spa.ownership.sponsor"]
    assert sponsor.outcome == "pass"
    assert sponsor.fact_ids
    assert sponsor.citations
    assert {item.exact_quote for item in sponsor.citations}

    status = by_rule["spa.status.clarity"]
    assert status.outcome == "warning"

    budget = by_response["spa.ownership.budget"]
    assert budget.outcome == "unknown"
    assert budget.evidence_kind == "none"
    assert budget.fact_ids == []
    assert budget.citations == []
    assert "budget_owner" in budget.message

    security = by_rule["spa.ownership.security-signoff"]
    assert security.outcome == "fail"

    assert summary.fail_count == 2
    assert summary.pass_count >= 1
    assert summary.warning_count >= 1
    assert summary.unknown_count >= 1
    assert summary.no_findings is False
    failing_with_conflict = [
        item.rule_id
        for item in responses
        if item.outcome == "fail" and contradiction.contradiction_ids[0] in item.contradiction_ids
    ]
    assert failing_with_conflict == ["spa.milestone.production-readiness"]

    events = await examine.list_stage_events(corpus.id, run.id)
    assert {event.stage_name for event in events} >= set(CANONICAL_STAGES)
    assert all(event.estimated_cost_usd == 0.0 for event in events)
    assert all(event.cost_basis == "zero_deterministic" for event in events)
    assert all(event.model_operation_count == 0 for event in events)
    by_stage = {event.stage_name: event for event in events}
    assert by_stage["select_rules"].rule_evaluation_count == 0
    assert by_stage["evaluate_rules"].rule_evaluation_count == len(RULES)
    assert by_stage["validate_evidence"].rule_evaluation_count == 0
    assert by_stage["summarize_findings"].rule_evaluation_count == 0
    assert by_stage["finalize"].rule_evaluation_count == 0


@pytest.mark.integration
async def test_harbor_examine_has_a_different_profile_without_name_branching(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    examine = make_examine(phase02)
    aurora_analysis = await examine.understand.create_run(aurora.id)
    harbor_analysis = await examine.understand.create_run(harbor.id)
    aurora_run = await examine.create_run(aurora.id, aurora_analysis.id)
    harbor_run = await examine.create_run(harbor.id, harbor_analysis.id)
    aurora_findings = {
        item.rule_id: item for item in await examine.list_findings(aurora.id, aurora_run.id)
    }
    harbor_findings = {
        item.rule_id: item for item in await examine.list_findings(harbor.id, harbor_run.id)
    }

    assert harbor_run.corpus_id == harbor.id
    assert aurora_findings["spa.milestone.production-readiness"].outcome == "fail"
    assert harbor_findings["spa.milestone.production-readiness"].outcome == "unknown"
    assert aurora_findings["spa.status.clarity"].outcome == "warning"
    assert harbor_findings["spa.status.clarity"].outcome == "pass"
    assert aurora_findings["spa.contradiction.open"].outcome == "pass"
    assert harbor_findings["spa.contradiction.open"].outcome == "pass"
    assert harbor_findings["spa.contradiction.open"].evidence_kind == "process_attestation"
    assert list(harbor_findings["spa.contradiction.open"].fact_ids) == []
    assert aurora_findings["spa.dependency.evidence"].outcome == "pass"
    assert harbor_findings["spa.dependency.evidence"].outcome == "unknown"
    assert harbor_findings["spa.ownership.sponsor"].outcome == "pass"
    aurora_outcomes = {item.outcome for item in aurora_findings.values()}
    harbor_outcomes = {item.outcome for item in harbor_findings.values()}
    assert aurora_outcomes != harbor_outcomes
    harbor_messages = " ".join(item.message for item in harbor_findings.values())
    assert "Elena Marlow" not in harbor_messages
    assert "Aurora" not in harbor_messages


@pytest.mark.integration
async def test_no_findings_examination_is_explicit_empty_result(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, _storage = phase02_service
    corpus = await phase02.create_corpus(
        name="Blank notes",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    await phase02.ingest(
        corpus_id=corpus.id,
        logical_name="Blank",
        declared_format="txt",
        upload=UploadFile(
            BytesIO(b"This page intentionally left blank.\nWeather notes: sunny."),
            filename="blank.txt",
            headers=Headers({"content-type": "text/plain"}),
        ),
    )
    examine = make_examine(phase02)
    analysis = await examine.understand.create_run(corpus.id)
    run = await examine.create_run(corpus.id, analysis.id)
    findings = await examine.list_findings(corpus.id, run.id)
    summary = await examine.get_summary(corpus.id, run.id)
    events = await examine.list_stage_events(corpus.id, run.id)
    by_name = {event.stage_name: event for event in events}
    assert analysis.findings_status == "no_findings"
    assert run.findings_status == "no_findings"
    assert findings == []
    assert summary.no_findings is True
    assert summary.evaluated_rule_count == 0
    assert by_name["select_rules"].status == "skipped"
    assert by_name["select_rules"].skip_reason == "no_applicable_evidence"
    assert by_name["evaluate_rules"].skip_reason == "no_applicable_evidence"
    assert by_name["evaluate_rules"].rule_evaluation_count == 0


@pytest.mark.integration
async def test_examination_is_corpus_scoped(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    first = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    second = await phase02.create_corpus(
        name="Other",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    examine = make_examine(phase02)
    analysis = await examine.understand.create_run(first.id)
    run = await examine.create_run(first.id, analysis.id)
    with pytest.raises(NotFoundError) as missing_run:
        await examine.get_run(second.id, run.id)
    assert missing_run.value.code == "examination_run_not_found"
    with pytest.raises(NotFoundError) as missing_analysis:
        await examine.create_run(second.id, analysis.id)
    assert missing_analysis.value.code == "analysis_run_not_found"
    findings = await examine.list_findings(first.id, run.id)
    assert all(item.corpus_id == first.id for item in findings)


@pytest.mark.integration
async def test_failed_analysis_run_cannot_be_examined(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    phase02, _storage = phase02_service
    corpus = await phase02.create_corpus(
        name="Pending",
        domain="software-project-assurance",
        declared_formats=["txt"],
    )
    understand = make_understand(phase02)
    from app.models import AnalysisRun
    from app.taxonomy import GRAPH_VERSION, TAXONOMY_VERSION

    async with phase02.session_factory() as session:
        analysis = AnalysisRun(
            corpus_id=corpus.id,
            status="failed",
            findings_status="failed",
            started_at=understand_utcnow(),
            model_provider_mode="deterministic",
            model_name="test",
            taxonomy_version=TAXONOMY_VERSION,
            graph_version=GRAPH_VERSION,
            configuration={},
            result_payload={},
        )
        session.add(analysis)
        await session.commit()
        await session.refresh(analysis)
    examine = make_examine(phase02, understand=understand)
    with pytest.raises(ValidationError) as error:
        await examine.create_run(corpus.id, analysis.id)
    assert error.value.code == "analysis_run_not_examinable"


@pytest.mark.integration
async def test_database_rejects_cross_corpus_examination_and_bad_outcomes(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    examine = make_examine(phase02)
    aurora_analysis = await examine.understand.create_run(aurora.id)
    harbor_analysis = await examine.understand.create_run(harbor.id)

    async with phase02.session_factory() as session:
        run = ExaminationRun(
            corpus_id=aurora.id,
            analysis_run_id=harbor_analysis.id,
            status="running",
            findings_status="pending",
            ruleset_version=RULESET_VERSION,
            graph_version="examine.v1",
            started_at=understand_utcnow(),
            configuration={},
            result_payload={},
        )
        session.add(run)
        with pytest.raises(IntegrityError):
            await session.commit()

    async with phase02.session_factory() as session:
        run = _examination_run(aurora.id, aurora_analysis.id)
        session.add(run)
        await session.flush()
        session.add(
            Finding(
                examination_run_id=run.id,
                corpus_id=aurora.id,
                analysis_run_id=aurora_analysis.id,
                rule_id="spa.ownership.sponsor",
                rule_version="1",
                outcome="maybe",
                severity="info",
                title="bad",
                message="bad",
                structured_reason={},
                evidence_kind="none",
                confidence=1.0,
                status="recorded",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with phase02.session_factory() as session:
        run = _examination_run(aurora.id, aurora_analysis.id)
        session.add(run)
        await session.flush()
        session.add(
            Finding(
                examination_run_id=run.id,
                corpus_id=aurora.id,
                analysis_run_id=aurora_analysis.id,
                rule_id="",
                rule_version="1",
                outcome="pass",
                severity="info",
                title="empty rule",
                message="empty",
                structured_reason={},
                evidence_kind="process_attestation",
                confidence=1.0,
                status="recorded",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with phase02.session_factory() as session:
        run = _examination_run(aurora.id, aurora_analysis.id)
        session.add(run)
        await session.flush()
        session.add(
            Finding(
                examination_run_id=run.id,
                corpus_id=aurora.id,
                analysis_run_id=aurora_analysis.id,
                rule_id="spa.ownership.sponsor",
                rule_version="1",
                outcome="pass",
                severity="info",
                title="ungrounded pass",
                message="ungrounded",
                structured_reason={},
                evidence_kind="none",
                confidence=1.0,
                status="recorded",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.integration
async def test_database_rejects_random_and_cross_scope_evidence(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    examine = make_examine(phase02)
    aurora_analysis = await examine.understand.create_run(aurora.id)
    harbor_analysis = await examine.understand.create_run(harbor.id)
    aurora_again = await examine.understand.create_run(aurora.id)

    async with phase02.session_factory() as session:
        aurora_fact = await session.scalar(
            select(Fact).where(
                Fact.run_id == aurora_analysis.id,
                Fact.corpus_id == aurora.id,
                Fact.support_status == "supported",
            )
        )
        harbor_fact = await session.scalar(
            select(Fact).where(
                Fact.run_id == harbor_analysis.id,
                Fact.corpus_id == harbor.id,
                Fact.support_status == "supported",
            )
        )
        aurora_again_fact = await session.scalar(
            select(Fact).where(
                Fact.run_id == aurora_again.id,
                Fact.corpus_id == aurora.id,
                Fact.support_status == "supported",
            )
        )
        aurora_conflict = await session.scalar(
            select(Contradiction).where(
                Contradiction.run_id == aurora_analysis.id,
                Contradiction.corpus_id == aurora.id,
            )
        )
        aurora_again_conflict = await session.scalar(
            select(Contradiction).where(
                Contradiction.run_id == aurora_again.id,
                Contradiction.corpus_id == aurora.id,
            )
        )
        assert aurora_fact is not None
        assert harbor_fact is not None
        assert aurora_again_fact is not None
        assert aurora_conflict is not None
        assert aurora_again_conflict is not None
        aurora_fact_id = aurora_fact.id
        harbor_fact_id = harbor_fact.id
        aurora_again_fact_id = aurora_again_fact.id
        aurora_conflict_id = aurora_conflict.id
        aurora_again_conflict_id = aurora_again_conflict.id

    async with phase02.session_factory() as session:
        run = _examination_run(aurora.id, aurora_analysis.id)
        session.add(run)
        await session.flush()
        finding = _grounded_finding(run, "spa.ownership.sponsor")
        session.add(finding)
        await session.flush()
        session.add(
            FindingFactEvidence(
                finding_id=finding.id,
                examination_run_id=run.id,
                corpus_id=aurora.id,
                analysis_run_id=aurora_analysis.id,
                fact_id=uuid4(),
                evidence_kind="grounded_facts",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with phase02.session_factory() as session:
        run = _examination_run(aurora.id, aurora_analysis.id)
        session.add(run)
        await session.flush()
        finding = _grounded_finding(run, "spa.milestone.production-readiness")
        session.add(finding)
        await session.flush()
        session.add(
            FindingContradictionEvidence(
                finding_id=finding.id,
                examination_run_id=run.id,
                corpus_id=aurora.id,
                analysis_run_id=aurora_analysis.id,
                contradiction_id=uuid4(),
                evidence_kind="grounded_facts",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with phase02.session_factory() as session:
        run = _examination_run(aurora.id, aurora_analysis.id)
        session.add(run)
        await session.flush()
        finding = _grounded_finding(run, "spa.ownership.sponsor")
        session.add(finding)
        await session.flush()
        session.add(
            FindingFactEvidence(
                finding_id=finding.id,
                examination_run_id=run.id,
                corpus_id=aurora.id,
                analysis_run_id=aurora_analysis.id,
                fact_id=harbor_fact_id,
                evidence_kind="grounded_facts",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with phase02.session_factory() as session:
        run = _examination_run(aurora.id, aurora_analysis.id)
        session.add(run)
        await session.flush()
        finding = _grounded_finding(run, "spa.ownership.sponsor")
        session.add(finding)
        await session.flush()
        session.add(
            FindingFactEvidence(
                finding_id=finding.id,
                examination_run_id=run.id,
                corpus_id=aurora.id,
                analysis_run_id=aurora_analysis.id,
                fact_id=aurora_again_fact_id,
                evidence_kind="grounded_facts",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with phase02.session_factory() as session:
        run = _examination_run(aurora.id, aurora_analysis.id)
        session.add(run)
        await session.flush()
        finding = _grounded_finding(run, "spa.milestone.production-readiness")
        session.add(finding)
        await session.flush()
        session.add(
            FindingContradictionEvidence(
                finding_id=finding.id,
                examination_run_id=run.id,
                corpus_id=aurora.id,
                analysis_run_id=aurora_analysis.id,
                contradiction_id=aurora_again_conflict_id,
                evidence_kind="grounded_facts",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with phase02.session_factory() as session:
        run = _examination_run(aurora.id, aurora_analysis.id)
        session.add(run)
        await session.flush()
        finding = Finding(
            examination_run_id=run.id,
            corpus_id=aurora.id,
            analysis_run_id=aurora_analysis.id,
            rule_id="spa.ownership.budget",
            rule_version="1",
            outcome="unknown",
            severity="info",
            title="Budget owner is identified",
            message="missing",
            structured_reason={},
            evidence_kind="none",
            confidence=0.0,
            status="recorded",
        )
        session.add(finding)
        await session.flush()
        session.add(
            FindingFactEvidence(
                finding_id=finding.id,
                examination_run_id=run.id,
                corpus_id=aurora.id,
                analysis_run_id=aurora_analysis.id,
                fact_id=aurora_fact_id,
                evidence_kind="grounded_facts",
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()

    async with phase02.session_factory() as session:
        run = _examination_run(aurora.id, aurora_analysis.id)
        session.add(run)
        await session.flush()
        finding = _grounded_finding(run, "spa.milestone.production-readiness")
        session.add(finding)
        await session.flush()
        session.add(
            FindingFactEvidence(
                finding_id=finding.id,
                examination_run_id=run.id,
                corpus_id=aurora.id,
                analysis_run_id=aurora_analysis.id,
                fact_id=aurora_fact_id,
                evidence_kind="grounded_facts",
            )
        )
        session.add(
            FindingContradictionEvidence(
                finding_id=finding.id,
                examination_run_id=run.id,
                corpus_id=aurora.id,
                analysis_run_id=aurora_analysis.id,
                contradiction_id=aurora_conflict_id,
                evidence_kind="grounded_facts",
            )
        )
        await session.commit()


@pytest.mark.integration
async def test_valid_persisted_citation_allows_definitive_finding(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    examine = make_examine(phase02)
    analysis = await examine.understand.create_run(corpus.id)
    run = await examine.create_run(corpus.id, analysis.id)
    responses = await examine.list_finding_responses(corpus.id, run.id)
    sponsor = next(item for item in responses if item.rule_id == "spa.ownership.sponsor")
    assert run.status == "completed"
    assert sponsor.outcome == "pass"
    assert sponsor.citations
    async with phase02.session_factory() as session:
        fact = await session.get(Fact, sponsor.fact_ids[0])
        assert fact is not None
        assert fact.citation is not None
        assert sponsor.citations[0].exact_quote == fact.citation["exact_quote"]


@pytest.mark.integration
async def test_tampered_persisted_citation_blocks_definitive_finding(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    examine = make_examine(phase02)
    analysis = await examine.understand.create_run(corpus.id)
    async with phase02.session_factory() as session:
        fact = await session.scalar(
            select(Fact).where(
                Fact.run_id == analysis.id,
                Fact.corpus_id == corpus.id,
                Fact.support_status == "supported",
                Fact.subject_key == "project_sponsor",
            )
        )
        assert fact is not None
        citation = dict(fact.citation or {})
        citation["exact_quote"] = "this quote is not in the original source"
        fact.citation = citation
        flag_modified(fact, "citation")
        await session.commit()
    run = await examine.create_run(corpus.id, analysis.id)
    assert run.status == "failed"
    assert run.error_code == "citation_revalidation_failed"
    assert await examine.list_findings(corpus.id, run.id) == []


@pytest.mark.integration
async def test_wrong_block_citation_blocks_definitive_finding(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    examine = make_examine(phase02)
    analysis = await examine.understand.create_run(corpus.id)
    async with phase02.session_factory() as session:
        fact = await session.scalar(
            select(Fact).where(
                Fact.run_id == analysis.id,
                Fact.corpus_id == corpus.id,
                Fact.support_status == "supported",
                Fact.subject_key == "project_sponsor",
            )
        )
        assert fact is not None
        other = await session.scalar(
            select(SourceBlock).where(
                SourceBlock.corpus_id == corpus.id,
                SourceBlock.id != fact.source_block_id,
            )
        )
        assert other is not None
        fact.source_block_id = other.id
        await session.commit()
    run = await examine.create_run(corpus.id, analysis.id)
    assert run.status == "failed"
    assert run.error_code in {"source_block_mismatch", "citation_revalidation_failed"}
    assert await examine.list_findings(corpus.id, run.id) == []


@pytest.mark.integration
async def test_contradiction_with_one_tampered_side_is_rejected(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    corpus = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    examine = make_examine(phase02)
    analysis = await examine.understand.create_run(corpus.id)
    async with phase02.session_factory() as session:
        conflict = await session.scalar(
            select(Contradiction).where(
                Contradiction.run_id == analysis.id,
                Contradiction.corpus_id == corpus.id,
            )
        )
        assert conflict is not None
        fact = await session.get(Fact, conflict.fact_a_id)
        assert fact is not None
        citation = dict(fact.citation or {})
        citation["exact_quote"] = "tampered production readiness quote"
        fact.citation = citation
        flag_modified(fact, "citation")
        await session.commit()
    run = await examine.create_run(corpus.id, analysis.id)
    assert run.status == "failed"
    assert run.error_code == "citation_revalidation_failed"
    assert await examine.list_findings(corpus.id, run.id) == []


def _examination_run(corpus_id: UUID, analysis_run_id: UUID) -> ExaminationRun:
    return ExaminationRun(
        corpus_id=corpus_id,
        analysis_run_id=analysis_run_id,
        status="completed",
        findings_status="populated",
        ruleset_version=RULESET_VERSION,
        graph_version="examine.v1",
        started_at=understand_utcnow(),
        configuration={},
        result_payload={},
    )


def _grounded_finding(run: ExaminationRun, rule_id: str) -> Finding:
    return Finding(
        examination_run_id=run.id,
        corpus_id=run.corpus_id,
        analysis_run_id=run.analysis_run_id,
        rule_id=rule_id,
        rule_version="1",
        outcome="fail",
        severity="high",
        title=rule_id,
        message="grounded",
        structured_reason={},
        evidence_kind="grounded_facts",
        confidence=1.0,
        status="recorded",
    )
