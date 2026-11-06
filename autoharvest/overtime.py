from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from autoharvest.harvest import HarvestClient
from autoharvest.models import (
    HarvestTimeEntry,
    OvertimeCategorySummary,
    OvertimeItem,
    OvertimeReport,
)


def parse_month_string(month_str: str, default_year: int) -> tuple[int, int]:
    """
    Parse a month specification string into (year, month).
    Supports:
    - 'YYYY-MM' or 'YYYY/MM' (e.g. '2026-10')
    - 'MM' or 'M' (e.g. '10' or '5')
    - Month names or abbreviations (e.g. 'october', 'oct', 'nov')
    """
    s = month_str.strip().lower()

    # Case 1: YYYY-MM or YYYY/MM
    if "-" in s or "/" in s:
        sep = "-" if "-" in s else "/"
        parts = s.split(sep)
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            year, month = int(parts[0]), int(parts[1])
            if 1 <= month <= 12:
                return year, month

    # Case 2: Numeric month (1-12)
    if s.isdigit():
        month = int(s)
        if 1 <= month <= 12:
            return default_year, month

    # Case 3: Month name (e.g. October, Oct)
    month_names = {name.lower(): idx for idx, name in enumerate(calendar.month_name) if name}
    month_abbrs = {abbr.lower(): idx for idx, abbr in enumerate(calendar.month_abbr) if abbr}

    if s in month_names:
        return default_year, month_names[s]
    if s in month_abbrs:
        return default_year, month_abbrs[s]

    raise ValueError(
        f"Invalid month format: '{month_str}'. "
        "Use YYYY-MM (e.g. '2026-10'), month number (e.g. '10'), or month name (e.g. 'October')."
    )


def resolve_overtime_period(
    month: Optional[str] = None,
    last_month: bool = False,
    this_month: bool = False,
    since: Optional[str] = None,
    until: Optional[str] = None,
    tz: Optional[ZoneInfo] = None,
) -> tuple[str, str, str]:
    """
    Determine start date, end date, and descriptive label for an overtime query.
    Returns: (from_date 'YYYY-MM-DD', to_date 'YYYY-MM-DD', period_label).
    """
    target_tz = tz or ZoneInfo("UTC")
    today = datetime.now(target_tz).date()

    if since:
        from_date = since.strip()
        to_date = until.strip() if until else today.strftime("%Y-%m-%d")
        return from_date, to_date, f"{from_date} to {to_date}"

    if last_month:
        first_of_this_month = today.replace(day=1)
        last_day_of_last_month = first_of_this_month - timedelta(days=1)
        first_day_of_last_month = last_day_of_last_month.replace(day=1)
        return (
            first_day_of_last_month.strftime("%Y-%m-%d"),
            last_day_of_last_month.strftime("%Y-%m-%d"),
            first_day_of_last_month.strftime("%B %Y"),
        )

    if month:
        year, month_num = parse_month_string(month, default_year=today.year)
        last_day = calendar.monthrange(year, month_num)[1]
        start_d = date(year, month_num, 1)
        end_d = date(year, month_num, last_day)
        return (
            start_d.strftime("%Y-%m-%d"),
            end_d.strftime("%Y-%m-%d"),
            start_d.strftime("%B %Y"),
        )

    # Default / this_month
    first_of_this_month = today.replace(day=1)
    return (
        first_of_this_month.strftime("%Y-%m-%d"),
        today.strftime("%Y-%m-%d"),
        f"{today.strftime('%B %Y')} (to date)",
    )


def classify_overtime_task(
    task_name: str,
    project_name: Optional[str],
    rates: dict[str, float],
) -> tuple[str, float]:
    """
    Categorize a Harvest task and determine its hourly overtime rate.
    Default rates:
    - Inactive on-call: £6/hr
    - Active on-call: £30/hr
    - Out of hours configuration: £30/hr
    """
    t_lower = (task_name or "").lower().strip()
    rate_inactive = rates.get("inactive", 6.0)
    rate_active = rates.get("active", 30.0)
    rate_ooh = rates.get("out_of_hours", 30.0)

    if "inactive" in t_lower:
        return "1st On Call - Inactive", rate_inactive
    elif "out of hours" in t_lower or "ooh" in t_lower:
        return "Out of Hours Configuration", rate_ooh
    elif "active" in t_lower or "on call" in t_lower or "on-call" in t_lower:
        return "1st On Call - Active", rate_active
    else:
        # Fallback for other tasks (default active rate £30)
        return task_name, rate_active


def calculate_overtime_report(
    harvest_client: HarvestClient,
    start_date: str,
    end_date: str,
    period_label: str,
    rates: dict[str, float],
    currency_symbol: str = "£",
) -> OvertimeReport:
    """Fetch Harvest time entries for the period and compile an OvertimeReport."""
    entries = harvest_client.get_time_entries(from_date=start_date, to_date=end_date)
    # Sort entries chronologically by spent_date
    entries.sort(key=lambda e: (e.spent_date, e.id))

    items: list[OvertimeItem] = []
    category_buckets: dict[tuple[str, str, int, float], list[OvertimeItem]] = {}

    for entry in entries:
        tname = entry.task_name or f"Task {entry.task_id}"
        pname = entry.project_name or f"Project {entry.project_id}"
        category, rate = classify_overtime_task(tname, pname, rates)

        item = OvertimeItem(entry=entry, category=category, hourly_rate=rate)
        items.append(item)

        bucket_key = (category, pname, entry.task_id, rate)
        category_buckets.setdefault(bucket_key, []).append(item)

    summaries: list[OvertimeCategorySummary] = []
    for (category, pname, task_id, rate), bucket_items in category_buckets.items():
        cat_hours = sum(i.entry.hours for i in bucket_items)
        cat_earned = sum(i.total_earned for i in bucket_items)
        t_name = bucket_items[0].entry.task_name or str(task_id)
        summaries.append(
            OvertimeCategorySummary(
                category=category,
                project_name=pname,
                task_name=t_name,
                task_id=task_id,
                hourly_rate=rate,
                total_hours=cat_hours,
                total_earned=cat_earned,
                entry_count=len(bucket_items),
            )
        )

    # Sort categories: Active first, then Out of hours, then Inactive, then by earnings
    def sort_key(s: OvertimeCategorySummary) -> tuple[int, float]:
        name_lower = s.category.lower()
        if "active" in name_lower:
            rank = 1
        elif "out of hours" in name_lower:
            rank = 2
        elif "inactive" in name_lower:
            rank = 3
        else:
            rank = 4
        return (rank, -s.total_earned)

    summaries.sort(key=sort_key)

    total_hours = sum(i.entry.hours for i in items)
    total_earned = sum(i.total_earned for i in items)

    return OvertimeReport(
        start_date=start_date,
        end_date=end_date,
        period_label=period_label,
        items=items,
        categories=summaries,
        total_hours=total_hours,
        total_earned=total_earned,
        currency_symbol=currency_symbol,
    )
