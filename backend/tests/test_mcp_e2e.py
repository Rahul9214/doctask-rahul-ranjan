from pathlib import Path
from uuid import UUID, uuid4

import pytest
from helpers import ingest_corpus
from mcp_helpers import (
    ApplicationErrorCall,
    call_err,
    call_ok,
    mappings,
    stdio_mcp,
    stdio_mcp_capturing_stderr,
)
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.mcp_server import BUSINESS_TOOL_NAMES
from app.models import Fact
from app.services import Phase02Service
from app.storage import LocalFileStorage


def _required(items: object) -> list[dict[str, object]]:
    return [item for item in mappings(items) if item["review_required"]]


@pytest.mark.integration
@pytest.mark.mcp
async def test_mcp_stdio_aurora_machine_review_flow(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, storage = phase02_service
    await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    async with stdio_mcp(storage) as client:
        listed = await client.list_tools()
        names = {tool.name for tool in listed.tools}
        assert set(BUSINESS_TOOL_NAMES) <= names
        discovered = await call_ok(client, "list_corpora", {"name": "Aurora Control Hub"})
        assert len(discovered["corpora"]) == 1
        corpus_id = discovered["corpora"][0]["id"]
        corpus = await call_ok(client, "get_corpus", {"corpus_id": corpus_id})
        assert corpus["name"] == "Aurora Control Hub"
        sources = await call_ok(client, "list_sources", {"corpus_id": corpus_id})
        assert sources["sources"]

        run = await call_ok(client, "start_workflow", {"corpus_id": corpus_id})
        assert run["status"] == "waiting_for_review"
        status = await call_ok(
            client,
            "get_workflow_status",
            {"corpus_id": corpus_id, "workflow_run_id": run["id"]},
        )
        assert status["run"]["status"] == "waiting_for_review"
        assert status["review"]["status"] == "waiting_for_review"
        assert any(event["event_type"] == "waiting_for_review" for event in status["events"])

        understanding = await call_ok(
            client,
            "get_understanding",
            {"corpus_id": corpus_id, "analysis_run_id": run["analysis_run_id"]},
        )
        assert understanding["facts"]
        examination = await call_ok(
            client,
            "get_examination",
            {"corpus_id": corpus_id, "examination_run_id": run["examination_run_id"]},
        )
        assert examination["findings"]
        items = await call_ok(
            client,
            "list_review_items",
            {"corpus_id": corpus_id, "review_session_id": run["review_session_id"]},
        )
        required_items = _required(items["items"])
        assert required_items
        evidenced = next(item for item in required_items if item["citations"])
        assert mappings(evidenced["citations"])[0]["exact_quote"]
        assert evidenced["outcome"] in {"fail", "warning", "unknown"}

        await call_ok(
            client,
            "approve_review_item",
            {
                "corpus_id": corpus_id,
                "review_session_id": run["review_session_id"],
                "item_id": required_items[0]["id"],
            },
        )
        reject_target = required_items[1] if len(required_items) > 1 else required_items[0]
        await call_ok(
            client,
            "reject_review_item",
            {
                "corpus_id": corpus_id,
                "review_session_id": run["review_session_id"],
                "item_id": reject_target["id"],
            },
        )
        edit_target = required_items[-1]
        await call_ok(
            client,
            "edit_review_item",
            {
                "corpus_id": corpus_id,
                "review_session_id": run["review_session_id"],
                "item_id": edit_target["id"],
                "edited_content": "Reviewer-authored Aurora restatement.",
                "reviewer_authored_acknowledged": True,
            },
        )
        remaining = await call_ok(
            client,
            "list_review_items",
            {"corpus_id": corpus_id, "review_session_id": run["review_session_id"]},
        )
        for item in mappings(remaining["items"]):
            if item["review_required"] and item["review_status"] == "pending":
                await call_ok(
                    client,
                    "approve_review_item",
                    {
                        "corpus_id": corpus_id,
                        "review_session_id": run["review_session_id"],
                        "item_id": item["id"],
                    },
                )
        completed = await call_ok(
            client,
            "complete_review",
            {"corpus_id": corpus_id, "review_session_id": run["review_session_id"]},
        )
        assert completed["status"] == "completed"
        finished = await call_ok(
            client,
            "resume_workflow",
            {"corpus_id": corpus_id, "workflow_run_id": run["id"]},
        )
        assert finished["status"] == "completed"
        events = await call_ok(
            client,
            "get_workflow_status",
            {"corpus_id": corpus_id, "workflow_run_id": run["id"]},
        )
        assert events["run"]["status"] == "completed"
        assert events["events"]
        assert events["run"]["resume_count"] >= 1
        missing = await call_err(client, "get_current_register", {"corpus_id": corpus_id})
        assert missing["code"] == "publication_not_found"
        reviewed = await call_ok(
            client,
            "list_review_items",
            {"corpus_id": corpus_id, "review_session_id": run["review_session_id"]},
        )
        applied = next(
            item
            for item in mappings(reviewed["items"])
            if item["review_status"] in {"approved", "edited"} and item["fact_ids"]
        )
        fact_id = UUID(str(applied["fact_ids"][0]))
        async with phase02.session_factory() as session:
            fact = await session.scalar(
                select(Fact).where(Fact.id == fact_id, Fact.corpus_id == UUID(str(corpus_id)))
            )
            assert fact is not None
            original_citation = dict(fact.citation or {})
            tampered = dict(original_citation)
            tampered["exact_quote"] = "mcp-publication-tamper-sentinel"
            fact.citation = tampered
            flag_modified(fact, "citation")
            await session.commit()
        rejected_publication = await call_err(
            client,
            "publish_register",
            {
                "corpus_id": corpus_id,
                "review_session_id": run["review_session_id"],
            },
        )
        assert rejected_publication["code"] == "publication_evidence_validation_failed"
        assert "mcp-publication-tamper-sentinel" not in rejected_publication["raw_text"]
        async with phase02.session_factory() as session:
            fact = await session.get(Fact, fact_id)
            assert fact is not None
            fact.citation = original_citation
            flag_modified(fact, "citation")
            await session.commit()
        published = await call_ok(
            client,
            "publish_register",
            {
                "corpus_id": corpus_id,
                "review_session_id": run["review_session_id"],
            },
        )
        assert published["status"] == "published"
        assert published["is_current"] is True
        assert published["workflow_run_id"] == run["id"]
        applied_rules = {item["rule_id"] for item in mappings(published["items"])}
        rejected_rules = set(published["omitted_rejected_rule_ids"])
        assert rejected_rules
        assert rejected_rules.isdisjoint(applied_rules)
        edited = next(item for item in mappings(published["items"]) if item["reviewer_authored"])
        assert edited["content_origin"] == "mixed"
        assert edited["system_grounded"] is False
        assert "Reviewer-authored" in str(edited["reviewer_authored_content"])
        current = await call_ok(client, "get_current_register", {"corpus_id": corpus_id})
        assert current["id"] == published["id"]
        repeated = await call_ok(
            client,
            "publish_register",
            {
                "corpus_id": corpus_id,
                "review_session_id": run["review_session_id"],
            },
        )
        assert repeated["id"] == published["id"]
        assert repeated["content_sha256"] == published["content_sha256"]


@pytest.mark.integration
@pytest.mark.mcp
async def test_mcp_stdio_harbor_same_tools_and_cross_corpus_denial(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, storage = phase02_service
    aurora = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    async with stdio_mcp(storage) as client:
        listed = await client.list_tools()
        names = {tool.name for tool in listed.tools}
        assert set(BUSINESS_TOOL_NAMES) <= names
        harbor = await call_ok(client, "list_corpora", {"name": "Harbor Ledger Modernization"})
        assert len(harbor["corpora"]) == 1
        harbor_id = harbor["corpora"][0]["id"]
        assert harbor_id != str(aurora.id)
        sources = await call_ok(client, "list_sources", {"corpus_id": harbor_id})
        source_names = {item["logical_name"] for item in mappings(sources["sources"])}
        assert "Delivery Plan" in source_names
        assert "Governance Notes" in source_names
        assert "Project Charter" not in source_names

        harbor_run = await call_ok(client, "start_workflow", {"corpus_id": harbor_id})
        assert harbor_run["status"] == "waiting_for_review"
        harbor_exam = await call_ok(
            client,
            "get_examination",
            {"corpus_id": harbor_id, "examination_run_id": harbor_run["examination_run_id"]},
        )
        findings = mappings(harbor_exam["findings"])
        assert findings
        quotes = {
            citation["exact_quote"]
            for finding in findings
            for citation in mappings(finding["citations"])
        }
        assert quotes
        assert not any("Aurora Control Hub" in str(quote) for quote in quotes)

        denied_run = await call_err(
            client,
            "get_workflow_status",
            {"corpus_id": aurora.id, "workflow_run_id": harbor_run["id"]},
        )
        assert denied_run["code"] == "workflow_run_not_found"
        unknown = await call_err(
            client,
            "get_workflow_status",
            {"corpus_id": harbor_id, "workflow_run_id": uuid4()},
        )
        assert unknown["code"] == "workflow_run_not_found"
        harbor_items = await call_ok(
            client,
            "list_review_items",
            {"corpus_id": harbor_id, "review_session_id": harbor_run["review_session_id"]},
        )
        assert harbor_items["items"]
        cross_session = await call_err(
            client,
            "list_review_items",
            {
                "corpus_id": aurora.id,
                "review_session_id": UUID(str(harbor_run["review_session_id"])),
            },
        )
        assert cross_session["code"] == "review_session_not_found"
        for item in mappings(harbor_items["items"]):
            if item["review_required"] and item["review_status"] == "pending":
                await call_ok(
                    client,
                    "approve_review_item",
                    {
                        "corpus_id": harbor_id,
                        "review_session_id": harbor_run["review_session_id"],
                        "item_id": item["id"],
                    },
                )
        completed = await call_ok(
            client,
            "complete_review",
            {"corpus_id": harbor_id, "review_session_id": harbor_run["review_session_id"]},
        )
        assert completed["status"] == "completed"
        unpublished = await call_err(client, "get_current_register", {"corpus_id": harbor_id})
        assert unpublished["code"] == "publication_not_found"
        resumed = await call_ok(
            client,
            "resume_workflow",
            {"corpus_id": harbor_id, "workflow_run_id": harbor_run["id"]},
        )
        assert resumed["status"] == "completed"
        finished = await call_ok(
            client,
            "get_workflow_status",
            {"corpus_id": harbor_id, "workflow_run_id": harbor_run["id"]},
        )
        assert finished["run"]["status"] == "completed"
        published = await call_ok(
            client,
            "publish_register",
            {
                "corpus_id": harbor_id,
                "review_session_id": harbor_run["review_session_id"],
            },
        )
        assert published["status"] == "published"
        assert published["corpus_id"] == harbor_id
        current = await call_ok(client, "get_current_register", {"corpus_id": harbor_id})
        assert current["id"] == published["id"]
        cross_register = await call_err(
            client,
            "get_register",
            {
                "corpus_id": aurora.id,
                "publication_id": UUID(str(published["id"])),
            },
        )
        assert cross_register["code"] == "publication_not_found"


def _assert_no_leak(text: str, *sentinels: str) -> None:
    lowered = text.casefold()
    for sentinel in sentinels:
        assert sentinel not in text
        assert sentinel.casefold() not in lowered
    assert "traceback" not in lowered
    assert "pydantic" not in lowered
    assert "validation error" not in lowered
    assert "validationerror" not in lowered
    assert "runtimeerror" not in lowered


def _assert_raw_and_stderr_safe(
    parsed: ApplicationErrorCall,
    stderr: str,
    *sentinels: str,
) -> None:
    assert "raw_text" in parsed
    assert parsed["raw_text"]
    _assert_no_leak(parsed["raw_text"], *sentinels)
    _assert_no_leak(parsed["code"], *sentinels)
    _assert_no_leak(parsed["detail"], *sentinels)
    _assert_no_leak(parsed["action"], *sentinels)
    _assert_no_leak(stderr, *sentinels)


@pytest.mark.integration
@pytest.mark.mcp
async def test_mcp_stdio_unexpected_exception_does_not_leak_sentinels(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    from app.mcp_errors import (
        TEST_INJECT_FAILURE_ENV,
        TEST_INJECT_TOOL_ENV,
        TEST_INJECT_UNEXPECTED,
        TEST_SENTINEL_DSN,
        TEST_SENTINEL_SECRET,
        TEST_SENTINEL_SOURCE,
    )

    _phase02, storage = phase02_service
    del _phase02
    async with stdio_mcp_capturing_stderr(
        storage,
        extra_env={
            TEST_INJECT_FAILURE_ENV: TEST_INJECT_UNEXPECTED,
            TEST_INJECT_TOOL_ENV: "list_corpora",
        },
    ) as (client, err_path):
        leaked = await call_err(client, "list_corpora", {})
    stderr = err_path.read_text(encoding="utf-8")
    _assert_raw_and_stderr_safe(
        leaked,
        stderr,
        TEST_SENTINEL_SECRET,
        TEST_SENTINEL_SOURCE,
        TEST_SENTINEL_DSN,
    )
    assert leaked["code"] == "internal_error"


@pytest.mark.integration
@pytest.mark.mcp
async def test_mcp_stdio_oversized_comment_raw_content_is_controlled(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    _phase02, storage = phase02_service
    del _phase02
    oversized = "OVERSIZED_COMMENT_SENTINEL_" + ("x" * 2000)
    async with stdio_mcp_capturing_stderr(storage) as (client, err_path):
        comment_err = await call_err(
            client,
            "approve_review_item",
            {
                "corpus_id": uuid4(),
                "review_session_id": uuid4(),
                "item_id": uuid4(),
                "comment": oversized,
            },
        )
    stderr = err_path.read_text(encoding="utf-8")
    assert comment_err["code"] == "invalid_request"
    assert comment_err["detail"]
    assert comment_err["action"]
    assert oversized not in comment_err["raw_text"]
    assert oversized not in stderr
    _assert_raw_and_stderr_safe(comment_err, stderr, oversized)


@pytest.mark.integration
@pytest.mark.mcp
async def test_mcp_stdio_malformed_uuid_raw_content_is_controlled(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    _phase02, storage = phase02_service
    del _phase02
    malformed = "not-a-uuid-MALFORMED_UUID_SENTINEL"
    async with stdio_mcp_capturing_stderr(storage) as (client, err_path):
        uuid_err = await call_err(client, "get_corpus", {"corpus_id": malformed})
    stderr = err_path.read_text(encoding="utf-8")
    assert uuid_err["code"] == "invalid_request"
    assert uuid_err["detail"]
    assert uuid_err["action"]
    assert malformed not in uuid_err["raw_text"]
    assert malformed not in stderr
    _assert_raw_and_stderr_safe(uuid_err, stderr, malformed)


@pytest.mark.integration
@pytest.mark.mcp
async def test_mcp_stdio_response_validation_does_not_leak_sentinels(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
) -> None:
    from app.mcp_errors import (
        TEST_INJECT_FAILURE_ENV,
        TEST_INJECT_RESPONSE_VALIDATION,
        TEST_INJECT_TOOL_ENV,
        TEST_SENTINEL_DSN,
        TEST_SENTINEL_SECRET,
        TEST_SENTINEL_SOURCE,
    )

    _phase02, storage = phase02_service
    del _phase02
    async with stdio_mcp_capturing_stderr(
        storage,
        extra_env={
            TEST_INJECT_FAILURE_ENV: TEST_INJECT_RESPONSE_VALIDATION,
            TEST_INJECT_TOOL_ENV: "list_corpora",
        },
    ) as (client, err_path):
        leaked = await call_err(client, "list_corpora", {})
    stderr = err_path.read_text(encoding="utf-8")
    _assert_raw_and_stderr_safe(
        leaked,
        stderr,
        TEST_SENTINEL_SECRET,
        TEST_SENTINEL_SOURCE,
        TEST_SENTINEL_DSN,
    )
    assert leaked["code"] in {"internal_error", "invalid_request"}
    assert leaked["detail"]
    assert leaked["action"]
