"""UK Payroll, Tax, and National Insurance calculation module."""
from __future__ import annotations

from typing import Optional

from autoharvest.models import EstimatedPayBreakdown

# Standard UK PAYE & Class 1 NI thresholds (Annual)
# Rates apply to England, Wales, and Northern Ireland
UK_PERSONAL_ALLOWANCE_ANNUAL = 12_570.0
UK_BASIC_RATE_LIMIT_ANNUAL = 50_270.0  # Basic rate band: £12,571 to £50,270 (width = £37,700)
UK_ADDITIONAL_RATE_LIMIT_ANNUAL = 125_140.0
UK_TAPER_THRESHOLD_ANNUAL = 100_000.0

UK_BASIC_RATE = 0.20
UK_HIGHER_RATE = 0.40
UK_ADDITIONAL_RATE = 0.45

# Class 1 Employee National Insurance (Annual equivalents)
UK_NI_PRIMARY_THRESHOLD_ANNUAL = 12_570.0
UK_NI_UPPER_EARNINGS_LIMIT_ANNUAL = 50_270.0
UK_NI_MAIN_RATE = 0.08  # 8% between PT and UEL
UK_NI_UPPER_RATE = 0.02  # 2% above UEL


def calculate_uk_income_tax_monthly(
    monthly_gross: float,
    annual_salary_estimate: Optional[float] = None,
) -> float:
    """
    Calculate estimated UK monthly Income Tax under standard PAYE.

    Thresholds are divided by 12 for monthly pay frequency.
    Handles personal allowance taper for incomes above £100,000.
    """
    if monthly_gross <= 0:
        return 0.0

    # Project annual income to determine personal allowance taper
    proj_annual = (
        annual_salary_estimate
        if annual_salary_estimate is not None
        else (monthly_gross * 12.0)
    )

    if proj_annual > UK_TAPER_THRESHOLD_ANNUAL:
        taper_reduction = min(
            UK_PERSONAL_ALLOWANCE_ANNUAL,
            (proj_annual - UK_TAPER_THRESHOLD_ANNUAL) * 0.5,
        )
        allowance_annual = max(0.0, UK_PERSONAL_ALLOWANCE_ANNUAL - taper_reduction)
    else:
        allowance_annual = UK_PERSONAL_ALLOWANCE_ANNUAL

    monthly_allowance = allowance_annual / 12.0
    basic_band_width = (
        UK_BASIC_RATE_LIMIT_ANNUAL - UK_PERSONAL_ALLOWANCE_ANNUAL
    ) / 12.0  # £3,141.67
    higher_band_width = (
        UK_ADDITIONAL_RATE_LIMIT_ANNUAL - UK_BASIC_RATE_LIMIT_ANNUAL
    ) / 12.0  # £6,239.17

    taxable_income = max(0.0, monthly_gross - monthly_allowance)
    if taxable_income <= 0:
        return 0.0

    # 1. Basic Rate (20%)
    taxable_basic = min(taxable_income, basic_band_width)
    tax = taxable_basic * UK_BASIC_RATE

    # 2. Higher Rate (40%)
    remainder = taxable_income - taxable_basic
    if remainder > 0:
        taxable_higher = min(remainder, higher_band_width)
        tax += taxable_higher * UK_HIGHER_RATE
        remainder -= taxable_higher

        # 3. Additional Rate (45%)
        if remainder > 0:
            tax += remainder * UK_ADDITIONAL_RATE

    return round(tax, 2)


def calculate_uk_national_insurance_monthly(monthly_gross: float) -> float:
    """
    Calculate estimated UK Class 1 Employee National Insurance on monthly earnings.

    - 0% up to Primary Threshold (£1,047.50 / month)
    - 8% from Primary Threshold to Upper Earnings Limit (£1,047.50 to £4,189.17 / month)
    - 2% above Upper Earnings Limit (> £4,189.17 / month)
    """
    if monthly_gross <= 0:
        return 0.0

    pt_monthly = UK_NI_PRIMARY_THRESHOLD_ANNUAL / 12.0
    uel_monthly = UK_NI_UPPER_EARNINGS_LIMIT_ANNUAL / 12.0

    if monthly_gross <= pt_monthly:
        return 0.0

    # Main rate (8%)
    ni_main_band = min(monthly_gross, uel_monthly) - pt_monthly
    ni = ni_main_band * UK_NI_MAIN_RATE

    # Upper rate (2%)
    if monthly_gross > uel_monthly:
        ni_upper_band = monthly_gross - uel_monthly
        ni += ni_upper_band * UK_NI_UPPER_RATE

    return round(ni, 2)


def calculate_estimated_pay(
    annual_salary: float,
    overtime_gross: float,
    currency_symbol: str = "£",
) -> EstimatedPayBreakdown:
    """
    Calculate estimated monthly take-home pay, comparing base salary vs overtime.

    Reconciles base monthly pay, marginal deductions on overtime, and overall monthly totals.
    """
    if annual_salary < 0:
        annual_salary = 0.0
    if overtime_gross < 0:
        overtime_gross = 0.0

    base_monthly_gross = round(annual_salary / 12.0, 2)
    total_monthly_gross = round(base_monthly_gross + overtime_gross, 2)

    # Base monthly tax and NI (without overtime)
    base_tax = calculate_uk_income_tax_monthly(
        base_monthly_gross, annual_salary_estimate=annual_salary
    )
    base_ni = calculate_uk_national_insurance_monthly(base_monthly_gross)
    base_net = round(base_monthly_gross - base_tax - base_ni, 2)

    # Total monthly tax and NI (with overtime)
    total_tax = calculate_uk_income_tax_monthly(
        total_monthly_gross, annual_salary_estimate=annual_salary + overtime_gross
    )
    total_ni = calculate_uk_national_insurance_monthly(total_monthly_gross)
    total_net = round(total_monthly_gross - total_tax - total_ni, 2)

    # Marginal overtime contribution
    overtime_tax = round(total_tax - base_tax, 2)
    overtime_ni = round(total_ni - base_ni, 2)
    overtime_net = round(overtime_gross - overtime_tax - overtime_ni, 2)

    return EstimatedPayBreakdown(
        annual_salary=annual_salary,
        base_monthly_gross=base_monthly_gross,
        overtime_gross=overtime_gross,
        total_monthly_gross=total_monthly_gross,
        base_tax=base_tax,
        base_ni=base_ni,
        base_net=base_net,
        overtime_tax=overtime_tax,
        overtime_ni=overtime_ni,
        overtime_net=overtime_net,
        total_tax=total_tax,
        total_ni=total_ni,
        total_net=total_net,
        currency_symbol=currency_symbol,
    )
