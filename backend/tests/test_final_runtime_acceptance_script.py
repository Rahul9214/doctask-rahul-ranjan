from collections.abc import Callable
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, cast

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "final_runtime_acceptance.py"
SPEC = spec_from_file_location("final_runtime_acceptance", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

_validate_applied_semantics = cast(
    Callable[..., None],
    MODULE._validate_applied_semantics,
)
_validate_usage = cast(
    Callable[[dict[str, Any]], None],
    MODULE._validate_usage,
)


def _published(*, applied_rule: str, omitted_rules: list[str]) -> dict[str, Any]:
    return {
        "omitted_rejected_rule_ids": omitted_rules,
        "items": [
            {
                "rule_id": applied_rule,
                "review_status": "approved",
                "system_grounded": True,
                "reviewer_authored": False,
            }
        ],
    }


@pytest.mark.parametrize(
    ("usage", "message"),
    [
        (
            {"cost_basis": "unavailable", "estimated_cost_usd": 0.0},
            "cost_basis must be zero_deterministic",
        ),
        (
            {"cost_basis": "zero_deterministic", "estimated_cost_usd": 0.01},
            "estimated_cost_usd must be 0.0",
        ),
    ],
)
def test_live_acceptance_rejects_non_deterministic_cost_contract(
    usage: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(SystemExit, match=message):
        _validate_usage(usage)


def test_live_acceptance_requires_actual_rejected_rule_in_omitted_list() -> None:
    with pytest.raises(SystemExit, match="actually rejected rule missing from omitted list"):
        _validate_applied_semantics(
            _published(applied_rule="spa.applied", omitted_rules=[]),
            rejected_rule_id="spa.rejected",
        )


def test_live_acceptance_forbids_actual_rejected_rule_in_applied_items() -> None:
    with pytest.raises(SystemExit, match="actually rejected rule was published"):
        _validate_applied_semantics(
            _published(applied_rule="spa.rejected", omitted_rules=["spa.rejected"]),
            rejected_rule_id="spa.rejected",
        )
