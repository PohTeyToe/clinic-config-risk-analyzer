"""Integration tests running all features against all clinics.

Validates end-to-end behavior: loading configs, detecting conflicts,
generating rollout plans, and producing terminal reports.
"""

import io
import sys
from pathlib import Path

import pytest

from src.conflict_detector import detect_conflicts
from src.html_report import generate_html_report
from src.models import load_all_clinics, load_feature
from src.report import print_conflict_report, print_rollout_report
from src.rollout_planner import create_rollout_plan

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CLINICS_DIR = _PROJECT_ROOT / "configs" / "clinics"
_FEATURES_DIR = _PROJECT_ROOT / "features"

_FEATURE_FILES = sorted(f for f in _FEATURES_DIR.iterdir() if f.suffix in (".yaml", ".yml"))


@pytest.fixture(scope="module")
def all_clinics():
    return load_all_clinics(str(_CLINICS_DIR))


class TestEndToEndConflictDetection:
    """Run full conflict detection for every feature against all 15 clinics."""

    @pytest.mark.parametrize(
        "feature_path",
        _FEATURE_FILES,
        ids=[f.stem for f in _FEATURE_FILES],
    )
    def test_detect_conflicts(self, all_clinics, feature_path):
        feature = load_feature(str(feature_path))
        conflicts = detect_conflicts(all_clinics, feature)
        assert isinstance(conflicts, dict)
        # Every key should be a real clinic name.
        clinic_names = {c.name for c in all_clinics}
        for name in conflicts:
            assert name in clinic_names


class TestEndToEndRolloutPlan:
    """Generate rollout plans for every feature and verify structure."""

    @pytest.mark.parametrize(
        "feature_path",
        _FEATURE_FILES,
        ids=[f.stem for f in _FEATURE_FILES],
    )
    def test_rollout_plan(self, all_clinics, feature_path):
        feature = load_feature(str(feature_path))
        conflicts = detect_conflicts(all_clinics, feature)
        plan = create_rollout_plan(feature, all_clinics, conflicts)

        assert plan.total_clinics == 15
        assert len(plan.risk_scores) == 15
        assigned = []
        for cohort in plan.cohorts:
            assigned.extend(cohort.clinics)
        assert len(set(assigned)) == 15


class TestReportOutput:
    """Verify the terminal report functions produce output without crashing."""

    @pytest.mark.parametrize(
        "feature_path",
        _FEATURE_FILES,
        ids=[f.stem for f in _FEATURE_FILES],
    )
    def test_conflict_report(self, all_clinics, feature_path):
        feature = load_feature(str(feature_path))
        conflicts = detect_conflicts(all_clinics, feature)

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            print_conflict_report(feature, conflicts, clinics=all_clinics)
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        assert feature.name in output
        assert len(output) > 100

    @pytest.mark.parametrize(
        "feature_path",
        _FEATURE_FILES,
        ids=[f.stem for f in _FEATURE_FILES],
    )
    def test_rollout_report(self, all_clinics, feature_path):
        feature = load_feature(str(feature_path))
        conflicts = detect_conflicts(all_clinics, feature)
        plan = create_rollout_plan(feature, all_clinics, conflicts)

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            print_rollout_report(plan)
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        assert plan.feature_name in output
        assert "Cohort" in output


class TestHtmlReport:
    """Verify the HTML report generates correctly for each feature."""

    @pytest.mark.parametrize(
        "feature_path",
        _FEATURE_FILES,
        ids=[f.stem for f in _FEATURE_FILES],
    )
    def test_html_report_generation(self, all_clinics, feature_path, tmp_path):
        feature = load_feature(str(feature_path))
        out = tmp_path / "report.html"
        result = generate_html_report(feature, all_clinics, out)
        assert result.exists()
        html = result.read_text(encoding="utf-8")
        assert feature.name in html
        assert "clinic-card" in html
        # Should have all 15 clinics represented.
        assert html.count('class="clinic-card"') == 15
