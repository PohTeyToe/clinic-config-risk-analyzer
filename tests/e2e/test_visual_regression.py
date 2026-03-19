"""Visual regression tests -- capture screenshots as baselines."""

from pathlib import Path

import pytest

_SCREENSHOTS_DIR = Path(__file__).resolve().parent.parent.parent / "test-results" / "screenshots"


@pytest.fixture(autouse=True)
def _ensure_screenshots_dir():
    _SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)


@pytest.mark.e2e
class TestVisualRegression:
    """Capture screenshots for visual review and baseline comparison."""

    def test_full_report_screenshot(self, report_page):
        report_page.screenshot(path=str(_SCREENSHOTS_DIR / "full-report.png"), full_page=True)
        assert (_SCREENSHOTS_DIR / "full-report.png").exists()

    def test_filtered_bc_screenshot(self, report_page):
        report_page.select_option("#province-filter", "BC")
        report_page.wait_for_timeout(300)
        report_page.screenshot(path=str(_SCREENSHOTS_DIR / "filtered-bc.png"), full_page=True)
        assert (_SCREENSHOTS_DIR / "filtered-bc.png").exists()

    def test_expanded_clinic_screenshot(self, report_page):
        # Reset filter to all and sort by risk desc.
        report_page.select_option("#province-filter", "all")
        report_page.click("#sort-risk-desc")
        report_page.wait_for_timeout(300)

        # Expand the first (highest risk) clinic.
        first_header = report_page.locator(".clinic-header").first
        first_header.click()
        report_page.wait_for_timeout(300)

        report_page.screenshot(path=str(_SCREENSHOTS_DIR / "expanded-clinic.png"), full_page=True)
        assert (_SCREENSHOTS_DIR / "expanded-clinic.png").exists()
