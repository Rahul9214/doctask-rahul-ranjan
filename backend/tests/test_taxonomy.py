from app.taxonomy import FACT_CATEGORIES, INSPECTION_FIELDS, TAXONOMY_VERSION


def test_taxonomy_covers_required_assurance_categories() -> None:
    assert TAXONOMY_VERSION.startswith("software-project-assurance")
    assert "project_identity" in FACT_CATEGORIES
    assert "owner_accountability" in FACT_CATEGORIES
    assert "milestone_date" in FACT_CATEGORIES
    assert "status" in FACT_CATEGORIES
    assert "risk" in FACT_CATEGORIES
    assert "decision" in FACT_CATEGORIES
    assert "dependency" in FACT_CATEGORIES
    assert "control_assurance" in FACT_CATEGORIES
    keys = {field.subject_key for field in INSPECTION_FIELDS}
    assert "budget_owner" in keys
    assert "production_readiness" in keys
    assert "legacy_retirement" in keys
