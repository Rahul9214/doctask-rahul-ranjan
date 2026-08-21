from pathlib import Path
from uuid import uuid4

import pytest
from helpers import fixture_upload, ingest_corpus, prepare_incremental_corpus
from mcp_helpers import call_err, call_ok, in_memory_mcp, mappings

from app.mcp_server import BUSINESS_TOOL_NAMES
from app.services import Phase02Service
from app.storage import LocalFileStorage


def _max_length(schema: object) -> int | None:
    if not isinstance(schema, dict):
        return None
    if isinstance(schema.get("maxLength"), int):
        return int(schema["maxLength"])
    for option in schema.get("anyOf") or []:
        if isinstance(option, dict) and isinstance(option.get("maxLength"), int):
            return int(option["maxLength"])
    return None


def _required(items: object) -> list[dict[str, object]]:
    return [item for item in mappings(items) if item["review_required"]]


@pytest.mark.integration
async def test_mcp_tool_discovery_schemas_and_business_operations(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    async with in_memory_mcp(phase02) as (client, _services):
        listed = await client.list_tools()
        names = {tool.name for tool in listed.tools}
        assert set(BUSINESS_TOOL_NAMES) <= names
        by_name = {tool.name: tool for tool in listed.tools}
        for name in BUSINESS_TOOL_NAMES:
            schema = by_name[name].input_schema
            assert schema.get("type") == "object"
            assert "properties" in schema
        edit_schema = by_name["edit_review_item"].input_schema
        required = set(edit_schema.get("required") or [])
        assert "edited_content" in required
        assert "reviewer_authored_acknowledged" in required
        approve_props = by_name["approve_review_item"].input_schema.get("properties") or {}
        assert "edited_content" not in approve_props
        assert _max_length(approve_props.get("comment")) == 2000
        reject_props = by_name["reject_review_item"].input_schema.get("properties") or {}
        assert "edited_content" not in reject_props
        assert _max_length(reject_props.get("comment")) == 2000
        edit_comment = (edit_schema.get("properties") or {}).get("comment")
        assert _max_length(edit_comment) == 2000
        edited_content = (edit_schema.get("properties") or {}).get("edited_content") or {}
        assert _max_length(edited_content) == 8000
        assert edited_content.get("minLength") == 1

        corpora = await call_ok(client, "list_corpora", {"name": "Aurora Control Hub"})
        assert len(corpora["corpora"]) == 1
        assert corpora["corpora"][0]["id"] == str(aurora.id)
        corpus = await call_ok(client, "get_corpus", {"corpus_id": aurora.id})
        assert corpus["name"] == "Aurora Control Hub"
        sources = await call_ok(client, "list_sources", {"corpus_id": aurora.id})
        assert {item["logical_name"] for item in sources["sources"]} >= {
            "Decision Log",
            "Project Charter",
        }

        missing = await call_err(client, "get_corpus", {"corpus_id": uuid4()})
        assert missing["code"] == "corpus_not_found"
        assert missing["action"]

        run = await call_ok(client, "start_workflow", {"corpus_id": aurora.id})
        assert run["status"] == "waiting_for_review"
        status = await call_ok(
            client,
            "get_workflow_status",
            {"corpus_id": aurora.id, "workflow_run_id": run["id"]},
        )
        assert status["run"]["current_stage"] == "wait_for_review"
        assert any(event["event_type"] == "waiting_for_review" for event in status["events"])
        understanding = await call_ok(
            client,
            "get_understanding",
            {"corpus_id": aurora.id, "analysis_run_id": run["analysis_run_id"]},
        )
        assert understanding["facts"]
        examination = await call_ok(
            client,
            "get_examination",
            {"corpus_id": aurora.id, "examination_run_id": run["examination_run_id"]},
        )
        assert examination["findings"]
        opened = await call_ok(
            client,
            "open_review",
            {"corpus_id": aurora.id, "examination_run_id": run["examination_run_id"]},
        )
        assert opened["created"] is False
        session_id = opened["session"]["id"]
        items = await call_ok(
            client,
            "list_review_items",
            {"corpus_id": aurora.id, "review_session_id": session_id},
        )
        required_items = _required(items["items"])
        evidenced = next(item for item in required_items if item["citations"])
        citation = mappings(evidenced["citations"])[0]
        assert citation["exact_quote"]
        assert citation["native_locator"]
        assert citation["source_version_id"]
        assert "score" not in citation
        assert evidenced["review_status"] == "pending"

        incomplete = await call_err(
            client,
            "complete_review",
            {"corpus_id": aurora.id, "review_session_id": session_id},
        )
        assert incomplete["code"] == "review_session_incomplete"

        approved = await call_ok(
            client,
            "approve_review_item",
            {
                "corpus_id": aurora.id,
                "review_session_id": session_id,
                "item_id": required_items[0]["id"],
                "comment": "Accept",
            },
        )
        assert approved["item"]["review_status"] == "approved"
        assert approved["decision"]["actor"] == "mcp"
        reject_target = required_items[1] if len(required_items) > 1 else required_items[0]
        rejected = await call_ok(
            client,
            "reject_review_item",
            {
                "corpus_id": aurora.id,
                "review_session_id": session_id,
                "item_id": reject_target["id"],
            },
        )
        assert rejected["item"]["review_status"] == "rejected"
        edit_target = required_items[-1]
        unacked = await call_err(
            client,
            "edit_review_item",
            {
                "corpus_id": aurora.id,
                "review_session_id": session_id,
                "item_id": edit_target["id"],
                "edited_content": "Reviewer-authored restatement.",
                "reviewer_authored_acknowledged": False,
            },
        )
        assert unacked["code"] == "reviewer_authored_acknowledgement_required"
        edited = await call_ok(
            client,
            "edit_review_item",
            {
                "corpus_id": aurora.id,
                "review_session_id": session_id,
                "item_id": edit_target["id"],
                "edited_content": "Reviewer-authored restatement.",
                "reviewer_authored_acknowledged": True,
            },
        )
        assert edited["item"]["review_status"] == "edited"
        assert edited["item"]["edited_content_is_reviewer_authored"] is True
        assert edited["decision"]["reviewer_authored_acknowledged"] is True

        remaining = await call_ok(
            client,
            "list_review_items",
            {"corpus_id": aurora.id, "review_session_id": session_id},
        )
        for item in mappings(remaining["items"]):
            if item["review_required"] and item["review_status"] == "pending":
                await call_ok(
                    client,
                    "approve_review_item",
                    {
                        "corpus_id": aurora.id,
                        "review_session_id": session_id,
                        "item_id": item["id"],
                    },
                )
        completed = await call_ok(
            client,
            "complete_review",
            {"corpus_id": aurora.id, "review_session_id": session_id},
        )
        assert completed["status"] == "completed"
        later = await call_err(
            client,
            "approve_review_item",
            {
                "corpus_id": aurora.id,
                "review_session_id": session_id,
                "item_id": required_items[0]["id"],
            },
        )
        assert later["code"] == "review_session_already_completed"

        finished = await call_ok(
            client,
            "resume_workflow",
            {"corpus_id": aurora.id, "workflow_run_id": run["id"]},
        )
        assert finished["status"] == "completed"
        again = await call_err(
            client,
            "resume_workflow",
            {"corpus_id": aurora.id, "workflow_run_id": run["id"]},
        )
        assert again["code"] == "workflow_run_already_completed"

        isolated = await call_err(
            client,
            "get_workflow_status",
            {"corpus_id": harbor.id, "workflow_run_id": run["id"]},
        )
        assert isolated["code"] == "workflow_run_not_found"
        wrong_item = await call_err(
            client,
            "approve_review_item",
            {
                "corpus_id": aurora.id,
                "review_session_id": session_id,
                "item_id": uuid4(),
            },
        )
        assert wrong_item["code"] in {
            "review_item_not_found",
            "review_session_already_completed",
        }


@pytest.mark.integration
async def test_mcp_incremental_evidence_and_stale_baseline(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
    tmp_path: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora, _incremental = await prepare_incremental_corpus(
        phase02, corpus_fixtures / "aurora-control-hub"
    )
    async with in_memory_mcp(phase02) as (client, _services):
        revision = await call_ok(client, "get_current_revision", {"corpus_id": aurora.id})
        changed = tmp_path / "decision-log.txt"
        source = (corpus_fixtures / "aurora-control-hub" / "decision-log.txt").read_text(
            encoding="utf-8"
        )
        changed.write_text(source.replace("2026-10-30", "2026-12-01"), encoding="utf-8")
        await phase02.ingest(
            corpus_id=aurora.id,
            logical_name="Decision Log",
            declared_format="txt",
            upload=fixture_upload(changed, "txt"),
        )
        created = await call_ok(
            client,
            "start_incremental_run",
            {"corpus_id": aurora.id, "baseline_revision_id": revision["id"]},
        )
        assert created["status"] == "completed"
        evidence = await call_ok(
            client,
            "get_incremental_evidence",
            {"corpus_id": aurora.id, "incremental_run_id": created["id"]},
        )
        assert evidence["status"] == "completed"
        assert evidence["evidence"]["full_rerun"] is False
        stale = await call_err(
            client,
            "start_incremental_run",
            {"corpus_id": aurora.id, "baseline_revision_id": revision["id"]},
        )
        assert stale["code"] == "stale_baseline"
        missing = await call_err(
            client,
            "get_incremental_evidence",
            {"corpus_id": aurora.id, "incremental_run_id": uuid4()},
        )
        assert missing["code"] == "incremental_run_not_found"
