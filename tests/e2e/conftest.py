"""Playwright E2E test fixtures.

Generates an HTML report once per session and provides a navigated page
for each test.
"""

from pathlib import Path

import pytest

from src.html_report import generate_html_report
from src.models import load_all_clinics, load_feature

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_FEATURES_DIR = _PROJECT_ROOT / "features"
_REPORT_PATH = _PROJECT_ROOT / "test-results" / "e2e-report.html"


@pytest.fixture(scope="session")
def report_path():
    """Generate the HTML report once and return its path."""
    _REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    clinics = load_all_clinics(str(_PROJECT_ROOT / "configs" / "clinics"))
    feature = load_feature(str(_FEATURES_DIR / "prescribing_redesign.yaml"))
    generate_html_report(feature, clinics, _REPORT_PATH)
    return _REPORT_PATH


@pytest.fixture()
def report_page(page, report_path):
    """Navigate to the generated HTML report."""
    page.goto(report_path.as_uri())
    page.wait_for_load_state("domcontentloaded")
    return page
