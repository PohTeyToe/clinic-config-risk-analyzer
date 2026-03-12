"""Tests for the rollout planner."""

from pathlib import Path

import pytest

from src.models import (
    ClinicConfig,
    Conflict,
    FeatureChange,
    RolloutPlan,
    load_all_clinics,
    load_clinic,
    load_feature,
)
from src.conflict_detector import detect_conflicts
from src.rollout_planner import compute_risk_score, create_rollout_plan

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent
_FIXTURES = _THIS_DIR / "fixtures"
_PROJECT_ROOT = _THIS_DIR.parent
_CLINICS_DIR = _PROJECT_ROOT / "configs" / "clinics"
_FEATURES_DIR = _PROJECT_ROOT / "features"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_fixture_clinics_and_feature():
    """Load fixture clinics and the simple feature for testing."""
    clinics = [
        load_clinic(str(_FIXTURES / "simple_clinic.yaml")),
        load_clinic(str(_FIXTURES / "full_clinic.yaml")),
        load_clinic(str(_FIXTURES / "bc_clinic.yaml")),
    ]
    feature = load_feature(str(_FIXTURES / "simple_feature.yaml"))
    return clinics, feature


def _make_plan_from_fixtures():
    """Build a rollout plan from fixture data."""
    clinics, feature = _load_fixture_clinics_and_feature()
    conflicts = detect_conflicts(clinics, feature)
    return create_rollout_plan(feature, clinics, conflicts), clinics, conflicts


# ---------------------------------------------------------------------------
# Risk scores
# ---------------------------------------------------------------------------

class TestRiskScoreNonnegative:
    """All risk scores must be non-negative."""

    def test_risk_score_nonnegative(self):
        plan, clinics, conflicts = _make_plan_from_fixtures()
        for name, score in plan.risk_scores.items():
            assert score >= 0, f"Risk score for {name} is negative: {score}"


# ---------------------------------------------------------------------------
# All clinics assigned
# ---------------------------------------------------------------------------

class TestAllClinicsAssigned:
    """Every clinic should appear in exactly one cohort."""

    def test_all_clinics_assigned(self):
        plan, clinics, _ = _make_plan_from_fixtures()
        assigned = []
        for cohort in plan.cohorts:
            assigned.extend(cohort.clinics)
        clinic_names = [c.name for c in clinics]
        for name in clinic_names:
            assert name in assigned, f"Clinic {name} not in any cohort"
        # No duplicates.
        assert len(assigned) == len(set(assigned)), "Duplicate clinic in cohorts"


# ---------------------------------------------------------------------------
# Cohort ordering
# ---------------------------------------------------------------------------

class TestCohortOrdering:
    """Earlier cohorts should have lower or equal max risk scores."""

    def test_cohort_ordering(self):
        plan, _, _ = _make_plan_from_fixtures()
        if len(plan.cohorts) < 2:
            pytest.skip("Not enough cohorts to compare ordering")
        for i in range(len(plan.cohorts) - 1):
            current_scores = [
                plan.risk_scores[c] for c in plan.cohorts[i].clinics
            ]
            next_scores = [
                plan.risk_scores[c] for c in plan.cohorts[i + 1].clinics
            ]
            assert max(current_scores) <= max(next_scores), (
                f"Cohort {i} max score ({max(current_scores)}) > "
                f"Cohort {i+1} max score ({max(next_scores)})"
            )


# ---------------------------------------------------------------------------
# Test case specificity
# ---------------------------------------------------------------------------

class TestTestCaseSpecificity:
    """Test cases should reference actual clinic names and specific details."""

    def test_test_case_specificity(self):
        plan, clinics, _ = _make_plan_from_fixtures()
        clinic_names = {c.name for c in clinics}
        for cohort in plan.cohorts:
            for test_case in cohort.test_cases:
                assert "name" in test_case
                assert "description" in test_case
                # Each test case name or description should mention at least
                # one actual clinic name.
                mentions_clinic = any(
                    cname in test_case["name"] or cname in test_case["description"]
                    for cname in clinic_names
                )
                assert mentions_clinic, (
                    f"Test case '{test_case['name']}' does not reference "
                    f"any actual clinic name"
                )


# ---------------------------------------------------------------------------
# Zero-conflict clinics
# ---------------------------------------------------------------------------

class TestZeroConflictClinics:
    """Clinics with zero conflicts should still appear in the plan (cohort 1)."""

    def test_zero_conflict_clinics(self):
        clinics, feature = _load_fixture_clinics_and_feature()
        conflicts = detect_conflicts(clinics, feature)
        plan = create_rollout_plan(feature, clinics, conflicts)

        # Find clinics with no conflicts.
        zero_conflict_names = [
            c.name for c in clinics if c.name not in conflicts
        ]

        # All zero-conflict clinics must be in the plan.
        all_assigned = []
        for cohort in plan.cohorts:
            all_assigned.extend(cohort.clinics)
        for name in zero_conflict_names:
            assert name in all_assigned, (
                f"Zero-conflict clinic {name} missing from plan"
            )


# ---------------------------------------------------------------------------
# Rollout plan structure
# ---------------------------------------------------------------------------

class TestRolloutPlanStructure:
    """The plan object should have all required fields."""

    def test_rollout_plan_structure(self):
        plan, clinics, _ = _make_plan_from_fixtures()
        assert isinstance(plan, RolloutPlan)
        assert isinstance(plan.feature_name, str)
        assert plan.feature_name
        assert isinstance(plan.total_clinics, int)
        assert plan.total_clinics == len(clinics)
        assert isinstance(plan.cohorts, list)
        assert len(plan.cohorts) >= 1
        assert isinstance(plan.risk_scores, dict)
        assert len(plan.risk_scores) == len(clinics)
        for cohort in plan.cohorts:
            assert cohort.name
            assert isinstance(cohort.clinics, list)
            assert len(cohort.clinics) >= 1
            assert cohort.risk_range
            assert cohort.gate


# ---------------------------------------------------------------------------
# Full rollout plan with real data
# ---------------------------------------------------------------------------

class TestFullRolloutPlan:
    """Generate a full plan from all real clinics and prescribing_redesign."""

    def test_full_rollout_plan(self):
        clinics = load_all_clinics(str(_CLINICS_DIR))
        feature = load_feature(str(_FEATURES_DIR / "prescribing_redesign.yaml"))
        conflicts = detect_conflicts(clinics, feature)
        plan = create_rollout_plan(feature, clinics, conflicts)

        assert plan.feature_name == "Prescribing Workflow Redesign"
        assert plan.total_clinics == 15
        assert len(plan.cohorts) >= 2
        assert len(plan.risk_scores) == 15

        # Every clinic accounted for.
        all_assigned = []
        for cohort in plan.cohorts:
            all_assigned.extend(cohort.clinics)
        assert len(all_assigned) == 15
        assert len(set(all_assigned)) == 15
