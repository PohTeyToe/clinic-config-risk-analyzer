"""Conflict detection engine for the Clinic Configuration Risk Analyzer.

Compares each clinic configuration against every change in a feature release
and produces a list of conflicts categorised by severity.

Run directly:
    python -m src.conflict_detector features/prescribing_redesign.yaml
"""

from __future__ import annotations

from typing import Dict, List

from .models import Change, ClinicConfig, Conflict, FeatureChange


# ---------------------------------------------------------------------------
# Individual check functions -- each returns a (possibly empty) list of
# Conflict objects for ONE clinic / ONE change pair.
# ---------------------------------------------------------------------------

def check_province_mismatch(
    clinic: ClinicConfig,
    change: Change,
) -> List[Conflict]:
    """Flag when a change targets provinces that do not include this clinic."""
    conflicts: List[Conflict] = []
    provinces = change.affects_provinces

    if "all" in provinces:
        return conflicts

    if clinic.province not in provinces:
        # The change does not target this province at all -- behavioural
        # because the feature simply will not apply.
        conflicts.append(
            Conflict(
                clinic_name=clinic.name,
                clinic_file=clinic.file_name,
                change_description=change.description,
                conflict_type="behavioral",
                severity_score=3,
                reason=(
                    f"Change targets provinces {provinces} but clinic is in "
                    f"{clinic.province}. Feature behaviour may differ or not apply."
                ),
                affected_dimension=change.dimension,
            )
        )
        return conflicts

    # Province matches -- check if the change affects province-specific
    # billing or integrations that the clinic actually uses.
    if change.dimension == "billing" and change.field:
        if change.field in clinic.billing:
            conflicts.append(
                Conflict(
                    clinic_name=clinic.name,
                    clinic_file=clinic.file_name,
                    change_description=change.description,
                    conflict_type="breaking",
                    severity_score=10,
                    reason=(
                        f"Clinic uses province-specific billing type "
                        f"'{change.field}' which is modified by this change."
                    ),
                    affected_dimension=change.dimension,
                )
            )

    if change.dimension == "integrations" and change.field:
        if change.field in clinic.integrations:
            conflicts.append(
                Conflict(
                    clinic_name=clinic.name,
                    clinic_file=clinic.file_name,
                    change_description=change.description,
                    conflict_type="breaking",
                    severity_score=10,
                    reason=(
                        f"Clinic uses province-specific integration "
                        f"'{change.field}' which is modified by this change."
                    ),
                    affected_dimension=change.dimension,
                )
            )

    return conflicts


def check_missing_integration(
    clinic: ClinicConfig,
    change: Change,
) -> List[Conflict]:
    """Flag when a change requires integrations the clinic does not have."""
    conflicts: List[Conflict] = []
    if not change.requires_integrations:
        return conflicts

    missing = [i for i in change.requires_integrations if i not in clinic.integrations]
    if not missing:
        return conflicts

    # Only flag if the clinic actually uses affected modules or the
    # change dimension is something the clinic has enabled.
    has_affected_module = any(m in clinic.modules for m in change.requires_modules)
    uses_dimension = _clinic_uses_dimension(clinic, change)

    if has_affected_module or uses_dimension:
        conflicts.append(
            Conflict(
                clinic_name=clinic.name,
                clinic_file=clinic.file_name,
                change_description=change.description,
                conflict_type="breaking",
                severity_score=10,
                reason=(
                    f"Clinic is missing required integration(s) "
                    f"{missing} but uses affected module(s)/dimension."
                ),
                affected_dimension=change.dimension,
            )
        )

    return conflicts


def check_module_dependency(
    clinic: ClinicConfig,
    change: Change,
) -> List[Conflict]:
    """Flag when a change requires modules the clinic does not have."""
    conflicts: List[Conflict] = []
    if not change.requires_modules:
        return conflicts

    missing = [m for m in change.requires_modules if m not in clinic.modules]
    if not missing:
        return conflicts

    # If the change would force a dependency, that is breaking.
    if change.change_type in ("add", "modify") and _clinic_uses_dimension(clinic, change):
        conflicts.append(
            Conflict(
                clinic_name=clinic.name,
                clinic_file=clinic.file_name,
                change_description=change.description,
                conflict_type="breaking",
                severity_score=10,
                reason=(
                    f"Change forces dependency on module(s) {missing} "
                    f"which the clinic does not have enabled."
                ),
                affected_dimension=change.dimension,
            )
        )
    else:
        # Feature simply will not apply.
        conflicts.append(
            Conflict(
                clinic_name=clinic.name,
                clinic_file=clinic.file_name,
                change_description=change.description,
                conflict_type="behavioral",
                severity_score=3,
                reason=(
                    f"Clinic lacks module(s) {missing}; "
                    f"this change will not take effect."
                ),
                affected_dimension=change.dimension,
            )
        )

    return conflicts


def check_template_breakage(
    clinic: ClinicConfig,
    change: Change,
) -> List[Conflict]:
    """Flag when a change breaks templates the clinic uses."""
    conflicts: List[Conflict] = []
    if not change.breaks_templates:
        return conflicts

    # Gather every custom template name the clinic has.
    clinic_templates: List[str] = []
    for key in ("custom_note_stencils", "letter_stencils", "pdf_forms", "macros", "aliases"):
        clinic_templates.extend(clinic.templates.get(key, []))

    # Also include scribe templates if available.
    if clinic.scribe_settings and "templates" in clinic.scribe_settings:
        clinic_templates.extend(clinic.scribe_settings["templates"])

    matched = [t for t in change.breaks_templates if t in clinic_templates]
    if matched:
        conflicts.append(
            Conflict(
                clinic_name=clinic.name,
                clinic_file=clinic.file_name,
                change_description=change.description,
                conflict_type="breaking",
                severity_score=10,
                reason=(
                    f"Clinic uses template(s)/macro(s) {matched} "
                    f"that will break due to this change."
                ),
                affected_dimension=change.dimension,
            )
        )

    return conflicts


def check_role_permission_conflict(
    clinic: ClinicConfig,
    change: Change,
) -> List[Conflict]:
    """Flag when permission changes conflict with the clinic's role setup."""
    conflicts: List[Conflict] = []
    if not change.permission_changes:
        return conflicts

    for role, action in change.permission_changes.items():
        clinic_perms = clinic.role_permissions.get(role)

        if clinic_perms is None:
            # Role does not exist at this clinic.
            conflicts.append(
                Conflict(
                    clinic_name=clinic.name,
                    clinic_file=clinic.file_name,
                    change_description=change.description,
                    conflict_type="behavioral",
                    severity_score=3,
                    reason=(
                        f"Change modifies role '{role}' but clinic "
                        f"does not define that role."
                    ),
                    affected_dimension=change.dimension,
                )
            )
            continue

        # Check if the action adds a permission to a restrictive set.
        if action.startswith("add "):
            perm_name = action[4:].strip()
            if not clinic_perms:
                # Empty permission list -- very restrictive clinic.
                conflicts.append(
                    Conflict(
                        clinic_name=clinic.name,
                        clinic_file=clinic.file_name,
                        change_description=change.description,
                        conflict_type="behavioral",
                        severity_score=3,
                        reason=(
                            f"Change adds '{perm_name}' to role '{role}' but "
                            f"clinic has an empty permission set for that role, "
                            f"indicating a restrictive policy."
                        ),
                        affected_dimension=change.dimension,
                    )
                )
            elif perm_name not in clinic_perms and len(clinic_perms) < 5:
                # Small permission set suggests intentional restriction.
                conflicts.append(
                    Conflict(
                        clinic_name=clinic.name,
                        clinic_file=clinic.file_name,
                        change_description=change.description,
                        conflict_type="behavioral",
                        severity_score=3,
                        reason=(
                            f"Change adds '{perm_name}' to role '{role}'. "
                            f"Clinic has a restrictive permission set "
                            f"({len(clinic_perms)} permissions) -- new "
                            f"permission may conflict with clinic policy."
                        ),
                        affected_dimension=change.dimension,
                    )
                )

    return conflicts


def check_billing_incompatibility(
    clinic: ClinicConfig,
    change: Change,
) -> List[Conflict]:
    """Flag when a billing change affects billing types the clinic uses."""
    conflicts: List[Conflict] = []
    if change.dimension != "billing":
        return conflicts

    if not change.field:
        return conflicts

    if change.field not in clinic.billing:
        return conflicts

    if change.change_type == "remove":
        conflicts.append(
            Conflict(
                clinic_name=clinic.name,
                clinic_file=clinic.file_name,
                change_description=change.description,
                conflict_type="breaking",
                severity_score=10,
                reason=(
                    f"Billing type '{change.field}' is being removed "
                    f"but clinic actively uses it."
                ),
                affected_dimension=change.dimension,
            )
        )
    elif change.change_type in ("modify", "rename"):
        conflicts.append(
            Conflict(
                clinic_name=clinic.name,
                clinic_file=clinic.file_name,
                change_description=change.description,
                conflict_type="breaking",
                severity_score=10,
                reason=(
                    f"Billing type '{change.field}' is being modified; "
                    f"clinic uses this billing type and may need updates."
                ),
                affected_dimension=change.dimension,
            )
        )
    elif change.change_type == "add":
        # Adding a new billing code is cosmetic unless dependencies are missing.
        missing_int = [
            i for i in change.requires_integrations if i not in clinic.integrations
        ]
        if missing_int:
            conflicts.append(
                Conflict(
                    clinic_name=clinic.name,
                    clinic_file=clinic.file_name,
                    change_description=change.description,
                    conflict_type="behavioral",
                    severity_score=3,
                    reason=(
                        f"New billing code for '{change.field}' requires "
                        f"integration(s) {missing_int} that clinic lacks."
                    ),
                    affected_dimension=change.dimension,
                )
            )
        else:
            conflicts.append(
                Conflict(
                    clinic_name=clinic.name,
                    clinic_file=clinic.file_name,
                    change_description=change.description,
                    conflict_type="cosmetic",
                    severity_score=1,
                    reason=(
                        f"New billing code added for '{change.field}'; "
                        f"clinic may benefit but no action required."
                    ),
                    affected_dimension=change.dimension,
                )
            )

    return conflicts


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clinic_uses_dimension(clinic: ClinicConfig, change: Change) -> bool:
    """Return True if the clinic actively uses the dimension affected by the change."""
    dim = change.dimension
    if dim == "billing":
        return bool(change.field and change.field in clinic.billing)
    if dim == "integrations":
        return bool(change.field and change.field in clinic.integrations)
    if dim == "modules":
        return bool(change.field and change.field in clinic.modules)
    if dim == "scribe_settings":
        return "ava_scribe" in clinic.modules
    if dim == "autochart_settings":
        return "autochart" in clinic.modules
    if dim == "role_permissions":
        return bool(clinic.role_permissions)
    if dim == "scheduling":
        return bool(clinic.scheduling)
    if dim == "templates":
        return bool(clinic.templates)
    return False


# ---------------------------------------------------------------------------
# Main detection orchestrator
# ---------------------------------------------------------------------------

ALL_CHECKS = [
    check_province_mismatch,
    check_missing_integration,
    check_module_dependency,
    check_template_breakage,
    check_role_permission_conflict,
    check_billing_incompatibility,
]


def detect_conflicts(
    clinics: List[ClinicConfig],
    feature: FeatureChange,
) -> Dict[str, List[Conflict]]:
    """Run every check for every clinic/change pair.

    Returns a dict mapping clinic name to its list of Conflict objects.
    Only clinics with at least one conflict are included.
    """
    results: Dict[str, List[Conflict]] = {}

    for clinic in clinics:
        clinic_conflicts: List[Conflict] = []
        for change in feature.changes:
            for check_fn in ALL_CHECKS:
                clinic_conflicts.extend(check_fn(clinic, change))

        if clinic_conflicts:
            results[clinic.name] = clinic_conflicts

    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    from .models import load_all_clinics, load_feature
    from .report import print_conflict_report

    if len(sys.argv) < 2:
        print("Usage: python -m src.conflict_detector <feature_yaml>")
        sys.exit(1)

    feature_path = sys.argv[1]
    clinics = load_all_clinics()
    feature = load_feature(feature_path)
    conflicts = detect_conflicts(clinics, feature)
    print_conflict_report(feature, conflicts, clinics=clinics)
