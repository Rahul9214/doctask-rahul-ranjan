from pathlib import Path
from uuid import uuid4

import pytest
from helpers import ingest_corpus, make_workflow
from mcp_helpers import call_err, call_ok, in_memory_mcp

from app.mcp_server import BUSINESS_TOOL_NAMES
from app.services import Phase02Service
from app.storage import LocalFileStorage

FORBIDDEN_TOOL_NAMES = {
    "shell",
    "bash",
    "exec",
    "execute",
    "run_command",
    "read_file",
    "write_file",
    "delete_file",
}


@pytest.mark.integration
@pytest.mark.adversarial
@pytest.mark.mcp
async def test_mcp_hostile_inputs_are_controlled_application_errors(
    phase02_service: tuple[Phase02Service, LocalFileStorage],
    corpus_fixtures: Path,
) -> None:
    phase02, _storage = phase02_service
    aurora = await ingest_corpus(phase02, corpus_fixtures / "aurora-control-hub")
    harbor = await ingest_corpus(phase02, corpus_fixtures / "harbor-ledger-modernization")
    workflow = make_workflow(phase02)
    run = await workflow.create_run(aurora.id)
    assert run.status == "waiting_for_review"
    assert run.review_session_id is not None

    async with in_memory_mcp(phase02) as (client, _services):
        listed = await client.list_tools()
        names = {tool.name for tool in listed.tools}
        assert set(BUSINESS_TOOL_NAMES) <= names
        assert names.isdisjoint(FORBIDDEN_TOOL_NAMES)

        malformed = await call_err(client, "get_corpus", {"corpus_id": "not-a-uuid"})
        assert malformed["code"] == "invalid_request"
        assert "not-a-uuid" not in malformed["raw_text"]
        assert "traceback" not in malformed["raw_text"].casefold()
        assert "pydantic" not in malformed["raw_text"].casefold()

        oversized_edit = await call_err(
            client,
            "edit_review_item",
            {
                "corpus_id": aurora.id,
                "review_session_id": run.review_session_id,
                "item_id": uuid4(),
                "edited_content": "x" * 8001,
                "reviewer_authored_acknowledged": True,
            },
        )
        assert oversized_edit["code"] == "invalid_request"
        assert "x" * 40 not in oversized_edit["raw_text"]

        wrong_corpus = await call_err(
            client,
            "get_workflow_status",
            {"corpus_id": harbor.id, "workflow_run_id": run.id},
        )
        assert wrong_corpus["code"] == "workflow_run_not_found"
        assert str(run.id) not in wrong_corpus["detail"]

        pending = await call_err(
            client,
            "complete_review",
            {"corpus_id": aurora.id, "review_session_id": run.review_session_id},
        )
        assert pending["code"] == "review_session_incomplete"

        items = await call_ok(
            client,
            "list_review_items",
            {"corpus_id": aurora.id, "review_session_id": run.review_session_id},
        )
        required = [item for item in items["items"] if item["review_required"]]
        for item in required:
            await call_ok(
                client,
                "approve_review_item",
                {
                    "corpus_id": aurora.id,
                    "review_session_id": run.review_session_id,
                    "item_id": item["id"],
                },
            )
        completed = await call_ok(
            client,
            "complete_review",
            {"corpus_id": aurora.id, "review_session_id": run.review_session_id},
        )
        assert completed["status"] == "completed"
        post = await call_err(
            client,
            "approve_review_item",
            {
                "corpus_id": aurora.id,
                "review_session_id": run.review_session_id,
                "item_id": required[0]["id"],
            },
        )
        assert post["code"] == "review_session_already_completed"
        finished = await call_ok(
            client,
            "resume_workflow",
            {"corpus_id": aurora.id, "workflow_run_id": run.id},
        )
        assert finished["status"] == "completed"
        again = await call_err(
            client,
            "resume_workflow",
            {"corpus_id": aurora.id, "workflow_run_id": run.id},
        )
        assert again["code"] == "workflow_run_already_completed"
        assert "traceback" not in again["raw_text"].casefold()
