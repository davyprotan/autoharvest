"""Unit tests for UK payroll, income tax, and national insurance calculations."""
from autoharvest.payroll import (
    calculate_estimated_pay,
    calculate_uk_income_tax_monthly,
    calculate_uk_national_insurance_monthly,
)


def test_calculate_uk_income_tax_monthly():
    # 1. Zero or negative
    assert calculate_uk_income_tax_monthly(0.0) == 0.0
    assert calculate_uk_income_tax_monthly(-500.0) == 0.0

    # 2. Below personal allowance (£1,047.50/mo)
    assert calculate_uk_income_tax_monthly(800.0) == 0.0
    assert calculate_uk_income_tax_monthly(1047.50) == 0.0

    # 3. Basic rate (20%)
    # Monthly gross = £3,000.00. Taxable = £3,000 - £1,047.50 = £1,952.50.
    # 20% of £1,952.50 = £390.50
    assert calculate_uk_income_tax_monthly(3000.0, annual_salary_estimate=36000.0) == 390.50

    # 4. Higher rate (40%)
    # Monthly gross = £5,000.00 (£60,000/yr).
    # Taxable = £5,000 - £1,047.50 = £3,952.50.
    # Basic band width = £3,141.67 -> tax = 3141.67 * 0.20 = £628.33
    # Higher band remainder = £3,952.50 - £3,141.67 = £810.83 -> tax = 810.83 * 0.40 = £324.33
    # Total = £628.333... + £324.333... = £952.666... -> £952.67
    assert calculate_uk_income_tax_monthly(5000.0, annual_salary_estimate=60000.0) == 952.67

    # 5. Personal allowance taper (> £100,000 annual)
    # Annual £110,000 -> excess £10,000 -> reduction £5,000 -> allowance £7,570 (£630.83/mo)
    tax_taper = calculate_uk_income_tax_monthly(9166.67, annual_salary_estimate=110000.0)
    assert tax_taper > 0.0


def test_calculate_uk_national_insurance_monthly():
    # 1. Zero or negative
    assert calculate_uk_national_insurance_monthly(0.0) == 0.0
    assert calculate_uk_national_insurance_monthly(-200.0) == 0.0

    # 2. Below primary threshold (£1,047.50/mo)
    assert calculate_uk_national_insurance_monthly(1000.0) == 0.0
    assert calculate_uk_national_insurance_monthly(1047.50) == 0.0

    # 3. Between primary threshold and upper earnings limit (8%)
    # Monthly gross = £3,000.00. Main band = £3,000 - £1,047.50 = £1,952.50.
    # 8% of £1,952.50 = £156.20
    assert calculate_uk_national_insurance_monthly(3000.0) == 156.20

    # 4. Above upper earnings limit (£4,189.17) (8% on main band, 2% above)
    # Monthly gross = £5,000.00.
    # Main band: (£4,189.17 - £1,047.50) * 0.08 = 3141.67 * 0.08 = £251.33
    # Upper band: (£5,000 - £4,189.17) * 0.02 = 810.83 * 0.02 = £16.22
    # Total = £251.33 + £16.22 = £267.55
    assert calculate_uk_national_insurance_monthly(5000.0) == 267.55


def test_calculate_estimated_pay_reconciliation():
    annual_salary = 48000.0  # £4,000/mo
    overtime_gross = 2352.0

    pay = calculate_estimated_pay(annual_salary=annual_salary, overtime_gross=overtime_gross)

    assert pay.annual_salary == 48000.0
    assert pay.base_monthly_gross == 4000.0
    assert pay.overtime_gross == 2352.0
    assert pay.total_monthly_gross == 6352.0

    # Verification: components must reconcile
    assert abs((pay.base_net + pay.overtime_net) - pay.total_net) <= 0.02
    assert abs((pay.base_tax + pay.overtime_tax) - pay.total_tax) <= 0.02
    assert abs((pay.base_ni + pay.overtime_ni) - pay.total_ni) <= 0.02

    # Overtime net must be positive and less than gross
    assert 0.0 < pay.overtime_net < pay.overtime_gross


def test_calculate_estimated_pay_zero_overtime():
    annual_salary = 36000.0
    pay = calculate_estimated_pay(annual_salary=annual_salary, overtime_gross=0.0)

    assert pay.overtime_gross == 0.0
    assert pay.overtime_tax == 0.0
    assert pay.overtime_ni == 0.0
    assert pay.overtime_net == 0.0
    assert pay.total_net == pay.base_net
