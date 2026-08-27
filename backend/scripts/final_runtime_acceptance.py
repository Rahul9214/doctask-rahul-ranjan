"""Live HTTP acceptance against a running Compose/backend stack.

This is not a pytest module. It talks to BASE_URL (default http://localhost:8000)
and exercises Aurora then Harbor: ingest → workflow → mixed review → complete →
resume → usage → explicit publish → register inspect → cross-corpus denial.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = BACKEND_ROOT / "fixtures" / "corpora"
MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "markdown": "text/markdown",
    "txt": "text/plain",
}


def _require_json(response: httpx.Response, expected: int | set[int]) -> Any:
    allowed = {expected} if isinstance(expected, int) else expected
    if response.status_code not in allowed:
        raise SystemExit(
            f"{response.request.method} {response.request.url} -> "
            f"{response.status_code}: {response.text[:800]}"
        )
    if not response.content:
        return {}
    return response.json()


def _require(response: httpx.Response, expected: int | set[int]) -> dict[str, Any]:
    payload = _require_json(response, expected)
    if not isinstance(payload, dict):
        raise SystemExit(f"expected JSON object from {response.request.url}")
    return payload


def ingest_corpus(client: httpx.Client, corpus_dir: Path) -> dict[str, Any]:
    manifest = json.loads((corpus_dir / "manifest.json").read_text(encoding="utf-8"))
    corpus = _require(
        client.post(
            "/corpora",
            json={
                "name": f"{manifest['name']} {uuid4()}",
                "domain": manifest["domain"],
                "declared_formats": manifest["declared_formats"],
            },
        ),
        201,
    )
    for document in manifest["documents"]:
        path = corpus_dir / str(document["filename"])
        media = MEDIA_TYPES[str(document["declared_format"])]
        _require(
            client.post(
                f"/corpora/{corpus['id']}/sources",
                files={"file": (path.name, path.read_bytes(), media)},
                data={
                    "logical_name": document["logical_name"],
                    "declared_format": document["declared_format"],
                },
            ),
            201,
        )
    ensure_initial_revision(client, str(corpus["id"]))
    return corpus


def ensure_initial_revision(client: httpx.Client, corpus_id: str) -> None:
    current = client.get(f"/corpora/{corpus_id}/revisions/current")
    if current.status_code == 200:
        return
    payload = current.json() if current.content else {}
    if current.status_code != 404 or payload.get("code") != "corpus_revision_not_found":
        raise SystemExit(
            f"GET /corpora/{corpus_id}/revisions/current -> "
            f"{current.status_code}: {current.text[:800]}"
        )
    analysis = _require(client.post(f"/corpora/{corpus_id}/analysis-runs"), 201)
    if analysis.get("status") != "completed":
        raise SystemExit(f"Understand failed while creating the initial revision: {analysis}")
    examination = _require(
        client.post(f"/corpora/{corpus_id}/analysis-runs/{analysis['id']}/examination-runs"),
        201,
    )
    if examination.get("status") != "completed":
        raise SystemExit(f"Examine failed while creating the initial revision: {examination}")
    _require(
        client.post(
            f"/corpora/{corpus_id}/revisions",
            json={
                "analysis_run_id": analysis["id"],
                "examination_run_id": examination["id"],
            },
        ),
        201,
    )


def _validate_applied_semantics(
    published: dict[str, Any],
    *,
    rejected_rule_id: str | None = None,
) -> None:
    items = published.get("items")
    if not isinstance(items, list):
        raise SystemExit("published register items must be a JSON array")
    applied_rules = {str(item["rule_id"]) for item in items}
    rejected_rules = {str(item) for item in published["omitted_rejected_rule_ids"]}
    if rejected_rule_id is not None:
        if rejected_rule_id not in rejected_rules:
            raise SystemExit(
                f"actually rejected rule missing from omitted list: {rejected_rule_id}"
            )
        if rejected_rule_id in applied_rules:
            raise SystemExit(f"actually rejected rule was published: {rejected_rule_id}")
    if applied_rules & rejected_rules:
        raise SystemExit("rejected rules must not appear in published items")
    if any(item["review_status"] not in {"approved", "edited"} for item in items):
        raise SystemExit("only approved or edited items may be published")
    for item in items:
        if item["review_status"] == "approved" and (
            not item["system_grounded"] or item["reviewer_authored"]
        ):
            raise SystemExit("approved item authorship flags are invalid")
        if item["review_status"] == "edited" and (
            item["content_origin"] != "mixed"
            or item["system_grounded"]
            or not item["reviewer_authored"]
            or not item["reviewer_authored_acknowledged"]
            or not item["reviewer_authored_content"]
        ):
            raise SystemExit("edited item must be an acknowledged reviewer-authored overlay")


def _validate_usage(usage: dict[str, Any]) -> None:
    if usage.get("cost_basis") != "zero_deterministic":
        raise SystemExit("workflow usage cost_basis must be zero_deterministic")
    if usage.get("estimated_cost_usd") != 0.0:
        raise SystemExit("workflow usage estimated_cost_usd must be 0.0")


def _validate_aurora(published: dict[str, Any], rejected_rule_id: str | None) -> None:
    _validate_applied_semantics(published, rejected_rule_id=rejected_rule_id)
    if published["register_status"] != "populated":
        raise SystemExit("Aurora final register must be populated")
    readiness = next(
        (
            item
            for item in published["items"]
            if item["rule_id"] == "spa.milestone.production-readiness"
        ),
        None,
    )
    if readiness is None:
        raise SystemExit("Aurora production-readiness item must be published")
    citations = readiness["citations"]
    quotes = {str(citation["exact_quote"]) for citation in citations}
    if not any("2026-10-30" in quote for quote in quotes) or not any(
        "2026-11-14" in quote for quote in quotes
    ):
        raise SystemExit("Aurora must retain both grounded production-readiness quotes")
    source_names = {str(citation["source_logical_name"]) for citation in citations}
    expected_sources = {"Project Charter", "Weekly Status Report"}
    if not expected_sources.issubset(source_names):
        missing = sorted(expected_sources - source_names)
        raise SystemExit(f"Aurora production-readiness sources missing: {missing}")
    if not any(item["review_status"] == "edited" for item in published["items"]):
        raise SystemExit("Aurora live flow must publish a clearly marked reviewer edit")


def _validate_harbor(published: dict[str, Any], rejected_rule_id: str | None) -> None:
    _validate_applied_semantics(published, rejected_rule_id=rejected_rule_id)
    if published["register_status"] != "insufficient_evidence":
        raise SystemExit("Harbor must preserve insufficient_evidence")
    items = published["items"]
    if not items or any(item["outcome"] != "unknown" for item in items):
        raise SystemExit("Harbor applied content must remain UNKNOWN-only")
    if any(item["citations"] for item in items):
        raise SystemExit("Harbor UNKNOWN-only items must not fabricate citations")
    serialized = json.dumps(published)
    if any(
        marker in serialized
        for marker in (
            "Aurora Control Hub",
            "Elena Marlow",
            "Project Charter",
            "Weekly Status Report",
            "2026-10-30",
            "2026-11-14",
        )
    ):
        raise SystemExit("Harbor register contains Aurora evidence")


def publish_mixed_workflow(
    client: httpx.Client, corpus_id: str, *, expected_corpus: str
) -> dict[str, Any]:
    run = _require(client.post(f"/corpora/{corpus_id}/workflow-runs"), 201)
    if run["status"] != "waiting_for_review":
        raise SystemExit(f"expected waiting_for_review, got {run['status']}")
    session_id = run["review_session_id"]
    listed = _require_json(
        client.get(f"/corpora/{corpus_id}/review-sessions/{session_id}/items"),
        200,
    )
    if not isinstance(listed, list):
        raise SystemExit("review items response must be a JSON array")
    items = listed
    required = [item for item in items if item["review_required"]]
    if not required:
        raise SystemExit("workflow produced no required review items")
    readiness = next(
        (item for item in required if item["rule_id"] == "spa.milestone.production-readiness"),
        required[0],
    )
    reject_target = next((item for item in required if item["id"] != readiness["id"]), None)
    rejected_rule_id = str(reject_target["rule_id"]) if reject_target is not None else None
    edit_target = next(
        (
            item
            for item in reversed(required)
            if item["id"] not in {readiness["id"], reject_target["id"] if reject_target else ""}
        ),
        None,
    )
    _require(
        client.post(
            f"/corpora/{corpus_id}/review-sessions/{session_id}/items/{readiness['id']}/decisions",
            json={"action": "approve", "decision_source": "api"},
        ),
        201,
    )
    if reject_target is not None:
        _require(
            client.post(
                f"/corpora/{corpus_id}/review-sessions/{session_id}/items/{reject_target['id']}/decisions",
                json={"action": "reject", "decision_source": "api"},
            ),
            201,
        )
    if edit_target is not None:
        _require(
            client.post(
                f"/corpora/{corpus_id}/review-sessions/{session_id}/items/{edit_target['id']}/decisions",
                json={
                    "action": "edit",
                    "edited_content": "Reviewer-authored overlay, not system-grounded evidence.",
                    "reviewer_authored_acknowledged": True,
                    "decision_source": "api",
                },
            ),
            201,
        )
    remaining_payload = _require_json(
        client.get(f"/corpora/{corpus_id}/review-sessions/{session_id}/items"),
        200,
    )
    if not isinstance(remaining_payload, list):
        raise SystemExit("review items response must be a JSON array")
    remaining = remaining_payload
    for item in remaining:
        if item["review_required"] and item["review_status"] == "pending":
            _require(
                client.post(
                    f"/corpora/{corpus_id}/review-sessions/{session_id}/items/{item['id']}/decisions",
                    json={"action": "approve", "decision_source": "api"},
                ),
                201,
            )
    completed = _require(
        client.post(f"/corpora/{corpus_id}/review-sessions/{session_id}/complete"),
        200,
    )
    if completed["status"] != "completed":
        raise SystemExit(f"review did not complete: {completed}")
    resumed = _require(
        client.post(f"/corpora/{corpus_id}/workflow-runs/{run['id']}/resume"),
        200,
    )
    if resumed["status"] != "completed":
        raise SystemExit(f"workflow resume did not complete: {resumed}")
    usage = _require(client.get(f"/corpora/{corpus_id}/workflow-runs/{run['id']}/usage"), 200)
    _validate_usage(usage)
    unpublished = client.get(f"/corpora/{corpus_id}/register")
    if unpublished.status_code != 404:
        raise SystemExit("workflow completion must not auto-publish")
    published = _require(
        client.post(f"/corpora/{corpus_id}/review-sessions/{session_id}/publish"),
        201,
    )
    if expected_corpus == "aurora":
        _validate_aurora(published, rejected_rule_id)
    elif expected_corpus == "harbor":
        _validate_harbor(published, rejected_rule_id)
    else:
        raise SystemExit("unknown acceptance corpus")
    return {
        "corpus_id": corpus_id,
        "workflow_run_id": run["id"],
        "review_session_id": session_id,
        "publication_id": published["id"],
        "register_status": published["register_status"],
        "applied_count": published["applied_count"],
        "omitted_rejected_rule_ids": published["omitted_rejected_rule_ids"],
        "usage_cost_basis": usage["cost_basis"],
        "estimated_cost_usd": usage["estimated_cost_usd"],
        "version_identity": published["version_identity"],
    }


def main() -> None:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"
    with httpx.Client(base_url=base_url, timeout=120.0) as client:
        health = _require(client.get("/health"), 200)
        ready = _require(client.get("/ready"), 200)
        version = _require(client.get("/version"), 200)
        aurora = ingest_corpus(client, FIXTURES / "aurora-control-hub")
        harbor = ingest_corpus(client, FIXTURES / "harbor-ledger-modernization")
        aurora_pub = publish_mixed_workflow(client, aurora["id"], expected_corpus="aurora")
        harbor_pub = publish_mixed_workflow(client, harbor["id"], expected_corpus="harbor")
        current_aurora = _require(client.get(f"/corpora/{aurora['id']}/register"), 200)
        current_harbor = _require(client.get(f"/corpora/{harbor['id']}/register"), 200)
        if current_aurora["id"] != aurora_pub["publication_id"]:
            raise SystemExit("Aurora current register mismatch")
        if current_harbor["id"] != harbor_pub["publication_id"]:
            raise SystemExit("Harbor current register mismatch")
        if aurora_pub["publication_id"] == harbor_pub["publication_id"]:
            raise SystemExit("Aurora and Harbor publications must be distinct")
        cross_aurora = _require(
            client.get(f"/corpora/{harbor['id']}/register/{aurora_pub['publication_id']}"),
            404,
        )
        cross_harbor = _require(
            client.get(f"/corpora/{aurora['id']}/register/{harbor_pub['publication_id']}"),
            404,
        )
        if cross_aurora.get("code") != "publication_not_found":
            raise SystemExit("Aurora register through Harbor must return controlled not found")
        if cross_harbor.get("code") != "publication_not_found":
            raise SystemExit("Harbor register through Aurora must return controlled not found")
        summary = {
            "health": health,
            "ready_status": ready["status"],
            "app_version": version["app_version"],
            "current_phase": version["current_phase"],
            "aurora": aurora_pub,
            "harbor": harbor_pub,
            "cross_corpus_denied": True,
        }
        json.dump(summary, sys.stdout, indent=2)
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
