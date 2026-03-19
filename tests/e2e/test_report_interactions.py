"""E2E tests verifying interactive features of the HTML report."""

import pytest


@pytest.mark.e2e
class TestProvinceFilter:
    """Test the province dropdown filter."""

    def test_filter_to_bc_shows_only_bc(self, report_page):
        report_page.select_option("#province-filter", "BC")
        report_page.wait_for_timeout(300)

        cards = report_page.locator(".clinic-card")
        for i in range(cards.count()):
            card = cards.nth(i)
            if card.is_visible():
                assert card.get_attribute("data-province") == "BC"

    def test_filter_to_all_shows_fifteen(self, report_page):
        # Filter to BC first, then back to all.
        report_page.select_option("#province-filter", "BC")
        report_page.wait_for_timeout(200)
        report_page.select_option("#province-filter", "all")
        report_page.wait_for_timeout(300)

        visible = report_page.locator(".clinic-card:visible")
        assert visible.count() == 15


@pytest.mark.e2e
class TestSorting:
    """Test the sort buttons."""

    def test_sort_by_risk_descending(self, report_page):
        report_page.click("#sort-risk-desc")
        report_page.wait_for_timeout(300)

        cards = report_page.locator(".clinic-card")
        risks = []
        for i in range(cards.count()):
            risks.append(float(cards.nth(i).get_attribute("data-risk")))
        # Should be descending.
        assert risks == sorted(risks, reverse=True)

    def test_sort_by_risk_ascending(self, report_page):
        report_page.click("#sort-risk-asc")
        report_page.wait_for_timeout(300)

        cards = report_page.locator(".clinic-card")
        risks = []
        for i in range(cards.count()):
            risks.append(float(cards.nth(i).get_attribute("data-risk")))
        assert risks == sorted(risks)

    def test_sort_by_name(self, report_page):
        report_page.click("#sort-name")
        report_page.wait_for_timeout(300)

        cards = report_page.locator(".clinic-card")
        names = []
        for i in range(cards.count()):
            names.append(cards.nth(i).get_attribute("data-name"))
        assert names == sorted(names)


@pytest.mark.e2e
class TestExpandCollapse:
    """Test clinic card expand/collapse."""

    def test_expand_shows_details(self, report_page):
        first_header = report_page.locator(".clinic-header").first
        first_details = report_page.locator(".clinic-details").first

        assert not first_details.is_visible()
        first_header.click()
        report_page.wait_for_timeout(200)
        assert first_details.is_visible()

    def test_collapse_hides_details(self, report_page):
        first_header = report_page.locator(".clinic-header").first
        first_details = report_page.locator(".clinic-details").first

        # Open then close.
        first_header.click()
        report_page.wait_for_timeout(200)
        first_header.click()
        report_page.wait_for_timeout(200)
        assert not first_details.is_visible()

    def test_expanded_card_has_conflict_table(self, report_page):
        first_header = report_page.locator(".clinic-header").first
        first_header.click()
        report_page.wait_for_timeout(200)

        first_details = report_page.locator(".clinic-details").first
        table = first_details.locator(".conflict-table")
        assert table.count() >= 1
