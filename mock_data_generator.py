from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz
import pandas as pd


DEMO_TAX_PROFILE = {
    "employee_name": "Aarav Mehta",
    "financial_year": "2025-26",
    "gross_salary": 1_650_000.0,
    "section_80c": 90_000.0,
    "section_80d": 18_000.0,
    "hra_exemption": 140_000.0,
    "standard_deduction": 50_000.0,
    "employer_nps": 0.0,
    "current_regime": "old",
}

DEMO_TRANSACTIONS = [
    {
        "date": "2022-06-10",
        "folio_number": "11223344/01",
        "isin": "INF846K01W80",
        "fund_name": "Axis Bluechip Fund Regular Growth",
        "transaction_type": "Purchase",
        "amount": 100_000.0,
        "units": 1_788.909,
        "nav": 55.90,
        "plan_type": "Regular",
    },
    {
        "date": "2023-06-10",
        "folio_number": "11223344/01",
        "isin": "INF846K01W80",
        "fund_name": "Axis Bluechip Fund Regular Growth",
        "transaction_type": "Purchase",
        "amount": 50_000.0,
        "units": 806.452,
        "nav": 62.00,
        "plan_type": "Regular",
    },
    {
        "date": "2024-06-10",
        "folio_number": "11223344/01",
        "isin": "INF846K01W80",
        "fund_name": "Axis Bluechip Fund Regular Growth",
        "transaction_type": "Purchase",
        "amount": 75_000.0,
        "units": 1_119.403,
        "nav": 67.00,
        "plan_type": "Regular",
    },
    {
        "date": "2025-06-10",
        "folio_number": "11223344/01",
        "isin": "INF846K01W80",
        "fund_name": "Axis Bluechip Fund Regular Growth",
        "transaction_type": "Purchase",
        "amount": 50_000.0,
        "units": 706.214,
        "nav": 70.80,
        "plan_type": "Regular",
    },
    {
        "date": "2026-01-10",
        "folio_number": "11223344/01",
        "isin": "INF846K01W80",
        "fund_name": "Axis Bluechip Fund Regular Growth",
        "transaction_type": "Purchase",
        "amount": 25_000.0,
        "units": 347.913,
        "nav": 71.86,
        "plan_type": "Regular",
    },
    {
        "date": "2022-08-15",
        "folio_number": "55667788/02",
        "isin": "INF179K01542",
        "fund_name": "HDFC Hybrid Equity Fund Regular Growth",
        "transaction_type": "Purchase",
        "amount": 75_000.0,
        "units": 1_153.846,
        "nav": 65.00,
        "plan_type": "Regular",
    },
    {
        "date": "2023-08-15",
        "folio_number": "55667788/02",
        "isin": "INF179K01542",
        "fund_name": "HDFC Hybrid Equity Fund Regular Growth",
        "transaction_type": "Purchase",
        "amount": 50_000.0,
        "units": 689.655,
        "nav": 72.50,
        "plan_type": "Regular",
    },
    {
        "date": "2024-08-15",
        "folio_number": "55667788/02",
        "isin": "INF179K01542",
        "fund_name": "HDFC Hybrid Equity Fund Regular Growth",
        "transaction_type": "Purchase",
        "amount": 40_000.0,
        "units": 500.000,
        "nav": 80.00,
        "plan_type": "Regular",
    },
    {
        "date": "2025-08-15",
        "folio_number": "55667788/02",
        "isin": "INF179K01542",
        "fund_name": "HDFC Hybrid Equity Fund Regular Growth",
        "transaction_type": "Purchase",
        "amount": 30_000.0,
        "units": 357.143,
        "nav": 84.00,
        "plan_type": "Regular",
    },
    {
        "date": "2021-09-01",
        "folio_number": "99887766/03",
        "isin": "INF879O01027",
        "fund_name": "Parag Parikh Flexi Cap Fund Regular Growth",
        "transaction_type": "Purchase",
        "amount": 150_000.0,
        "units": 2_142.857,
        "nav": 70.00,
        "plan_type": "Regular",
    },
    {
        "date": "2022-09-01",
        "folio_number": "99887766/03",
        "isin": "INF879O01027",
        "fund_name": "Parag Parikh Flexi Cap Fund Regular Growth",
        "transaction_type": "Purchase",
        "amount": 75_000.0,
        "units": 937.500,
        "nav": 80.00,
        "plan_type": "Regular",
    },
    {
        "date": "2024-09-01",
        "folio_number": "99887766/03",
        "isin": "INF879O01027",
        "fund_name": "Parag Parikh Flexi Cap Fund Regular Growth",
        "transaction_type": "Purchase",
        "amount": 50_000.0,
        "units": 588.235,
        "nav": 85.00,
        "plan_type": "Regular",
    },
    {
        "date": "2025-09-01",
        "folio_number": "99887766/03",
        "isin": "INF879O01027",
        "fund_name": "Parag Parikh Flexi Cap Fund Regular Growth",
        "transaction_type": "Purchase",
        "amount": 60_000.0,
        "units": 666.667,
        "nav": 90.00,
        "plan_type": "Regular",
    },
]

DEMO_CURRENT_NAVS = {
    "Axis Bluechip Fund Regular Growth": 72.40,
    "HDFC Hybrid Equity Fund Regular Growth": 84.15,
    "Parag Parikh Flexi Cap Fund Regular Growth": 103.25,
}

DEMO_PROFILE = {
    "current_age": 32,
    "target_retirement_age": 50,
    "monthly_expenses": 80_000.0,
    "annual_income": 1_650_000.0,
    "emergency_fund": 250_000.0,
    "life_cover": 12_000_000.0,
    "monthly_emi": 32_000.0,
    "existing_monthly_investment": 35_000.0,
    "asset_mix": {
        "Equity": 70.0,
        "Debt": 15.0,
        "Gold": 5.0,
        "Cash": 10.0,
    },
}


def _currency(value: float) -> str:
    return f"Rs. {value:,.2f}"


def build_demo_holdings() -> list[dict[str, Any]]:
    df = pd.DataFrame(DEMO_TRANSACTIONS)
    holdings = (
        df.groupby(["fund_name", "folio_number", "isin", "plan_type"], as_index=False)
        .agg(units_held=("units", "sum"))
        .assign(
            current_nav=lambda x: x["fund_name"].map(DEMO_CURRENT_NAVS),
            current_value=lambda x: x["units_held"] * x["current_nav"],
            asset_class=lambda x: x["fund_name"].map(
                {
                    "Axis Bluechip Fund Regular Growth": "Equity",
                    "HDFC Hybrid Equity Fund Regular Growth": "Hybrid",
                    "Parag Parikh Flexi Cap Fund Regular Growth": "Equity",
                }
            ),
        )
    )
    return holdings.to_dict(orient="records")


def build_form16_text() -> str:
    tax = DEMO_TAX_PROFILE
    lines = [
        "ET WealthPulse Demo Form 16",
        "Employee Name | " + tax["employee_name"],
        "Financial Year | " + tax["financial_year"],
        f"Gross Salary | {_currency(tax['gross_salary'])}",
        f"Section 80C | {_currency(tax['section_80c'])}",
        f"Section 80D | {_currency(tax['section_80d'])}",
        f"HRA Exemption | {_currency(tax['hra_exemption'])}",
        f"Standard Deduction | {_currency(tax['standard_deduction'])}",
        f"Employer NPS | {_currency(tax['employer_nps'])}",
        "Notes | Demo document generated locally for hackathon testing only.",
    ]
    return "\n".join(lines)


def build_cas_text() -> str:
    holdings = build_demo_holdings()
    lines = [
        "ET WealthPulse Demo CAMS Statement",
        "Statement Date: 2026-03-31",
        "Investor Name: Aarav Mehta",
        "",
        "HOLDING TABLE",
        "HOLDING | Fund Name | Folio | ISIN | Plan | Current NAV | Units Held | Current Value | Asset Class",
    ]

    for holding in holdings:
        lines.append(
            "HOLDING | "
            + " | ".join(
                [
                    holding["fund_name"],
                    holding["folio_number"],
                    holding["isin"],
                    holding["plan_type"],
                    f"{holding['current_nav']:.2f}",
                    f"{holding['units_held']:.3f}",
                    f"{holding['current_value']:.2f}",
                    holding["asset_class"],
                ]
            )
        )

    lines.extend(
        [
            "",
            "TRANSACTION TABLE",
            "TXN | Date | Folio | ISIN | Fund Name | Type | Amount | Units | NAV | Plan",
        ]
    )

    for row in DEMO_TRANSACTIONS:
        lines.append(
            "TXN | "
            + " | ".join(
                [
                    row["date"],
                    row["folio_number"],
                    row["isin"],
                    row["fund_name"],
                    row["transaction_type"],
                    f"{row['amount']:.2f}",
                    f"{row['units']:.3f}",
                    f"{row['nav']:.2f}",
                    row["plan_type"],
                ]
            )
        )

    return "\n".join(lines)


def create_pdf_bytes(title: str, text: str) -> bytes:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((40, 40), title, fontsize=18, fontname="helv")
    page.insert_textbox((40, 70, 555, 800), text, fontsize=10.5, fontname="cour", align=0)
    pdf_bytes = document.tobytes()
    document.close()
    return pdf_bytes


def generate_demo_documents() -> dict[str, Any]:
    form16_text = build_form16_text()
    cas_text = build_cas_text()
    ais_text = build_ais_text()
    return {
        "form16_text": form16_text,
        "cas_text": cas_text,
        "ais_text": ais_text,
        "form16_bytes": create_pdf_bytes("Demo Form 16", form16_text),
        "cas_bytes": create_pdf_bytes("Demo CAMS Statement", cas_text),
        "ais_bytes": create_pdf_bytes("Demo AIS", ais_text),
        "tax_profile": DEMO_TAX_PROFILE.copy(),
        "ais_profile": DEMO_AIS_PROFILE.copy(),
        "holdings": build_demo_holdings(),
        "transactions": [row.copy() for row in DEMO_TRANSACTIONS],
        "profile": {
            **DEMO_PROFILE,
            "asset_mix": DEMO_PROFILE["asset_mix"].copy(),
        },
    }


DEMO_AIS_PROFILE = {
    "pan": "ABCPM1234D",
    "taxpayer_name": "Aarav Mehta",
    "financial_year": "2025-26",
    "assessment_year": "2026-27",
    # Income fields
    "salary_reported": 1_650_000.0,    # matches Form 16 gross_salary
    "interest_savings": 14_500.0,      # SFT-001 savings bank interest
    "interest_fd": 62_400.0,           # SFT-016 FD interest (6 lakh FD @ ~10.4%)
    "dividend_income": 18_200.0,       # SFT-017 dividend
    # MF (slightly higher than CAMS — one folio missing in CAMS)
    "mf_purchase_total": 385_000.0,    # SFT-18
    "mf_redemption_total": 0.0,
    # Stocks
    "securities_purchase_total": 220_000.0,
    "securities_sale_total": 275_000.0,
    # Property
    "property_purchase_total": 0.0,
    "property_sale_total": 0.0,
    # TDS
    "tds_salary": 112_500.0,
    "tds_other": 6_240.0,              # 10% TDS on FD interest
    # Misc
    "cash_deposits": 0.0,
    "credit_card_spends": 720_000.0,   # triggers lifestyle inflation flag
    "foreign_remittance": 0.0,
}


def build_ais_text() -> str:
    a = DEMO_AIS_PROFILE
    lines = [
        "ANNUAL INFORMATION STATEMENT",
        "Annual Information Statement (AIS)",
        "Income Tax Department, Government of India",
        "",
        f"PAN: {a['pan']}",
        f"Taxpayer Name: {a['taxpayer_name']}",
        f"Financial Year: {a['financial_year']}",
        f"Assessment Year: {a['assessment_year']}",
        "",
        "PART B — INFORMATION CATEGORIES",
        "",
        "─── TDS-01 | Salary ───────────────────────────────────────────────",
        f"  Employer: TECHNOLOGY SOLUTIONS PVT LTD",
        f"  Salary Credited: Rs. {a['salary_reported']:,.2f}",
        "",
        "─── SFT-001 | Interest from Savings Bank Account ─────────────────",
        f"  Bank: HDFC Bank Ltd",
        f"  Amount:   Rs. {a['interest_savings']:,.2f}",
        "",
        "─── SFT-016 | Interest from Deposits ─────────────────────────────",
        f"  Bank: State Bank of India",
        f"  Amount:   Rs. {a['interest_fd']:,.2f}",
        "",
        "─── TDS-26Q | TDS on Interest Income ─────────────────────────────",
        f"  TDS on Interest Deducted: Rs. {a['tds_other']:,.2f}",
        "",
        "─── SFT-017 | Dividend Income ─────────────────────────────────────",
        f"  Amount:   Rs. {a['dividend_income']:,.2f}",
        "",
        "─── SFT-018 | Purchase / Redemption of Mutual Fund Units ──────────",
        f"  MF House: AXIS MUTUAL FUND",
        f"  Purchase  Amount: Rs. {a['mf_purchase_total'] * 0.40:,.2f}",
        f"  MF House: PARAG PARIKH MUTUAL FUND",
        f"  Purchase  Amount: Rs. {a['mf_purchase_total'] * 0.60:,.2f}",
        "",
        "─── SFT-004 | Purchase / Sale of Securities (Shares) ──────────────",
        f"  Broker: ZERODHA BROKING LTD",
        f"  Purchase  Amount: Rs. {a['securities_purchase_total']:,.2f}",
        f"  Sale      Amount: Rs. {a['securities_sale_total']:,.2f}",
        "",
        "─── SFT-012 | Credit Card Payments ────────────────────────────────",
        f"  Bank: HDFC Bank Ltd",
        f"  Amount:   Rs. {a['credit_card_spends']:,.2f}",
        "",
        "END OF ANNUAL INFORMATION STATEMENT",
        "This is a system-generated document. No signature required.",
    ]
    return "\n".join(lines)


def write_demo_files(output_dir: str | Path = "demo_docs") -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    docs = generate_demo_documents()
    form16_path = output_path / "demo_form16.pdf"
    cas_path = output_path / "demo_cams_statement.pdf"

    ais_path = output_path / "demo_ais.pdf"
    form16_path.write_bytes(docs["form16_bytes"])
    cas_path.write_bytes(docs["cas_bytes"])
    ais_path.write_bytes(docs["ais_bytes"])
    return {"form16": form16_path, "cams_statement": cas_path, "ais": ais_path}


def generate_mock_form16(output_dir: str = "demo_docs") -> tuple[str, str]:
    paths = write_demo_files(output_dir)
    form16_txt_path = str(Path(output_dir) / "demo_form16.txt")
    Path(form16_txt_path).write_text(build_form16_text(), encoding="utf-8")
    return form16_txt_path, str(paths["form16"])


def generate_mock_cams_statement(output_dir: str = "demo_docs") -> tuple[str, str]:
    paths = write_demo_files(output_dir)
    cams_txt_path = str(Path(output_dir) / "demo_cams_statement.txt")
    Path(cams_txt_path).write_text(build_cas_text(), encoding="utf-8")
    return cams_txt_path, str(paths["cams_statement"])


if __name__ == "__main__":
    created = write_demo_files()
    print("Generated demo documents:")
    for label, path in created.items():
        print(f"- {label}: {path.resolve()}")
#oknow
