from datetime import date, datetime, timezone
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo
import pytest

from autoharvest.models import HarvestTimeEntry
from autoharvest.overtime import (
    calculate_overtime_report,
    classify_overtime_task,
    parse_month_string,
    resolve_overtime_period,
)


def test_parse_month_string():
    # YYYY-MM
    assert parse_month_string("2026-10", 2026) == (2026, 10)
    assert parse_month_string("2025/05", 2026) == (2025, 5)

    # Numeric month
    assert parse_month_string("10", 2026) == (2026, 10)
    assert parse_month_string("3", 2026) == (2026, 3)

    # Month name
    assert parse_month_string("October", 2026) == (2026, 10)
    assert parse_month_string("october", 2026) == (2026, 10)
    assert parse_month_string("nov", 2026) == (2026, 11)
    assert parse_month_string("Jan", 2026) == (2026, 1)

    # Invalid
    with pytest.raises(ValueError):
        parse_month_string("invalid_month", 2026)

    with pytest.raises(ValueError):
        parse_month_string("13", 2026)


def test_resolve_overtime_period():
    tz = ZoneInfo("UTC")

    # Explicit since and until
    start, end, label = resolve_overtime_period(since="2026-05-01", until="2026-05-15", tz=tz)
    assert start == "2026-05-01"
    assert end == "2026-05-15"
    assert "2026-05-01 to 2026-05-15" in label

    # Specific month
    start, end, label = resolve_overtime_period(month="2026-10", tz=tz)
    assert start == "2026-10-01"
    assert end == "2026-10-31"
    assert label == "October 2026"

    # Last month
    start, end, label = resolve_overtime_period(last_month=True, tz=tz)
    assert start.endswith("-01")
    assert label != ""

    # This month default
    start, end, label = resolve_overtime_period(this_month=True, tz=tz)
    assert start.endswith("-01")
    assert "to date" in label


def test_classify_overtime_task():
    rates = {
        "inactive": 6.0,
        "active": 30.0,
        "out_of_hours": 30.0,
    }

    # Inactive
    cat, rate = classify_overtime_task("1st On Call - Inactive", "xOn Call InActive", rates)
    assert cat == "1st On Call - Inactive"
    assert rate == 6.0

    cat, rate = classify_overtime_task("2nd on call - Inactive", "xOn Call InActive", rates)
    assert cat == "1st On Call - Inactive"
    assert rate == 6.0

    # Active
    cat, rate = classify_overtime_task("1st On call - Active", "UK Support", rates)
    assert cat == "1st On Call - Active"
    assert rate == 30.0

    # Out of hours
    cat, rate = classify_overtime_task("Out of hours configuration", "UK Support", rates)
    assert cat == "Out of Hours Configuration"
    assert rate == 30.0

    # Fallback
    cat, rate = classify_overtime_task("General Maintenance", "Internal", rates)
    assert cat == "General Maintenance"
    assert rate == 30.0


def test_calculate_overtime_report():
    harvest_mock = MagicMock()

    entries = [
        HarvestTimeEntry(
            id=1,
            spent_date="2026-10-05",
            hours=15.0,
            notes="",
            project_id=1,
            project_name="xOn Call InActive",
            task_id=10,
            task_name="1st On Call - Inactive",
        ),
        HarvestTimeEntry(
            id=2,
            spent_date="2026-10-05",
            hours=1.0,
            notes="PG#1001 - Core - Alert",
            project_id=2,
            project_name="UK Support",
            task_id=20,
            task_name="1st On call - Active",
        ),
        HarvestTimeEntry(
            id=3,
            spent_date="2026-10-06",
            hours=0.5,
            notes="PG#1002 - Web - Alert",
            project_id=2,
            project_name="UK Support",
            task_id=20,
            task_name="1st On call - Active",
        ),
        HarvestTimeEntry(
            id=4,
            spent_date="2026-10-10",
            hours=8.0,
            notes="Volta Migration",
            project_id=2,
            project_name="UK Support",
            task_id=30,
            task_name="Out of hours configuration",
        ),
    ]
    harvest_mock.get_time_entries.return_value = entries

    rates = {"inactive": 6.0, "active": 30.0, "out_of_hours": 30.0}
    report = calculate_overtime_report(
        harvest_client=harvest_mock,
        start_date="2026-10-01",
        end_date="2026-10-31",
        period_label="October 2026",
        rates=rates,
        currency_symbol="£",
    )

    assert report.start_date == "2026-10-01"
    assert report.end_date == "2026-10-31"
    assert report.period_label == "October 2026"
    assert len(report.items) == 4

    # Total hours: 15.0 + 1.0 + 0.5 + 8.0 = 24.5 hrs
    assert report.total_hours == 24.5

    # Total earnings:
    # Inactive: 15.0 * 6.0 = £90.00
    # Active: 1.5 * 30.0 = £45.00
    # OOH: 8.0 * 30.0 = £240.00
    # Total: £375.00
    assert report.total_earned == 375.0

    assert len(report.categories) == 3
    # Check category summaries
    active_summary = next(c for c in report.categories if "Active" in c.category)
    assert active_summary.total_hours == 1.5
    assert active_summary.total_earned == 45.0
    assert active_summary.entry_count == 2

    inactive_summary = next(c for c in report.categories if "Inactive" in c.category)
    assert inactive_summary.total_hours == 15.0
    assert inactive_summary.total_earned == 90.0
    assert inactive_summary.entry_count == 1

    ooh_summary = next(c for c in report.categories if "Out of Hours" in c.category)
    assert ooh_summary.total_hours == 8.0
    assert ooh_summary.total_earned == 240.0
    assert ooh_summary.entry_count == 1
