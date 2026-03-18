"""Tests for the conflict detection engine."""

from pathlib import Path

import pytest
import yaml

from src.conflict_detector import (
    check_billing_incompatibility,
    check_missing_integration,
    check_module_dependency,
    check_province_mismatch,
    check_template_breakage,
    detect_conflicts,
)
from src.models import (
    Change,
    FeatureChange,
    _fix_yaml_province,
    load_all_clinics,
    load_clinic,
    load_feature,
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
            "province" in c.reason.lower() or c.conflict_type == "behavioral" for c in conflicts
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


# ---------------------------------------------------------------------------
# YAML boolean province bug -- PyYAML 1.1 parses ON as True
# ---------------------------------------------------------------------------


class TestYamlBooleanProvinceBug:
    """PyYAML parses ON as True. Without handling this, every Ontario clinic
    would fail to load correctly. This test proves the fix works."""

    def test_on_parsed_as_true_fixed(self):
        raw = yaml.safe_load("province: ON")
        assert raw["province"] is True  # PyYAML quirk
        assert _fix_yaml_province(raw["province"]) == "ON"

    def test_no_parsed_as_false_fixed(self):
        raw = yaml.safe_load("province: NO")
        assert raw["province"] is False
        assert _fix_yaml_province(raw["province"]) == "NO"

    def test_normal_province_unchanged(self):
        raw = yaml.safe_load("province: BC")
        assert _fix_yaml_province(raw["province"]) == "BC"

    def test_ontario_clinics_load_correctly(self):
        clinics = load_all_clinics(str(_CLINICS_DIR))
        on_clinics = [c for c in clinics if c.province == "ON"]
        assert len(on_clinics) >= 1
        for c in on_clinics:
            assert c.province == "ON"
            assert isinstance(c.province, str)


# ---------------------------------------------------------------------------
# Scribe confidentiality + Connect auto-release interaction
# ---------------------------------------------------------------------------


class TestScribeConfidentialityConnectAutoRelease:
    """If a clinic has Scribe with confidential_toggle AND Connect with
    auto-release, the conflict detector should flag the interaction when a
    feature changes note flow. Confidential notes auto-releasing to the
    patient portal is a patient safety issue."""

    def test_confidential_auto_release_flagged(self):
        clinics = load_all_clinics(str(_CLINICS_DIR))
        feature = load_feature(str(_FEATURES_DIR / "connect_messaging_overhaul.yaml"))
        conflicts = detect_conflicts(clinics, feature)

        # Find clinics that have both scribe confidential_toggle=true
        # AND connect auto_release_days > 0.
        dual_clinics = [
            c
            for c in clinics
            if c.scribe_settings
            and c.scribe_settings.get("confidential_toggle") is True
            and c.connect_settings
            and c.connect_settings.get("auto_release_days", 0) > 0
        ]
        assert len(dual_clinics) >= 1, "Expected at least one clinic with both features"

        # Each of these clinics should have at least one conflict from the
        # connect_messaging_overhaul feature (which changes auto-release behavior).
        for clinic in dual_clinics:
            assert clinic.name in conflicts, (
                f"{clinic.name} has confidential toggle + auto-release but no conflicts"
            )


# ---------------------------------------------------------------------------
# All provinces parametrized
# ---------------------------------------------------------------------------


class TestAllProvincesParametrized:
    """Run province mismatch detection across all 15 real clinic configs."""

    @pytest.fixture()
    def all_clinics(self):
        return load_all_clinics(str(_CLINICS_DIR))

    @pytest.mark.parametrize("target_province", ["AB", "BC", "ON"])
    def test_province_mismatch_fires_correctly(self, all_clinics, target_province):
        change = Change(
            dimension="billing",
            field="test_billing",
            change_type="modify",
            description=f"Province-specific change for {target_province}",
            old_value="old",
            new_value="new",
            affects_provinces=[target_province],
            requires_modules=[],
            requires_integrations=[],
            breaks_templates=[],
            permission_changes=None,
        )
        for clinic in all_clinics:
            conflicts = check_province_mismatch(clinic, change)
            if clinic.province != target_province:
                assert len(conflicts) >= 1, (
                    f"{clinic.name} ({clinic.province}) should flag mismatch "
                    f"for {target_province}-only change"
                )
            else:
                # Same province -- no province mismatch conflict expected
                mismatch_conflicts = [c for c in conflicts if "province" in c.reason.lower()]
                # Province match means no "does not include this clinic" conflict
                assert not any(
                    "not" in c.reason.lower() and "province" in c.reason.lower()
                    for c in mismatch_conflicts
                )


# ---------------------------------------------------------------------------
# Billing change type severity mapping
# ---------------------------------------------------------------------------


class TestBillingChangeTypesSeverity:
    """Verify correct severity mapping for billing changes:
    remove/modify = breaking(10), add = cosmetic(1) or behavioral(3)."""

    @pytest.mark.parametrize(
        "change_type,expected_type,expected_score",
        [
            ("remove", "breaking", 10),
            ("modify", "breaking", 10),
            ("rename", "breaking", 10),
        ],
    )
    def test_destructive_billing_changes(self, change_type, expected_type, expected_score):
        clinic = load_clinic(str(_FIXTURES / "full_clinic.yaml"))
        change = Change(
            dimension="billing",
            field="ab_health",
            change_type=change_type,
            description=f"Billing {change_type} test",
            old_value="old",
            new_value="new",
            affects_provinces=["all"],
            requires_modules=[],
            requires_integrations=[],
            breaks_templates=[],
            permission_changes=None,
        )
        conflicts = check_billing_incompatibility(clinic, change)
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type == expected_type
        assert conflicts[0].severity_score == expected_score

    def test_add_billing_is_cosmetic(self):
        clinic = load_clinic(str(_FIXTURES / "full_clinic.yaml"))
        change = Change(
            dimension="billing",
            field="ab_health",
            change_type="add",
            description="Add new billing code",
            old_value=None,
            new_value="new_code",
            affects_provinces=["all"],
            requires_modules=[],
            requires_integrations=[],
            breaks_templates=[],
            permission_changes=None,
        )
        conflicts = check_billing_incompatibility(clinic, change)
        assert len(conflicts) >= 1
        assert conflicts[0].conflict_type == "cosmetic"
        assert conflicts[0].severity_score == 1


# ---------------------------------------------------------------------------
# Missing integration with no module overlap -- guard logic
# ---------------------------------------------------------------------------


class TestMissingIntegrationNoModuleOverlap:
    """When a change requires integrations the clinic lacks BUT the clinic
    does not use affected modules, no breaking conflict should fire."""

    def test_no_conflict_when_modules_unaffected(self):
        clinic = load_clinic(str(_FIXTURES / "simple_clinic.yaml"))
        # Simple clinic has ava_scribe only. Change requires prescribeit
        # integration AND autochart module (which simple clinic lacks).
        change = Change(
            dimension="autochart_settings",
            field="categories",
            change_type="modify",
            description="AutoChart upgrade requiring prescribeit",
            old_value="old",
            new_value="new",
            affects_provinces=["all"],
            requires_modules=["autochart"],
            requires_integrations=["prescribeit"],
            breaks_templates=[],
            permission_changes=None,
        )
        conflicts = check_missing_integration(clinic, change)
        # Clinic does not use autochart, so even though it lacks prescribeit,
        # the missing integration check should not fire as breaking.
        assert len(conflicts) == 0


# ---------------------------------------------------------------------------
# Malformed clinic YAML -- defensive negative tests
# ---------------------------------------------------------------------------


class TestMalformedClinicYaml:
    """In production, clinic configs could have missing fields or unusual values.
    These tests verify the system handles edge cases gracefully."""

    def test_empty_modules_list(self, tmp_path):
        config = tmp_path / "empty_modules.yaml"
        config.write_text(
            "name: Empty Modules Clinic\n"
            "province: AB\n"
            "clinic_type: family\n"
            "provider_count: 1\n"
            "providers: [MD]\n"
            "modules: []\n"
            "billing: [ab_health]\n"
            "integrations: []\n"
            "scheduling:\n"
            "  appointment_types: [standard_visit]\n"
            "role_permissions: {}\n"
            "templates: {}\n"
        )
        clinic = load_clinic(str(config))
        assert clinic.modules == []
        assert clinic.name == "Empty Modules Clinic"

    def test_missing_optional_fields(self, tmp_path):
        config = tmp_path / "minimal.yaml"
        config.write_text("name: Minimal Clinic\nprovince: BC\nclinic_type: solo\n")
        clinic = load_clinic(str(config))
        assert clinic.name == "Minimal Clinic"
        assert clinic.province == "BC"
        assert clinic.modules == []
        assert clinic.billing == []

    def test_detect_conflicts_with_empty_clinic(self, tmp_path):
        config = tmp_path / "bare.yaml"
        config.write_text("name: Bare Clinic\nprovince: AB\nclinic_type: family\n")
        clinic = load_clinic(str(config))
        feature = load_feature(str(_FIXTURES / "simple_feature.yaml"))
        # Should not crash even with minimal config.
        result = detect_conflicts([clinic], feature)
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# Conflict invariants across all real data
# ---------------------------------------------------------------------------


class TestConflictInvariants:
    """Run detect_conflicts with all real data and verify structural invariants
    on every conflict produced."""

    def test_all_conflicts_have_required_fields(self):
        clinics = load_all_clinics(str(_CLINICS_DIR))
        valid_types = {"breaking", "behavioral", "cosmetic"}
        valid_scores = {1, 3, 10}

        for feature_path in sorted(_FEATURES_DIR.iterdir()):
            if feature_path.suffix not in (".yaml", ".yml"):
                continue
            feature = load_feature(str(feature_path))
            conflicts = detect_conflicts(clinics, feature)

            for clinic_name, clinic_conflicts in conflicts.items():
                for c in clinic_conflicts:
                    assert c.clinic_name, "Empty clinic_name"
                    assert c.clinic_name == clinic_name
                    assert c.conflict_type in valid_types, (
                        f"Invalid conflict_type: {c.conflict_type}"
                    )
                    assert c.severity_score in valid_scores, (
                        f"Invalid severity_score: {c.severity_score}"
                    )
                    assert c.reason, "Empty reason"
                    assert c.affected_dimension, "Empty affected_dimension"
