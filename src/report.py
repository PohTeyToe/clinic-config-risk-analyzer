"""Formatted terminal output for conflict reports and rollout plans.

Uses simple ASCII formatting (dashes and pipes). No box-drawing characters.
"""

from __future__ import annotations

from .models import ClinicConfig, Conflict, FeatureChange, RolloutPlan

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _pad(text: str, width: int) -> str:
    """Left-align *text* in a field of *width* characters."""
    return text[:width].ljust(width)


def _header(title: str) -> str:
    """Return a section header with a line of dashes underneath."""
    line = "-" * len(title)
    return f"\n{title}\n{line}"


# ---------------------------------------------------------------------------
# Conflict report
# ---------------------------------------------------------------------------


def print_conflict_report(
    feature: FeatureChange,
    conflicts_by_clinic: dict[str, list[Conflict]],
    clinics: list[ClinicConfig] | None = None,
) -> None:
    """Print a complete conflict report to stdout.

    If *clinics* is provided, the province column will show the actual
    province code.  Otherwise it falls back to the config file name.
    """

    # Build province lookup from clinics if available.
    province_map: dict[str, str] = {}
    if clinics:
        for c in clinics:
            province_map[c.name] = c.province

    print(_header(f"Conflict Report: {feature.name}"))
    print(f"Version: {feature.version}")
    print(f"Changes: {len(feature.changes)}")
    print()

    # -- Summary --
    total_clinics = len(conflicts_by_clinic)
    all_conflicts = [c for lst in conflicts_by_clinic.values() for c in lst]
    breaking = sum(1 for c in all_conflicts if c.conflict_type == "breaking")
    behavioral = sum(1 for c in all_conflicts if c.conflict_type == "behavioral")
    cosmetic = sum(1 for c in all_conflicts if c.conflict_type == "cosmetic")

    print(f"Clinics affected: {total_clinics}")
    print(
        f"Total conflicts:  {len(all_conflicts)} "
        f"(breaking: {breaking}, behavioral: {behavioral}, cosmetic: {cosmetic})"
    )
    print()

    if not conflicts_by_clinic:
        print("No conflicts detected.")
        return

    # -- Summary table --
    col_name = 34
    col_prov = 8
    col_num = 10
    col_reason = 48

    hdr = (
        f"| {_pad('Clinic', col_name)} "
        f"| {_pad('Province', col_prov)} "
        f"| {_pad('Breaking', col_num)} "
        f"| {_pad('Behavioral', col_num)} "
        f"| {_pad('Cosmetic', col_num)} "
        f"| {_pad('Top Conflict Reason', col_reason)} |"
    )
    sep = "-" * len(hdr)

    print(sep)
    print(hdr)
    print(sep)

    for clinic_name in sorted(conflicts_by_clinic.keys()):
        clist = conflicts_by_clinic[clinic_name]
        b = sum(1 for c in clist if c.conflict_type == "breaking")
        bh = sum(1 for c in clist if c.conflict_type == "behavioral")
        co = sum(1 for c in clist if c.conflict_type == "cosmetic")

        prov_str = province_map.get(clinic_name, clist[0].clinic_file.split(".")[0])

        # Find most severe reason.
        top = sorted(clist, key=lambda x: -x.severity_score)[0]
        reason = top.reason[:col_reason]

        print(
            f"| {_pad(clinic_name, col_name)} "
            f"| {_pad(prov_str, col_prov)} "
            f"| {_pad(str(b), col_num)} "
            f"| {_pad(str(bh), col_num)} "
            f"| {_pad(str(co), col_num)} "
            f"| {_pad(reason, col_reason)} |"
        )

    print(sep)
    print()

    # -- Detail section --
    print(_header("Detailed Conflicts"))

    for clinic_name in sorted(conflicts_by_clinic.keys()):
        clist = conflicts_by_clinic[clinic_name]
        prov_str = province_map.get(clinic_name, "")
        prov_tag = f", {prov_str}" if prov_str else ""
        print(f"\n  {clinic_name} ({clist[0].clinic_file}{prov_tag})")
        for i, conflict in enumerate(clist, 1):
            sev = conflict.conflict_type.upper()
            print(f"    {i}. [{sev}] ({conflict.affected_dimension})")
            print(f"       {conflict.reason}")

    print()


# ---------------------------------------------------------------------------
# Rollout report
# ---------------------------------------------------------------------------


def print_rollout_report(plan: RolloutPlan) -> None:
    """Print a complete rollout plan to stdout."""

    print(_header(f"{plan.feature_name} -- Rollout Plan"))
    print(f"Total clinics: {plan.total_clinics}")
    print(f"Cohorts: {len(plan.cohorts)}")
    print()

    # -- Risk ranking table --
    col_name = 38
    col_score = 10
    col_cohort = 24

    hdr = (
        f"| {_pad('Clinic', col_name)} "
        f"| {_pad('Risk Score', col_score)} "
        f"| {_pad('Cohort', col_cohort)} |"
    )
    sep = "-" * len(hdr)

    # Build a lookup: clinic_name -> cohort_name.
    cohort_lookup: dict[str, str] = {}
    for cohort in plan.cohorts:
        for cname in cohort.clinics:
            cohort_lookup[cname] = cohort.name

    print(sep)
    print(hdr)
    print(sep)

    for cname in sorted(plan.risk_scores.keys(), key=lambda k: plan.risk_scores[k]):
        score = plan.risk_scores[cname]
        cohort_name = cohort_lookup.get(cname, "Unassigned")
        print(
            f"| {_pad(cname, col_name)} "
            f"| {_pad(f'{score:.1f}', col_score)} "
            f"| {_pad(cohort_name, col_cohort)} |"
        )

    print(sep)
    print()

    # -- Cohort details --
    for cohort in plan.cohorts:
        print(_header(cohort.name))
        print(f"  Risk range: {cohort.risk_range}")
        print(f"  Gate:       {cohort.gate}")
        print(f"  Clinics:    {', '.join(cohort.clinics)}")
        print()

        if cohort.test_cases:
            print("  Test Cases:")
            for i, tc in enumerate(cohort.test_cases, 1):
                print(f"    {i}. {tc['name']}")
                print(f"       {tc['description']}")
            print()
