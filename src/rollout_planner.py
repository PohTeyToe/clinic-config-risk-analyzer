"""Rollout planner for the Clinic Configuration Risk Analyzer.

Takes the output of the conflict detector and produces a phased rollout
plan with risk-scored cohorts and clinic-specific test cases.

Run directly:
    python -m src.rollout_planner features/prescribing_redesign.yaml
"""

from __future__ import annotations

from .conflict_detector import detect_conflicts
from .models import (
    ClinicConfig,
    Conflict,
    FeatureChange,
    RolloutCohort,
    RolloutPlan,
)

# ---------------------------------------------------------------------------
# Risk scoring
# ---------------------------------------------------------------------------

COHORT_GATES = [
    "Zero critical bugs for 48 hours",
    "Zero critical bugs in Cohort 1 for 72 hours",
    "Zero critical bugs in Cohorts 1-2 for 72 hours, < 3 behavioral issues",
    "Full regression pass, zero critical bugs in Cohorts 1-3 for 1 week",
]

COHORT_NAMES = [
    "Cohort 1: Low Risk",
    "Cohort 2: Moderate Risk",
    "Cohort 3: High Risk",
    "Cohort 4: Critical",
]


def _count_custom_templates(clinic: ClinicConfig) -> int:
    """Count custom stencils, macros, and aliases."""
    total = 0
    for key in ("custom_note_stencils", "macros", "aliases"):
        total += len(clinic.templates.get(key, []))
    return total


def compute_risk_score(
    clinic: ClinicConfig,
    conflicts: list[Conflict],
) -> float:
    """Compute a numeric risk score for a clinic.

    Formula:
        (breaking * 10) + (behavioral * 3) + (cosmetic * 1)
        + (provider_count * 0.5)
        + (integration_count * 1)
        + (custom_template_count * 2)
    """
    breaking = sum(1 for c in conflicts if c.conflict_type == "breaking")
    behavioral = sum(1 for c in conflicts if c.conflict_type == "behavioral")
    cosmetic = sum(1 for c in conflicts if c.conflict_type == "cosmetic")

    score = (
        breaking * 10
        + behavioral * 3
        + cosmetic * 1
        + clinic.provider_count * 0.5
        + len(clinic.integrations) * 1
        + _count_custom_templates(clinic) * 2
    )

    return round(score, 1)


# ---------------------------------------------------------------------------
# Cohort assignment
# ---------------------------------------------------------------------------


def _assign_cohorts(
    scored: list[tuple[str, float]],
) -> list[list[str]]:
    """Split *scored* (sorted ascending by score) into 3-4 cohorts.

    Uses quartile boundaries.  If there are fewer than 4 clinics the
    number of cohorts is reduced so that each cohort has at least one
    clinic.
    """
    n = len(scored)
    if n == 0:
        return []

    num_cohorts = min(4, n) if n <= 4 else 4
    if num_cohorts == 4 and n < 8:
        num_cohorts = 3
    if num_cohorts == 3 and n < 3:
        num_cohorts = n

    cohorts: list[list[str]] = [[] for _ in range(num_cohorts)]

    for idx, (name, _score) in enumerate(scored):
        bucket = int(idx * num_cohorts / n)
        if bucket >= num_cohorts:
            bucket = num_cohorts - 1
        cohorts[bucket].append(name)

    return cohorts


# ---------------------------------------------------------------------------
# Test case generation
# ---------------------------------------------------------------------------


def _generate_test_cases(
    clinic: ClinicConfig,
    conflicts: list[Conflict],
) -> list[dict[str, str]]:
    """Generate 2-3 clinic-specific test cases based on conflicts and config."""
    cases: list[dict[str, str]] = []

    # Group conflicts by type for smarter case generation.
    breaking = [c for c in conflicts if c.conflict_type == "breaking"]
    behavioral = [c for c in conflicts if c.conflict_type == "behavioral"]

    # Case 1: always generate a basic smoke test referencing the clinic.
    billing_str = ", ".join(clinic.billing) if clinic.billing else "none"
    cases.append(
        {
            "name": f"Smoke test for {clinic.name}",
            "description": (
                f"Verify core workflows function after deployment at "
                f"{clinic.name} ({clinic.province}, {clinic.clinic_type}). "
                f"Confirm billing via {billing_str} processes correctly."
            ),
        }
    )

    # Case 2: test the most severe breaking conflict if any.
    if breaking:
        top = breaking[0]
        cases.append(
            {
                "name": f"Breaking change validation - {clinic.name}",
                "description": (
                    f"Validate the breaking change in '{top.affected_dimension}' "
                    f"at {clinic.name}: {top.reason} "
                    f"Integrations in use: {', '.join(clinic.integrations)}."
                ),
            }
        )

    # Case 3: test behavioral or integration-specific concerns.
    if behavioral:
        top = behavioral[0]
        cases.append(
            {
                "name": f"Behavioral change check - {clinic.name}",
                "description": (
                    f"Confirm behavioral change handling for "
                    f"'{top.affected_dimension}' at {clinic.name}: "
                    f"{top.reason}"
                ),
            }
        )
    elif len(clinic.integrations) > 2:
        integration_str = ", ".join(clinic.integrations)
        cases.append(
            {
                "name": f"Integration regression - {clinic.name}",
                "description": (
                    f"Run integration regression suite for {clinic.name} "
                    f"covering: {integration_str}."
                ),
            }
        )

    # Ensure we have at least 2 cases.
    if len(cases) < 2:
        templates_count = _count_custom_templates(clinic)
        cases.append(
            {
                "name": f"Template/macro validation - {clinic.name}",
                "description": (
                    f"Verify {templates_count} custom templates and macros "
                    f"render correctly at {clinic.name} after deployment."
                ),
            }
        )

    return cases[:3]


# ---------------------------------------------------------------------------
# Main planner
# ---------------------------------------------------------------------------


def create_rollout_plan(
    feature: FeatureChange,
    clinics: list[ClinicConfig],
    conflicts: dict[str, list[Conflict]],
) -> RolloutPlan:
    """Build a complete rollout plan from conflict analysis results."""

    # Build a lookup of clinics by name for easy access.
    clinic_map: dict[str, ClinicConfig] = {c.name: c for c in clinics}

    # Compute risk scores for every clinic (including those with 0 conflicts).
    risk_scores: dict[str, float] = {}
    for clinic in clinics:
        clinic_conflicts = conflicts.get(clinic.name, [])
        risk_scores[clinic.name] = compute_risk_score(clinic, clinic_conflicts)

    # Sort clinics by risk score ascending.
    sorted_clinics = sorted(risk_scores.items(), key=lambda x: x[1])

    # Assign to cohorts.
    cohort_lists = _assign_cohorts(sorted_clinics)

    cohorts: list[RolloutCohort] = []
    for i, clinic_names in enumerate(cohort_lists):
        if not clinic_names:
            continue

        scores_in_cohort = [risk_scores[n] for n in clinic_names]
        low = min(scores_in_cohort)
        high = max(scores_in_cohort)
        risk_range = f"{low:.1f} - {high:.1f}" if low != high else f"{low:.1f}"

        # Collect test cases for every clinic in this cohort.
        all_test_cases: list[dict[str, str]] = []
        for cname in clinic_names:
            clinic_conflicts = conflicts.get(cname, [])
            all_test_cases.extend(_generate_test_cases(clinic_map[cname], clinic_conflicts))

        cohorts.append(
            RolloutCohort(
                name=COHORT_NAMES[i],
                clinics=clinic_names,
                risk_range=risk_range,
                gate=COHORT_GATES[i],
                test_cases=all_test_cases,
            )
        )

    return RolloutPlan(
        feature_name=feature.name,
        total_clinics=len(clinics),
        cohorts=cohorts,
        risk_scores=risk_scores,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    from .models import load_all_clinics, load_feature
    from .report import print_rollout_report

    if len(sys.argv) < 2:
        print("Usage: python -m src.rollout_planner <feature_yaml>")
        sys.exit(1)

    feature_path = sys.argv[1]
    clinics = load_all_clinics()
    feature = load_feature(feature_path)
    conflicts = detect_conflicts(clinics, feature)
    plan = create_rollout_plan(feature, clinics, conflicts)
    print_rollout_report(plan)
