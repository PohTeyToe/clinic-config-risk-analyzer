"""Tests for the conflict detection engine."""

from pathlib import Path

import pytest

from src.models import (
    Change,
    ClinicConfig,
    Conflict,
    FeatureChange,
    load_all_clinics,
    load_clinic,
    load_feature,
)
from src.conflict_detector import (
    check_billing_incompatibility,
    check_missing_integration,
    check_module_dependency,
    check_province_mismatch,
    check_template_breakage,
    detect_conflicts,
)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent
_FIXTURES = _THIS_DIR / "fixtures"
_PROJECT_ROOT = _THIS_DIR.parent
_CLINICS_DIR = _PROJECT_ROOT / "configs" / "clinics"
_FEATURES_DIR = _PROJECT_ROOT / "features"


# ---------------------------------------------------------------------------
# Loading fixtures
# ---------------------------------------------------------------------------

class TestLoadSimpleClinic:
    """Verify simple_clinic.yaml loads correctly."""

    def test_load_simple_clinic(self):
        clinic = load_clinic(str(_FIXTURES / "simple_clinic.yaml"))
        assert clinic.name == "Simple Test Clinic"
        assert clinic.province == "AB"
        assert clinic.clinic_type == "family"
        assert clinic.provider_count == 1
        assert clinic.providers == ["MD"]
        assert "ava_scribe" in clinic.modules
        assert "ab_health" in clinic.billing
        assert "netcare" in clinic.integrations
        assert "srfax" in clinic.integrations
        assert clinic.connect_settings is None
        assert clinic.autochart_settings is None


class TestLoadSimpleFeature:
    """Verify simple_feature.yaml loads correctly."""

    def test_load_simple_feature(self):
        feature = load_feature(str(_FIXTURES / "simple_feature.yaml"))
        assert feature.name == "Simple Test Feature"
        assert len(feature.changes) == 2
        assert feature.changes[0].dimension == "scribe_settings"
        assert feature.changes[1].dimension == "billing"


# ---------------------------------------------------------------------------
# Province filtering
# ---------------------------------------------------------------------------

class TestProvinceFiltering:
    """Changes targeting specific provinces should flag mismatches."""

    def test_province_filtering(self):
        bc_clinic = load_clinic(str(_FIXTURES / "bc_clinic.yaml"))
        # Create a change that only affects AB.
        ab_only_change = Change(
            dimension="billing",
            field="ab_health",
            change_type="modify",
            description="AB-only billing update",
            old_value="old",
            new_value="new",
            affects_provinces=["AB"],
            requires_modules=[],
            requires_integrations=[],
            breaks_templates=[],
            permission_changes=None,
        )
        conflicts = check_province_mismatch(bc_clinic, ab_only_change)
        assert len(conflicts) >= 1
        assert any(
            "province" in c.reason.lower() or c.conflict_type == "behavioral"
            for c in conflicts
        )


# ---------------------------------------------------------------------------
# Severity classification
# ---------------------------------------------------------------------------

class TestSeverityClassification:
    """Verify severity scores map correctly to conflict types."""

    def test_severity_classification(self):
        clinic = load_clinic(str(_FIXTURES / "full_clinic.yaml"))
        feature = load_feature(str(_FIXTURES / "simple_feature.yaml"))
        all_conflicts = detect_conflicts([clinic], feature)
        conflicts = all_conflicts.get(clinic.name, [])
        for c in conflicts:
            if c.conflict_type == "breaking":
                assert c.severity_score == 10
            elif c.conflict_type == "behavioral":
                assert c.severity_score == 3
            elif c.conflict_type == "cosmetic":
                assert c.severity_score == 1
            else:
                pytest.fail(f"Unknown conflict type: {c.conflict_type}")


# ---------------------------------------------------------------------------
# Zero conflicts
# ---------------------------------------------------------------------------

class TestZeroConflicts:
    """A feature that does not touch any clinic dimension produces no conflicts."""

    def test_zero_conflicts(self):
        clinic = load_clinic(str(_FIXTURES / "simple_clinic.yaml"))
        # Create a feature that touches a dimension/field the simple clinic
        # does not use, with no module or integration requirements, so
        # none of the conflict checks fire.
        feature = FeatureChange(
            name="No Conflict Feature",
            description="Targets a billing type the clinic does not use.",
            version="0.1",
            changes=[
                Change(
                    dimension="billing",
                    field="bc_msp",
                    change_type="modify",
                    description="Update BC MSP billing codes",
                    old_value="old",
                    new_value="new",
                    affects_provinces=["all"],
                    requires_modules=[],
                    requires_integrations=[],
                    breaks_templates=[],
                    permission_changes=None,
                ),
            ],
        )
        result = detect_conflicts([clinic], feature)
        # Simple clinic uses ab_health, not bc_msp. No modules or
        # integrations required. Province is "all" so no mismatch.
        # billing_incompatibility only fires if the clinic uses the
        # field. No templates broken, no permissions changed.
        assert clinic.name not in result


# ---------------------------------------------------------------------------
# Module dependency
# ---------------------------------------------------------------------------

class TestModuleDependency:
    """Feature requiring a module the clinic lacks should flag a conflict."""

    def test_module_dependency(self):
        clinic = load_clinic(str(_FIXTURES / "simple_clinic.yaml"))
        # Simple clinic has ava_scribe but NOT prescribeit.
        change = Change(
            dimension="scribe_settings",
            field="templates",
            change_type="add",
            description="Requires prescribeit module",
            old_value=None,
            new_value="new_template",
            affects_provinces=["all"],
            requires_modules=["prescribeit"],
            requires_integrations=[],
            breaks_templates=[],
            permission_changes=None,
        )
        conflicts = check_module_dependency(clinic, change)
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type in ("breaking", "behavioral")


# ---------------------------------------------------------------------------
# Template breakage
# ---------------------------------------------------------------------------

class TestTemplateBreakage:
    """Feature breaking a template the clinic uses should flag breaking conflict."""

    def test_template_breakage(self):
        clinic = load_clinic(str(_FIXTURES / "full_clinic.yaml"))
        # Full clinic has "soap_standard" in scribe_settings.templates.
        change = Change(
            dimension="scribe_settings",
            field="templates",
            change_type="rename",
            description="Rename medications field in scribe templates",
            old_value="medications",
            new_value="prescriptions_list",
            affects_provinces=["all"],
            requires_modules=["ava_scribe"],
            requires_integrations=[],
            breaks_templates=["soap_standard"],
            permission_changes=None,
        )
        conflicts = check_template_breakage(clinic, change)
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type == "breaking"
        assert conflicts[0].severity_score == 10


# ---------------------------------------------------------------------------
# Missing integration
# ---------------------------------------------------------------------------

class TestMissingIntegration:
    """Feature requiring an integration the clinic lacks should flag breaking."""

    def test_missing_integration(self):
        # BC clinic has pharmanet but NOT prescribeit.
        bc_clinic = load_clinic(str(_FIXTURES / "bc_clinic.yaml"))
        change = Change(
            dimension="integrations",
            field="prescribeit",
            change_type="modify",
            description="PrescribeIT v3 upgrade",
            old_value="v2",
            new_value="v3",
            affects_provinces=["all"],
            requires_modules=["autochart"],
            requires_integrations=["prescribeit"],
            breaks_templates=[],
            permission_changes=None,
        )
        # BC clinic has autochart module but lacks prescribeit integration.
        conflicts = check_missing_integration(bc_clinic, change)
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type == "breaking"
        assert conflicts[0].severity_score == 10


# ---------------------------------------------------------------------------
# Loading all real configs
# ---------------------------------------------------------------------------

class TestAllClinicsLoad:
    """All 15 real clinic YAML files should load without errors."""

    def test_all_clinics_load(self):
        clinics = load_all_clinics(str(_CLINICS_DIR))
        assert len(clinics) == 15
        for clinic in clinics:
            assert clinic.name
            assert clinic.province
            assert clinic.file_name.endswith(".yaml")


class TestAllFeaturesLoad:
    """All 3 real feature YAML files should load without errors."""

    def test_all_features_load(self):
        features = []
        for f in sorted(_FEATURES_DIR.iterdir()):
            if f.suffix in (".yaml", ".yml"):
                features.append(load_feature(str(f)))
        assert len(features) == 3
        for feature in features:
            assert feature.name
            assert len(feature.changes) > 0


# ---------------------------------------------------------------------------
# Full conflict detection against real data
# ---------------------------------------------------------------------------

class TestFullConflictDetection:
    """Run full conflict detection with all clinics and prescribing_redesign."""

    def test_full_conflict_detection(self):
        clinics = load_all_clinics(str(_CLINICS_DIR))
        feature = load_feature(str(_FEATURES_DIR / "prescribing_redesign.yaml"))
        conflicts = detect_conflicts(clinics, feature)

        # At least some clinics should have conflicts.
        assert len(conflicts) > 0

        # Collect all conflict types across all clinics.
        all_types = set()
        for clinic_conflicts in conflicts.values():
            for c in clinic_conflicts:
                all_types.add(c.conflict_type)

        # We expect at least breaking and behavioral conflicts.
        assert "breaking" in all_types
        assert "behavioral" in all_types
