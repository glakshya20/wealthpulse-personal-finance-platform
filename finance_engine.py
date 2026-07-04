from __future__ import annotations

import io
import math
import re
from dataclasses import dataclass
from typing import Any

import fitz
import numpy as np
import numpy_financial as npf
import pandas as pd

try:
    from pyxirr import xirr
    PYXIRR_AVAILABLE = True
except ModuleNotFoundError:
    PYXIRR_AVAILABLE = False

    def xirr(dates, values):
        # Fallback approximate if pyxirr is missing
        if len(values) < 2:
            return None
        try:
            cash_flows = np.array(values, dtype=float)
            if np.all(cash_flows == 0):
                return None
            # Rough from npf.irr for uniform intervals as approximate fallback
            return float(npf.irr(cash_flows)) if len(cash_flows) > 1 else None
        except Exception:
            return None


FY_2025_26_LABEL = "FY 2025-26 (1 Apr 2025 to 31 Mar 2026) / AY 2026-27"

DEFAULT_NEW_REGIME_SLABS = [
    (400_000, 0.00),
    (800_000, 0.05),
    (1_200_000, 0.10),
    (1_600_000, 0.15),
    (2_000_000, 0.20),
    (2_400_000, 0.25),
    (math.inf, 0.30),
]

OLD_REGIME_SLABS_BY_AGE = {
    "under_60": [
        (250_000, 0.00),
        (500_000, 0.05),
        (1_000_000, 0.20),
        (math.inf, 0.30),
    ],
    "60_to_79": [
        (300_000, 0.00),
        (500_000, 0.05),
        (1_000_000, 0.20),
        (math.inf, 0.30),
    ],
    "80_plus": [
        (500_000, 0.00),
        (1_000_000, 0.20),
        (math.inf, 0.30),
    ],
}

SOURCE_LIBRARY = {
    "tax_period": {
        "label": "Finance Act 2025 salary-tax rates",
        "citation": "Finance Bill 2025 / FY 2025-26 salary-tax slabs under Section 115BAC and Part III of the First Schedule.",
        "url": "https://www.indiabudget.gov.in/budget2025-26/doc/memo.pdf",
    },
    "section_115bac": {
        "label": "Section 115BAC",
        "citation": "Default new tax regime slabs for salaried taxpayers in FY 2025-26.",
        "url": "https://incometaxindia.gov.in/Documents/Left%20Menu/TAX%20RATES_HUF.htm?ID=411",
    },
    "section_87a": {
        "label": "Section 87A",
        "citation": "Resident individual rebate: up to Rs. 5 lakh in old regime, up to Rs. 12 lakh in new regime for AY 2026-27, subject to conditions.",
        "url": "https://incometaxindia.gov.in/charts%20%20tables/deductions.htm",
    },
    "standard_deduction": {
        "label": "Section 16(ia)",
        "citation": "Standard deduction is Rs. 50,000 in old regime and up to Rs. 75,000 in new regime for AY 2026-27.",
        "url": "https://incometaxindia.gov.in/charts%20%20tables/deductions.htm",
    },
    "section_80c": {
        "label": "Section 80C",
        "citation": "Combined deduction limit of Rs. 1,50,000 under Chapter VI-A for eligible 80C items.",
        "url": "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1",
    },
    "section_80d": {
        "label": "Section 80D",
        "citation": "Health insurance deduction up to Rs. 25,000 or Rs. 50,000 for senior citizens, subject to conditions.",
        "url": "https://www.incometax.gov.in/iec/foportal/help/individual/return-applicable-1",
    },
    "hra": {
        "label": "Section 10(13A) read with Rule 2A",
        "citation": "HRA exemption applies only to actual rent paid and is limited under Rule 2A.",
        "url": "https://incometaxindia.gov.in/pages/rules/income-tax-rules-1962.aspx?key=10%2813A%29",
    },
    "xirr": {
        "label": "Portfolio XIRR",
        "citation": "Annualized money-weighted return computed from dated cash flows using pyxirr.",
        "url": "https://github.com/Anexen/pyxirr",
    },
    "expense_drag": {
        "label": "Expense Ratio Drag",
        "citation": "Direct-plan savings estimated using a 0.75% to 1.00% annual TER gap assumption for demo purposes.",
        "url": "",
    },
    "fire": {
        "label": "FIRE Rule",
        "citation": "Target corpus modeled using a 4% withdrawal rule, 12% annual return assumption, and 6% inflation assumption.",
        "url": "",
    },
    "emergency_rule": {
        "label": "Emergency Fund Rule",
        "citation": "Financial planning heuristic: hold at least 6x monthly expenses in liquid reserves.",
        "url": "",
    },
    "insurance_rule": {
        "label": "Insurance Rule",
        "citation": "Financial planning heuristic: life cover target set to roughly 20x annual income.",
        "url": "",
    },
    "debt_rule": {
        "label": "Debt-to-Income Rule",
        "citation": "Financial planning heuristic: EMI burden below 35% of gross monthly income is healthier.",
        "url": "",
    },
    "diversification_rule": {
        "label": "Diversification Rule",
        "citation": "Diversification score rewards asset allocation spread across equity, debt, gold, and cash buckets.",
        "url": "",
    },
    "schedule_os": {
        "label": "Schedule OS (Other Sources)",
        "citation": "Income from FD interest, savings bank interest, and dividends must be declared under Schedule OS "
                    "of ITR-1 / ITR-2. Section 56(2) governs taxability of such income at applicable slab rates.",
        "url": "https://incometaxindia.gov.in/charts%20%20tables/income-other-sources.htm",
    },
    "section_234c": {
        "label": "Section 234C — Advance Tax",
        "citation": "If total tax liability (after TDS credit) exceeds Rs. 10,000, advance tax must be paid in four "
                    "instalments. AIS other income contributes to this liability.",
        "url": "https://incometaxindia.gov.in/pages/tools/advance-tax-calculator.aspx",
    },
    "ais_portal": {
        "label": "Annual Information Statement (AIS)",
        "citation": "AIS is the Income Tax Department's consolidated financial information statement covering salary, "
                    "interest, dividends, MF/securities transactions, and property deals reported by third parties.",
        "url": "https://eportal.incometax.gov.in",
    },
    "section_194a": {
        "label": "Section 194A — TDS on Interest",
        "citation": "Banks deduct TDS at 10% on FD interest exceeding Rs. 40,000 per year (Rs. 50,000 for senior citizens). "
                    "This TDS is claimable as a credit when filing ITR.",
        "url": "https://incometaxindia.gov.in/charts%20%20tables/tds-rates.htm",
    },
}


@dataclass
class TaxInputs:
    gross_salary: float
    section_80c: float = 0.0
    section_80d: float = 0.0
    hra_exemption: float = 0.0
    standard_deduction_old: float = 50_000.0
    standard_deduction_new: float = 75_000.0
    employer_nps: float = 0.0
    age: int = 30
    current_regime: str = "new"
    # ── AIS other-income fields (all default 0 → fully backward-compatible) ──
    ais_fd_interest: float = 0.0        # SFT-016: FD / recurring deposit interest
    ais_savings_interest: float = 0.0   # SFT-001: savings bank interest
    ais_dividend_income: float = 0.0    # SFT-017: dividend income
    ais_tds_paid: float = 0.0           # TDS-26Q: TDS already deducted on above income


def source_reference(key: str) -> dict[str, str]:
    return SOURCE_LIBRARY.get(key, {"label": key, "citation": key, "url": ""})


def load_pdf_text(pdf_source: bytes | bytearray | io.BytesIO | str) -> str:
    if isinstance(pdf_source, (bytes, bytearray)):
        document = fitz.open(stream=pdf_source, filetype="pdf")
    elif isinstance(pdf_source, io.BytesIO):
        document = fitz.open(stream=pdf_source.getvalue(), filetype="pdf")
    elif isinstance(pdf_source, str):
        document = fitz.open(pdf_source)
    else:
        raise TypeError("Unsupported PDF source")

    try:
        text_parts = [page.get_text("text") for page in document]
    finally:
        document.close()
    return "\n".join(text_parts).strip()


def normalize_currency(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float, np.number)):
        return float(value)
    text = str(value).strip()
    if not text:
        return 0.0
    text = (
        text.replace("Rs.", "")
        .replace("Rs", "")
        .replace("INR", "")
        .replace("₹", "")
        .replace(",", "")
        .strip()
    )
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text or text == "-":
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def normalize_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _search_amount(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return normalize_currency(match.group(1))
    return None


def parse_form16_text(text: str) -> dict[str, Any]:
    clean_text = normalize_text(text)
    field_patterns = {
        "gross_salary": [
            r"gross salary(?: paid)?\s*[:\-|]?\s*([A-Za-z₹0-9,.\s]+)",
            r"income chargeable under the head salaries\s*[:\-|]?\s*([A-Za-z₹0-9,.\s]+)",
            r"salary income\s*[:\-|]?\s*([A-Za-z₹0-9,.\s]+)",
        ],
        "section_80c": [
            r"section\s*80c\s*[:\-|]?\s*([A-Za-z₹0-9,.\s]+)",
            r"80c deduction\s*[:\-|]?\s*([A-Za-z₹0-9,.\s]+)",
        ],
        "section_80d": [
            r"section\s*80d\s*[:\-|]?\s*([A-Za-z₹0-9,.\s]+)",
            r"80d deduction\s*[:\-|]?\s*([A-Za-z₹0-9,.\s]+)",
        ],
        "hra_exemption": [
            r"hra exemption(?: u/s 10\(13a\))?\s*[:\-|]?\s*([A-Za-z₹0-9,.\s]+)",
            r"house rent allowance exemption\s*[:\-|]?\s*([A-Za-z₹0-9,.\s]+)",
        ],
        "standard_deduction": [
            r"standard deduction\s*[:\-|]?\s*([A-Za-z₹0-9,.\s]+)",
        ],
        "employer_nps": [
            r"employer nps(?: contribution)?\s*[:\-|]?\s*([A-Za-z₹0-9,.\s]+)",
            r"80ccd\(2\)\s*[:\-|]?\s*([A-Za-z₹0-9,.\s]+)",
        ],
    }

    parsed: dict[str, Any] = {}
    detected_fields: list[str] = []
    for field_name, patterns in field_patterns.items():
        value = _search_amount(patterns, clean_text)
        if value is not None:
            parsed[field_name] = value
            detected_fields.append(field_name)

    delimited_rows = {}
    for line in clean_text.splitlines():
        if "|" in line:
            parts = [part.strip() for part in line.split("|") if part.strip()]
            if len(parts) >= 2:
                delimited_rows[parts[0].lower()] = normalize_currency(parts[-1])

    for key_alias, field_name in [
        ("gross salary", "gross_salary"),
        ("section 80c", "section_80c"),
        ("section 80d", "section_80d"),
        ("hra exemption", "hra_exemption"),
        ("standard deduction", "standard_deduction"),
        ("employer nps", "employer_nps"),
    ]:
        if field_name not in parsed and key_alias in delimited_rows:
            parsed[field_name] = delimited_rows[key_alias]
            detected_fields.append(field_name)

    if "standard_deduction" not in parsed:
        parsed["standard_deduction"] = 50_000.0

    parsed.setdefault("gross_salary", 0.0)
    parsed.setdefault("section_80c", 0.0)
    parsed.setdefault("section_80d", 0.0)
    parsed.setdefault("hra_exemption", 0.0)
    parsed.setdefault("employer_nps", 0.0)
    parsed["confidence"] = round(len(set(detected_fields)) / 6, 2)
    parsed["detected_fields"] = sorted(set(detected_fields))
    return parsed


def _parse_date(value: Any) -> pd.Timestamp | pd.NaT:
    if value is None or value == "":
        return pd.NaT

    value = str(value).strip()

    # ISO format: YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return pd.to_datetime(value, format="%Y-%m-%d", errors="coerce")

    # Indian format: DD/MM/YYYY or DD-MM-YYYY
    return pd.to_datetime(value, dayfirst=True, errors="coerce")


def parse_cas_text(text: str) -> dict[str, Any]:
    clean_text = normalize_text(text)
    merged_lines = []
    current_line = ""
    for line in clean_text.splitlines():
        line = line.strip()
        if line.startswith(("HOLDING", "TXN")):
            if current_line:
                merged_lines.append(current_line)
            current_line = line
        elif current_line:
            current_line += " " + line
        else:
            merged_lines.append(line)
    if current_line:
        merged_lines.append(current_line)
    clean_text = "\n".join(merged_lines)
    
    statement_date_match = re.search(
        r"statement date\s*[:\-]?\s*([0-9]{4}-[0-9]{2}-[0-9]{2}|[0-9]{2}[/-][0-9]{2}[/-][0-9]{4})",
        clean_text,
        flags=re.IGNORECASE,
    )
    statement_date = _parse_date(statement_date_match.group(1)) if statement_date_match else pd.Timestamp.today().normalize()

    holdings_rows: list[dict[str, Any]] = []
    transaction_rows: list[dict[str, Any]] = []
    print("\n===== MERGED LINES =====")
    for l in merged_lines[:10]:
        print(l)

    for line in merged_lines:
        parts = [part.strip() for part in line.split("|")]
        if not parts:
            continue

        tag = parts[0].upper()
        if (
            tag == "HOLDING"
            and len(parts) >= 9
            and parts[1].strip().lower() != "fund name"
        ):
            holdings_rows.append(
                {
                    "fund_name": parts[1],
                    "folio_number": parts[2],
                    "isin": parts[3],
                    "plan_type": parts[4],
                    "current_nav": normalize_currency(parts[5]),
                    "units_held": normalize_currency(parts[6]),
                    "current_value": normalize_currency(parts[7]),
                    "asset_class": parts[8].replace("TRANSACTION TABLE", "").strip(),
                }
            )
        elif (
            tag == "TXN"
            and len(parts) >= 10
            and parts[1].strip().lower() != "date"
        ):
            transaction_rows.append(
                {
                    "date": _parse_date(parts[1]),
                    "folio_number": parts[2],
                    "isin": parts[3],
                    "fund_name": parts[4],
                    "transaction_type": parts[5],
                    "amount": normalize_currency(parts[6]),
                    "units": normalize_currency(parts[7]),
                    "nav": normalize_currency(parts[8]),
                    "plan_type": parts[9],
                }
            )

    if not transaction_rows:
        generic_txn_pattern = re.compile(
            r"(?P<date>[0-9]{2}[/-][0-9]{2}[/-][0-9]{4}|[0-9]{4}-[0-9]{2}-[0-9]{2}).*?"
            r"(?P<folio>[A-Z0-9/\-]+).*?"
            r"(?P<isin>INF[A-Z0-9]{9}|INE[A-Z0-9]{9}).*?"
            r"(?P<amount>[A-Za-z₹0-9,.\-\s]+)",
            flags=re.IGNORECASE,
        )
        for match in generic_txn_pattern.finditer(clean_text):
            transaction_rows.append(
                {
                    "date": _parse_date(match.group("date")),
                    "folio_number": match.group("folio"),
                    "isin": match.group("isin").upper(),
                    "fund_name": "Parsed Transaction",
                    "transaction_type": "Purchase",
                    "amount": normalize_currency(match.group("amount")),
                    "units": 0.0,
                    "nav": 0.0,
                    "plan_type": "Unknown",
                }
            )

    transactions_df = pd.DataFrame(transaction_rows)
    holdings_df = pd.DataFrame(holdings_rows)

    if transactions_df.empty:
        transactions_df = pd.DataFrame(
            columns=[
                "date",
                "folio_number",
                "isin",
                "fund_name",
                "transaction_type",
                "amount",
                "units",
                "nav",
                "plan_type",
            ]
        )

    if holdings_df.empty and not transactions_df.empty:
        synthesized = (
            transactions_df.assign(
                signed_units=lambda df: np.where(
                    df["transaction_type"].str.contains("redemption|switch out", case=False, na=False),
                    -df["units"],
                    df["units"],
                )
            )
            .groupby(["fund_name", "folio_number", "isin", "plan_type"], as_index=False)
            .agg(units_held=("signed_units", "sum"), current_nav=("nav", "last"))
        )
        synthesized["current_value"] = synthesized["units_held"] * synthesized["current_nav"]
        synthesized["asset_class"] = "Equity"
        holdings_df = synthesized

    folios = sorted({folio for folio in transactions_df.get("folio_number", pd.Series(dtype=str)).dropna().tolist() if str(folio).strip()})
    isins = sorted({isin for isin in transactions_df.get("isin", pd.Series(dtype=str)).dropna().tolist() if str(isin).strip()})
    if not folios and not holdings_df.empty:
        folios = sorted({folio for folio in holdings_df["folio_number"].dropna().tolist() if str(folio).strip()})
    if not isins and not holdings_df.empty:
        isins = sorted({isin for isin in holdings_df["isin"].dropna().tolist() if str(isin).strip()})

    # Fallback: detect isolated folio/isin references in text even when structured rows are not captured
    if folios == [] and isins == [] and transactions_df.empty and holdings_df.empty:
        folio_candidates = sorted(
            set(
                re.findall(r"(?:folio(?: number| no\\.?)?)\\s*[:\\-]?\\s*([A-Za-z0-9\\/\\-]+)", clean_text, flags=re.IGNORECASE)
            )
        )
        isin_candidates = sorted(
            set(
                match.upper()
                for match in re.findall(r"(?:isin)\\s*[:\\-]?\\s*((?:INF|INE)[A-Z0-9]{9})", clean_text, flags=re.IGNORECASE)
            )
        )
        if folio_candidates:
            folios = folio_candidates
        if isin_candidates:
            isins = isin_candidates

    transaction_dates = transactions_df["date"].dropna().sort_values().dt.date.tolist() if not transactions_df.empty else []
    confidence = round(min(1.0, (len(folios) + len(isins) + len(transaction_dates)) / 9), 2)
    if holdings_exist := not holdings_df.empty:
        # if we have holdings data from parsed table, bump confidence to avoid false fails
        confidence = max(confidence, 0.25)

    return {
        "statement_date": statement_date,
        "folios": folios,
        "isins": isins,
        "transaction_dates": transaction_dates,
        "transactions": transactions_df,
        "holdings": holdings_df,
        "confidence": confidence,
    }


def parse_form16(pdf_or_text: bytes | str) -> dict[str, Any]:
    if isinstance(pdf_or_text, (bytes, bytearray)):
        text = load_pdf_text(pdf_or_text)
    elif isinstance(pdf_or_text, str) and pdf_or_text.strip().endswith(".pdf"):
        text = load_pdf_text(pdf_or_text)
    elif isinstance(pdf_or_text, str):
        text = pdf_or_text
    else:
        raise ValueError("Unsupported type for Form 16 input")

    parsed = parse_form16_text(text)
    return parsed


def parse_cams_statement(pdf_or_text: bytes | str) -> dict[str, Any]:
    if isinstance(pdf_or_text, (bytes, bytearray)):
        text = load_pdf_text(pdf_or_text)
    elif isinstance(pdf_or_text, str) and pdf_or_text.strip().endswith(".pdf"):
        text = load_pdf_text(pdf_or_text)
    elif isinstance(pdf_or_text, str):
        text = pdf_or_text
    else:
        raise ValueError("Unsupported type for CAMS statement input")

    parsed = parse_cas_text(text)
    return parsed


def age_bucket(age: int) -> str:
    if age >= 80:
        return "80_plus"
    if age >= 60:
        return "60_to_79"
    return "under_60"


def apply_slabs(taxable_income: float, slabs: list[tuple[float, float]]) -> float:
    taxable_income = max(0.0, taxable_income)
    tax = 0.0
    lower = 0.0
    for upper, rate in slabs:
        if taxable_income <= lower:
            break
        taxable_at_this_rate = min(taxable_income, upper) - lower
        if taxable_at_this_rate > 0:
            tax += taxable_at_this_rate * rate
        lower = upper
    return max(0.0, tax)


def cap_80d(amount: float, age: int) -> float:
    return min(max(amount, 0.0), 50_000.0 if age >= 60 else 25_000.0)


def estimate_marginal_tax_rate(taxable_income: float, age: int, regime: str) -> float:
    slabs = DEFAULT_NEW_REGIME_SLABS if regime == "new" else OLD_REGIME_SLABS_BY_AGE[age_bucket(age)]
    lower = 0.0
    for upper, rate in slabs:
        if lower < taxable_income <= upper:
            return rate
        lower = upper
    return slabs[-1][1]


def calculate_tax_for_regime(inputs: TaxInputs, regime: str) -> dict[str, Any]:
    if regime not in {"old", "new"}:
        raise ValueError("Regime must be 'old' or 'new'")

    allowed_80c = min(max(inputs.section_80c, 0.0), 150_000.0)
    allowed_80d = cap_80d(inputs.section_80d, inputs.age)
    allowed_hra = max(inputs.hra_exemption, 0.0)
    allowed_nps = max(inputs.employer_nps, 0.0)

    # AIS other income (Schedule OS) — no standard deduction applies to these
    other_income = max(0.0,
        inputs.ais_fd_interest + inputs.ais_savings_interest + inputs.ais_dividend_income
    )

    if regime == "old":
        standard_deduction = min(max(inputs.standard_deduction_old, 0.0), inputs.gross_salary)
        deductions = allowed_80c + allowed_80d + allowed_hra + allowed_nps
        salary_taxable = max(0.0, inputs.gross_salary - standard_deduction - deductions)
        taxable_income = salary_taxable + other_income
        slab_tax = apply_slabs(taxable_income, OLD_REGIME_SLABS_BY_AGE[age_bucket(inputs.age)])
        rebate_threshold = 500_000.0
        rebate = min(12_500.0, slab_tax) if taxable_income <= rebate_threshold else 0.0
    else:
        standard_deduction = min(max(inputs.standard_deduction_new, 0.0), inputs.gross_salary)
        deductions = allowed_nps
        salary_taxable = max(0.0, inputs.gross_salary - standard_deduction - deductions)
        taxable_income = salary_taxable + other_income
        slab_tax = apply_slabs(taxable_income, DEFAULT_NEW_REGIME_SLABS)
        if taxable_income <= 1_200_000.0:
            rebate = min(60_000.0, slab_tax)
        else:
            marginal_relief = max(0.0, slab_tax - (taxable_income - 1_200_000.0))
            rebate = min(60_000.0, marginal_relief, slab_tax)

    tax_after_rebate = max(0.0, slab_tax - rebate)
    cess = tax_after_rebate * 0.04
    total_tax = tax_after_rebate + cess

    # TDS credit from AIS: already deducted at source on interest/dividend income
    tds_credit = max(0.0, inputs.ais_tds_paid)
    net_payable = max(0.0, total_tax - tds_credit)

    total_income = inputs.gross_salary + other_income
    effective_rate = total_tax / total_income if total_income else 0.0

    return {
        "regime": regime,
        "gross_salary": round(inputs.gross_salary, 2),
        "other_income": round(other_income, 2),           # NEW — AIS Schedule OS income
        "total_income": round(total_income, 2),           # NEW — salary + other income
        "standard_deduction": round(standard_deduction, 2),
        "allowed_80c": round(allowed_80c if regime == "old" else 0.0, 2),
        "allowed_80d": round(allowed_80d if regime == "old" else 0.0, 2),
        "allowed_hra": round(allowed_hra if regime == "old" else 0.0, 2),
        "allowed_nps": round(allowed_nps, 2),
        "taxable_income": round(taxable_income, 2),
        "slab_tax": round(slab_tax, 2),
        "rebate": round(rebate, 2),
        "cess": round(cess, 2),
        "total_tax": round(total_tax, 2),
        "tds_credit": round(tds_credit, 2),               # NEW — AIS TDS-26Q credit
        "net_payable": round(net_payable, 2),             # NEW — total_tax minus TDS already paid
        "effective_rate": round(effective_rate, 4),
    }


def compare_tax_regimes(inputs: TaxInputs) -> dict[str, Any]:
    old_tax = calculate_tax_for_regime(inputs, "old")
    new_tax = calculate_tax_for_regime(inputs, "new")

    current_regime = inputs.current_regime.lower().strip()
    current_regime = current_regime if current_regime in {"old", "new"} else "new"
    current_tax = old_tax if current_regime == "old" else new_tax
    alternate_tax = new_tax if current_regime == "old" else old_tax

    better_regime = "old" if old_tax["total_tax"] < new_tax["total_tax"] else "new"
    better_tax = old_tax if better_regime == "old" else new_tax

    unused_80c = max(0.0, 150_000.0 - min(inputs.section_80c, 150_000.0))
    unused_80d = max(0.0, cap_80d(999_999_999.0, inputs.age) - cap_80d(inputs.section_80d, inputs.age))
    old_regime_marginal_rate = estimate_marginal_tax_rate(old_tax["taxable_income"], inputs.age, "old")
    missed_deduction_alpha = round((unused_80c + unused_80d) * old_regime_marginal_rate * 1.04, 2)
    regime_switch_alpha = round(max(0.0, current_tax["total_tax"] - alternate_tax["total_tax"]), 2)
    tax_alpha = round(max(regime_switch_alpha, missed_deduction_alpha), 2)

    # AIS other income summary (used in recommendations and AIS Insights page)
    other_income = inputs.ais_fd_interest + inputs.ais_savings_interest + inputs.ais_dividend_income
    tds_credit = inputs.ais_tds_paid
    best_net_payable = better_tax["net_payable"]

    recommendations: list[dict[str, Any]] = []
    if better_regime != current_regime and regime_switch_alpha > 0:
        recommendations.append(
            {
                "title": f"Switch to {better_regime.title()} Regime",
                "impact": regime_switch_alpha,
                "summary": f"Estimated annual tax saving is Rs. {regime_switch_alpha:,.0f} versus your current {current_regime.title()} regime.",
                "source": [
                    source_reference("section_115bac"),
                    source_reference("section_87a"),
                    source_reference("standard_deduction"),
                ],
            }
        )

    if unused_80c > 0:
        recommendations.append(
            {
                "title": "80C Headroom Available",
                "impact": round(unused_80c * old_regime_marginal_rate * 1.04, 2),
                "summary": f"You still have Rs. {unused_80c:,.0f} of 80C headroom. If genuinely eligible, that could cut old-regime tax by roughly Rs. {unused_80c * old_regime_marginal_rate * 1.04:,.0f}.",
                "source": [source_reference("section_80c")],
            }
        )

    if unused_80d > 0:
        recommendations.append(
            {
                "title": "80D Headroom Available",
                "impact": round(unused_80d * old_regime_marginal_rate * 1.04, 2),
                "summary": f"You still have Rs. {unused_80d:,.0f} of 80D headroom. If you have eligible medical insurance or senior-citizen medical spend, the old regime improves further.",
                "source": [source_reference("section_80d")],
            }
        )

    if inputs.hra_exemption > 0:
        recommendations.append(
            {
                "title": "HRA Is Meaningful in Old Regime",
                "impact": round(inputs.hra_exemption * old_regime_marginal_rate * 1.04, 2),
                "summary": f"Your HRA exemption of Rs. {inputs.hra_exemption:,.0f} materially supports the old regime if rent proofs are valid.",
                "source": [source_reference("hra")],
            }
        )

    # ── AIS other-income recommendation ──────────────────────────────────────
    if other_income > 0:
        marginal = estimate_marginal_tax_rate(better_tax["taxable_income"], inputs.age, better_regime)
        other_income_tax = round(other_income * marginal * 1.04, 2)
        net_after_tds = max(0.0, other_income_tax - tds_credit)
        recommendations.append(
            {
                "title": "Declare AIS Other Income in Schedule OS",
                "impact": net_after_tds,
                "summary": (
                    f"AIS shows Rs. {other_income:,.0f} of additional taxable income "
                    f"(FD interest + savings interest + dividend). "
                    f"At your marginal rate of {marginal * 100:.0f}% + cess, estimated tax is "
                    f"Rs. {other_income_tax:,.0f}. "
                    f"TDS of Rs. {tds_credit:,.0f} has already been deducted — "
                    f"net payable on filing ITR is approximately Rs. {net_after_tds:,.0f}. "
                    "Declare under Schedule OS of ITR-1 or ITR-2."
                ),
                "source": [source_reference("schedule_os"), source_reference("section_194a")],
            }
        )

        # Advance tax flag if net > Rs. 10,000
        if net_after_tds > 10_000:
            recommendations.append(
                {
                    "title": "Advance Tax May Be Due",
                    "impact": net_after_tds,
                    "summary": (
                        f"Net additional tax liability of Rs. {net_after_tds:,.0f} exceeds the Rs. 10,000 "
                        "threshold. You may need to pay advance tax in four instalments "
                        "(June 15, Sep 15, Dec 15, Mar 15) to avoid interest under Section 234C."
                    ),
                    "source": [source_reference("section_234c")],
                }
            )

    return {
        "tax_period": FY_2025_26_LABEL,
        "current_regime": current_regime,
        "better_regime": better_regime,
        "old_regime": old_tax,
        "new_regime": new_tax,
        "current_tax": current_tax,
        "best_tax": better_tax,
        "regime_switch_alpha": regime_switch_alpha,
        "missed_deduction_alpha": missed_deduction_alpha,
        "tax_alpha": tax_alpha,
        "unused_80c": round(unused_80c, 2),
        "unused_80d": round(unused_80d, 2),
        # AIS-enriched fields (0.0 when no AIS data supplied)
        "ais_other_income": round(other_income, 2),
        "ais_tds_credit": round(tds_credit, 2),
        "best_net_payable": round(best_net_payable, 2),
        "recommendations": recommendations,
    }


def classify_transaction_sign(transaction_type: str) -> int:
    tx = str(transaction_type).lower()
    if any(keyword in tx for keyword in ["redemption", "switch out", "sell", "dividend payout", "stp out"]):
        return 1
    return -1


def calculate_xirr_from_transactions(
    transactions: pd.DataFrame,
    holdings: pd.DataFrame | None = None,
    valuation_date: pd.Timestamp | None = None,
) -> dict[str, Any]:
    if transactions is None or transactions.empty:
        return {"xirr": None, "cash_flows": pd.DataFrame(columns=["date", "amount"])}

    cash_flows = transactions.copy()
    cash_flows["date"] = pd.to_datetime(cash_flows["date"], errors="coerce")
    cash_flows = cash_flows.dropna(subset=["date"])
    cash_flows["signed_amount"] = cash_flows.apply(
        lambda row: classify_transaction_sign(row.get("transaction_type", "")) * abs(normalize_currency(row.get("amount"))),
        axis=1,
    )
    cash_flow_rows = cash_flows[["date", "signed_amount"]].rename(columns={"signed_amount": "amount"}).copy()

    if holdings is not None and not holdings.empty:
        final_value = float(pd.to_numeric(holdings["current_value"], errors="coerce").fillna(0.0).sum())
        if final_value > 0:
            cash_flow_rows.loc[len(cash_flow_rows)] = {
                "date": valuation_date or pd.Timestamp.today().normalize(),
                "amount": final_value,
            }

    result = None
    if cash_flow_rows["amount"].gt(0).any() and cash_flow_rows["amount"].lt(0).any():
        try:
            result = float(xirr(cash_flow_rows["date"].tolist(), cash_flow_rows["amount"].tolist()))
        except Exception:
            result = None

    return {
        "xirr": result,
        "cash_flows": cash_flow_rows.sort_values("date").reset_index(drop=True),
    }


def estimate_expense_ratio_drag(
    holdings: pd.DataFrame,
    low_delta: float = 0.0075,
    high_delta: float = 0.0100,
) -> dict[str, Any]:
    if holdings is None or holdings.empty:
        empty = pd.DataFrame(
            columns=[
                "fund_name",
                "folio_number",
                "plan_type",
                "current_value",
                "direct_equivalent",
                "annual_saving_low",
                "annual_saving_high",
                "annual_saving_mid",
            ]
        )
        return {
            "holdings": empty,
            "eligible_holdings": empty,
            "total_saving_low": 0.0,
            "total_saving_high": 0.0,
            "total_saving_mid": 0.0,
        }

    drag_df = holdings.copy()
    if "fund_name" not in drag_df.columns:
        drag_df["fund_name"] = "Unknown Fund"
    if "plan_type" not in drag_df.columns:
        drag_df["plan_type"] = "Unknown"
    drag_df["current_value"] = pd.to_numeric(drag_df["current_value"], errors="coerce").fillna(0.0)
    drag_df["plan_type"] = drag_df["plan_type"].fillna("Unknown")
    drag_df["direct_equivalent"] = drag_df["fund_name"].astype(str).str.replace("Regular", "Direct", regex=False)
    drag_df["annual_saving_low"] = drag_df["current_value"] * low_delta
    drag_df["annual_saving_high"] = drag_df["current_value"] * high_delta
    drag_df["annual_saving_mid"] = drag_df["current_value"] * ((low_delta + high_delta) / 2)

    eligible = drag_df[
        drag_df["plan_type"].astype(str).str.contains("regular", case=False, na=False)
        | drag_df["fund_name"].astype(str).str.contains("regular", case=False, na=False)
    ].copy()

    return {
        "holdings": drag_df,
        "eligible_holdings": eligible.sort_values("annual_saving_mid", ascending=False),
        "total_saving_low": round(float(eligible["annual_saving_low"].sum()), 2),
        "total_saving_high": round(float(eligible["annual_saving_high"].sum()), 2),
        "total_saving_mid": round(float(eligible["annual_saving_mid"].sum()), 2),
    }


def build_portfolio_recommendations(portfolio_xirr_value: float | None, drag_result: dict[str, Any]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []

    if drag_result.get("total_saving_mid", 0.0) > 0:
        recommendations.append(
            {
                "title": "Reduce Regular Plan Drag",
                "impact": drag_result["total_saving_mid"],
                "summary": (
                    "Regular-plan holdings appear eligible for a direct-plan review. "
                    f"Estimated annual saving range is Rs. {drag_result['total_saving_low']:,.0f} to "
                    f"Rs. {drag_result['total_saving_high']:,.0f}."
                ),
                "source": [source_reference("expense_drag")],
            }
        )

    if portfolio_xirr_value is not None:
        recommendations.append(
            {
                "title": "Portfolio XIRR Computed",
                "impact": 0.0,
                "summary": f"Your money-weighted annualized return is {portfolio_xirr_value * 100:,.2f}% based on dated transaction cash flows and current valuation.",
                "source": [source_reference("xirr")],
            }
        )

    return recommendations


def portfolio_xray(parsed_cas: dict[str, Any]) -> dict[str, Any]:
    transactions = parsed_cas.get("transactions", pd.DataFrame())
    holdings = parsed_cas.get("holdings", pd.DataFrame())
    valuation_date = parsed_cas.get("statement_date", pd.Timestamp.today().normalize())
    print("Transactions:", len(transactions))
    print(transactions.head())
    print("Holdings:", len(holdings))
    print(holdings.head())

    xirr_result = calculate_xirr_from_transactions(transactions, holdings, valuation_date)
    drag_result = estimate_expense_ratio_drag(holdings)

    fund_xirr_rows = []
    if not transactions.empty:
        for fund_name, fund_transactions in transactions.groupby("fund_name"):
            matching_holdings = holdings[holdings["fund_name"] == fund_name] if not holdings.empty else pd.DataFrame()
            fund_xirr = calculate_xirr_from_transactions(fund_transactions, matching_holdings, valuation_date)["xirr"]
            current_value = float(matching_holdings["current_value"].sum()) if not matching_holdings.empty else 0.0
            fund_xirr_rows.append(
                {
                    "fund_name": fund_name,
                    "xirr": fund_xirr,
                    "current_value": current_value,
                }
            )

    return {
        "folios": parsed_cas.get("folios", []),
        "isins": parsed_cas.get("isins", []),
        "transaction_dates": parsed_cas.get("transaction_dates", []),
        "transactions": transactions,
        "holdings": holdings,
        "portfolio_xirr": xirr_result["xirr"],
        "cash_flows": xirr_result["cash_flows"],
        "expense_drag": drag_result,
        "fund_xirr": pd.DataFrame(fund_xirr_rows).sort_values("current_value", ascending=False) if fund_xirr_rows else pd.DataFrame(columns=["fund_name", "xirr", "current_value"]),
        "recommendations": build_portfolio_recommendations(xirr_result["xirr"], drag_result),
    }


def monthly_rate_from_annual(annual_rate: float) -> float:
    return (1 + annual_rate) ** (1 / 12) - 1


def future_value_with_monthly_contributions(
    current_corpus: float,
    monthly_contribution: float,
    months: int,
    monthly_return: float,
) -> float:
    if months <= 0:
        return current_corpus
    if monthly_return == 0:
        return current_corpus + (monthly_contribution * months)
    return float(
        current_corpus * ((1 + monthly_return) ** months)
        + monthly_contribution * (((1 + monthly_return) ** months - 1) / monthly_return)
    )


def calculate_fire_plan(
    current_age: int,
    target_retirement_age: int,
    monthly_expenses: float,
    found_money_monthly: float,
    current_corpus: float = 0.0,
    existing_monthly_investment: float = 0.0,
    annual_return: float = 0.12,
    annual_inflation: float = 0.06,
    withdrawal_rate: float = 0.04,
) -> dict[str, Any]:
    months = max(0, int((target_retirement_age - current_age) * 12))
    monthly_return = monthly_rate_from_annual(annual_return)
    monthly_inflation = monthly_rate_from_annual(annual_inflation)

    current_monthly_expense = max(monthly_expenses, 0.0)
    future_monthly_expense = current_monthly_expense * ((1 + monthly_inflation) ** months) if months else current_monthly_expense
    target_corpus = (future_monthly_expense * 12) / withdrawal_rate if withdrawal_rate else 0.0

    if months > 0 and monthly_return != 0:
        total_required_monthly = float(max(0.0, -npf.pmt(monthly_return, months, current_corpus, target_corpus)))
    elif months > 0:
        total_required_monthly = max(0.0, (target_corpus - current_corpus) / months)
    else:
        total_required_monthly = 0.0

    available_monthly = max(0.0, found_money_monthly) + max(0.0, existing_monthly_investment)
    additional_monthly_needed = max(0.0, total_required_monthly - available_monthly)
    modeled_monthly_investment = available_monthly + additional_monthly_needed

    with_found_money_only = future_value_with_monthly_contributions(current_corpus, available_monthly, months, monthly_return)
    with_required_plan = future_value_with_monthly_contributions(current_corpus, modeled_monthly_investment, months, monthly_return)

    projection_rows: list[dict[str, Any]] = []
    running_corpus = current_corpus
    start_month = pd.Timestamp.today().normalize().replace(day=1)
    for month_index in range(months + 1):
        projection_rows.append(
            {
                "month": start_month + pd.DateOffset(months=month_index),
                "age": round(current_age + (month_index / 12), 2),
                "projected_corpus": running_corpus,
                "target_corpus": target_corpus,
                "monthly_investment": modeled_monthly_investment,
                "found_money_monthly": found_money_monthly,
                "additional_monthly_needed": additional_monthly_needed,
            }
        )
        running_corpus = (running_corpus * (1 + monthly_return)) + modeled_monthly_investment

    projection_df = pd.DataFrame(projection_rows)

    return {
        "months_to_retirement": months,
        "current_age": current_age,
        "target_retirement_age": target_retirement_age,
        "current_monthly_expense": current_monthly_expense,
        "future_monthly_expense": round(future_monthly_expense, 2),
        "target_corpus": round(target_corpus, 2),
        "current_corpus": round(current_corpus, 2),
        "existing_monthly_investment": round(existing_monthly_investment, 2),
        "found_money_monthly": round(found_money_monthly, 2),
        "available_monthly": round(available_monthly, 2),
        "required_total_monthly": round(total_required_monthly, 2),
        "additional_monthly_needed": round(additional_monthly_needed, 2),
        "projected_corpus_with_found_money_only": round(with_found_money_only, 2),
        "projected_corpus_with_required_plan": round(with_required_plan, 2),
        "projection": projection_df,
        "progress_pct": (with_found_money_only / target_corpus * 100) if target_corpus else 0.0,
        "recommendations": [
            {
                "title": "Invest Your Found Money",
                "impact": round(found_money_monthly * 12, 2),
                "summary": f"Routing Rs. {found_money_monthly:,.0f} per month of tax and expense-ratio savings straight into investing compounds meaningfully before retirement.",
                "source": [source_reference("fire")],
            },
            {
                "title": "Close the Retirement Gap",
                "impact": round(additional_monthly_needed, 2),
                "summary": f"To hit the modeled corpus by age {target_retirement_age}, total monthly investing should be about Rs. {total_required_monthly:,.0f}. That means an extra Rs. {additional_monthly_needed:,.0f} beyond current and found-money flows.",
                "source": [source_reference("fire")],
            },
        ],
    }


def calculate_diversification_score(asset_mix: dict[str, float]) -> tuple[float, str]:
    weights = np.array([max(0.0, value) for value in asset_mix.values()], dtype=float)
    total = weights.sum()
    if total <= 0:
        return 0.0, "No asset allocation data captured yet."

    normalized = weights / total
    effective_buckets = 1 / np.sum(normalized ** 2)
    score = min(100.0, (effective_buckets / len(weights)) * 100 * 1.25)
    major_bucket = list(asset_mix.keys())[int(np.argmax(normalized))]
    return score, f"Asset mix is concentrated in {major_bucket}." if normalized.max() > 0.65 else "Asset mix is reasonably diversified."


def score_money_health(
    annual_income: float,
    monthly_expenses: float,
    emergency_fund: float,
    life_cover: float,
    monthly_emi: float,
    current_tax: float,
    best_tax: float,
    fire_plan: dict[str, Any],
    asset_mix: dict[str, float],
    ais_summary=None,
) -> dict[str, Any]:
    monthly_income = annual_income / 12 if annual_income else 0.0
    emergency_target = monthly_expenses * 6
    insurance_target = annual_income * 20

    emergency_ratio = emergency_fund / emergency_target if emergency_target else 1.0
    insurance_ratio = life_cover / insurance_target if insurance_target else 1.0
    debt_ratio = monthly_emi / monthly_income if monthly_income else 0.0
    avoidable_tax = max(0.0, current_tax - best_tax)
    retirement_ratio = (
        fire_plan.get("projected_corpus_with_found_money_only", 0.0) / fire_plan.get("target_corpus", 1.0)
        if fire_plan.get("target_corpus", 0.0)
        else 1.0
    )
    diversification_score, diversification_note = calculate_diversification_score(asset_mix)
    
    ais_score = 100.0
    ais_note = "No AIS issues detected."

    if ais_summary is not None:
        high = getattr(ais_summary, "high_count", 0)
        medium = getattr(ais_summary, "medium_count", 0)
        info = getattr(ais_summary, "info_count", 0)

        ais_score = max(
            0.0,
            100
            - high * 25
            - medium * 10
            - info * 3,
        )

        ais_note = (
            f"{high} high, {medium} medium and {info} informational "
            "AIS reconciliation findings."
        )

    dimensions = [
        {
            "dimension": "Emergency",
            "score": round(min(100.0, emergency_ratio * 100), 1),
            "summary": f"Liquid reserves cover {emergency_ratio * 6:,.1f} months of spending.",
            "source": source_reference("emergency_rule"),
        },
        {
            "dimension": "Insurance",
            "score": round(min(100.0, insurance_ratio * 100), 1),
            "summary": f"Life cover is {life_cover / annual_income:,.1f}x annual income." if annual_income else "Annual income missing.",
            "source": source_reference("insurance_rule"),
        },
        {
            "dimension": "Diversification",
            "score": round(diversification_score, 1),
            "summary": diversification_note,
            "source": source_reference("diversification_rule"),
        },
        {
            "dimension": "Debt-to-Income",
            "score": round(max(0.0, min(100.0, 100 - max(0.0, debt_ratio - 0.20) / 0.55 * 100)), 1),
            "summary": f"EMI burden is {debt_ratio * 100:,.1f}% of gross monthly income.",
            "source": source_reference("debt_rule"),
        },
        {
            "dimension": "Tax Efficiency",
            "score": round(max(0.0, min(100.0, 100 - ((avoidable_tax / annual_income) * 1000 if annual_income else 0.0))), 1),
            "summary": f"Avoidable annual tax leakage is about Rs. {avoidable_tax:,.0f}.",
            "source": source_reference("section_115bac"),
        },
        {
            "dimension": "Retirement Gap",
            "score": round(min(100.0, retirement_ratio * 100), 1),
            "summary": f"Current invest-and-forget path funds {retirement_ratio * 100:,.1f}% of the modeled FIRE target.",
            "source": source_reference("fire"),
        },
        {
            "dimension": "AIS Compliance",
            "score": round(ais_score, 1),
            "summary": ais_note,
            "source": "AIS reconciliation",
        },
    ]

    total_score = round(float(np.mean([item["score"] for item in dimensions])), 1) if dimensions else 0.0
    recommendations = []
    if ais_summary is not None:

        if getattr(ais_summary, "high_count", 0):
            recommendations.append(
                {
                    "impact": "High",
                    "title": "Resolve AIS mismatches",
                    "description": (
                        "AIS contains high-priority reconciliation issues. "
                        "Verify Form 16, CAMS and AIS before filing your ITR."
                    ),
                    "source": "AIS",
                }
            )
        elif getattr(ais_summary, "medium_count", 0):
            recommendations.append(
                {
                    "impact": "Medium",
                    "title": "Review AIS observations",
                    "description": (
                        "Some AIS entries differ from uploaded financial documents."
                    ),
                    "source": "AIS",
                }
            )

    for item in dimensions:
        if item["score"] < 70:
            recommendations.append(
                {
                    "title": f"Improve {item['dimension']}",
                    "impact": 0.0,
                    "summary": item["summary"],
                    "source": [item["source"]],
                }
            )

    return {
        "total_score": total_score,
        "dimensions": dimensions,
        "recommendations": recommendations,
    }
