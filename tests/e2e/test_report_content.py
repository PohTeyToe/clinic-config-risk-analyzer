"""E2E tests verifying the HTML report content renders correctly."""

import pytest


@pytest.mark.e2e
class TestReportContent:
    """Verify static content of the generated HTML report."""

    def test_title_contains_feature_name(self, report_page):
        title = report_page.title()
        assert "Prescribing Workflow Redesign" in title

    def test_summary_stat_cards_visible(self, report_page):
        stats = report_page.locator(".stat-card")
        assert stats.count() == 4  # breaking, behavioral, cosmetic, clinics

        # Each card should have a number and label.
        for i in range(stats.count()):
            card = stats.nth(i)
            assert card.locator(".number").is_visible()
            assert card.locator(".label").is_visible()

    def test_fifteen_clinic_cards_render(self, report_page):
        cards = report_page.locator(".clinic-card")
        assert cards.count() == 15

    def test_each_card_has_province_and_risk(self, report_page):
        cards = report_page.locator(".clinic-card")
        valid_provinces = {"AB", "BC", "ON"}

        for i in range(cards.count()):
            card = cards.nth(i)
            province = card.get_attribute("data-province")
            risk = card.get_attribute("data-risk")
            assert province in valid_provinces, f"Card {i} has invalid province: {province}"
            assert float(risk) >= 0, f"Card {i} has invalid risk: {risk}"

    def test_rollout_section_exists(self, report_page):
        rollout = report_page.locator(".rollout-section")
        assert rollout.is_visible()
        cohorts = report_page.locator(".cohort")
        assert cohorts.count() >= 2
