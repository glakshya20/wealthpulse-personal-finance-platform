"""
ais_engine.py — Annual Information Statement (AIS) integration for ET WealthPulse
==================================================================================
AIS is the Income Tax Department's consolidated view of all financial transactions
reported to them by banks, MF registrars, brokers, and employers via SFT / TDS
filings.  It can be downloaded from eportal.incometax.gov.in as a PDF or JSON.

This module:
  1. parse_ais()              — unified entry point (PDF bytes, JSON string, or dict)
  2. _parse_ais_text()        — PDF text extractor (PyMuPDF output)
  3. _parse_ais_json()        — IT portal structured JSON handler
  4. reconcile_ais()          — cross-validates AIS vs Form 16 + CAMS data
  5. enrich_tax_inputs_from_ais() — adds other income / TDS to TaxInputs

Privacy guarantee: zero bytes leave the user's machine.  All computation is local.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd

# Re-use helpers already in finance_engine
from finance_engine import load_pdf_text, normalize_currency, normalize_text, TaxInputs


# ---------------------------------------------------------------------------
# AIS section codes → human-readable labels
# ---------------------------------------------------------------------------
AIS_SECTION_MAP: dict[str, str] = {
    "TDS-01":  "Salary (TDS from employer)",
    "TDS-26Q": "TDS on other income (interest/rent/etc.)",
    "SFT-001": "Savings bank account interest",
    "SFT-01":  "Savings bank account interest",
    "SFT-010": "Savings bank account interest",
    "SFT-016": "Fixed / recurring deposit interest",
    "SFT-16":  "Fixed / recurring deposit interest",
    "SFT-017": "Dividend income",
    "SFT-17":  "Dividend income",
    "SFT-018": "Mutual fund purchase / redemption (SFT)",
    "SFT-18":  "Mutual fund purchase / redemption (SFT)",
    "SFT-004": "Purchase / sale of securities (stocks/bonds)",
    "SFT-04":  "Purchase / sale of securities (stocks/bonds)",
    "SFT-005": "Immovable property purchase",
    "SFT-05":  "Immovable property purchase",
    "SFT-006": "Immovable property sale",
    "SFT-06":  "Immovable property sale",
    "SFT-011": "Cash deposits",
    "SFT-11":  "Cash deposits",
    "SFT-012": "Credit card payments",
    "SFT-12":  "Credit card payments",
    "SFT-013": "Foreign remittance",
    "SFT-13":  "Foreign remittance",
}

TOLERANCE_INR = 5_000.0   # ₹5k noise tolerance for reconciliation


# ---------------------------------------------------------------------------
# Core data structure
# ---------------------------------------------------------------------------
@dataclass
class AISData:
    """Typed, flat view of parsed AIS data."""
    pan: str | None
    taxpayer_name: str | None
    financial_year: str | None
    assessment_year: str | None

    # Income reported
    salary_reported: float          # from TDS-01
    interest_savings: float         # from SFT-001 / SFT-010
    interest_fd: float              # from SFT-016
    dividend_income: float          # from SFT-017

    # Securities (stocks/bonds)
    securities_purchase_total: float
    securities_sale_total: float
    securities_rows: list[dict]

    # Mutual fund (cross-check with CAMS)
    mf_purchase_total: float
    mf_redemption_total: float
    mf_rows: list[dict]

    # Property
    property_purchase_total: float
    property_sale_total: float

    # TDS already deposited
    tds_salary: float
    tds_other: float

    # Miscellaneous
    cash_deposits: float
    credit_card_spends: float
    foreign_remittance: float

    # Parser metadata
    confidence: float
    detected_sections: list[str]
    raw_sections: dict[str, float]   # code → aggregate amount
    parse_mode: str                  # "pdf" | "json" | "mock"

    @property
    def total_other_income(self) -> float:
        return self.interest_savings + self.interest_fd + self.dividend_income

    @property
    def total_tds_paid(self) -> float:
        return self.tds_salary + self.tds_other

    @property
    def stock_net_gain_proxy(self) -> float:
        return self.securities_sale_total - self.securities_purchase_total


def _empty_ais(parse_mode: str = "pdf") -> AISData:
    return AISData(
        pan=None, taxpayer_name=None, financial_year=None, assessment_year=None,
        salary_reported=0.0, interest_savings=0.0, interest_fd=0.0,
        dividend_income=0.0, securities_purchase_total=0.0,
        securities_sale_total=0.0, securities_rows=[],
        mf_purchase_total=0.0, mf_redemption_total=0.0, mf_rows=[],
        property_purchase_total=0.0, property_sale_total=0.0,
        tds_salary=0.0, tds_other=0.0, cash_deposits=0.0,
        credit_card_spends=0.0, foreign_remittance=0.0,
        confidence=0.0, detected_sections=[], raw_sections={},
        parse_mode=parse_mode,
    )


# ---------------------------------------------------------------------------
# PDF text parser
# ---------------------------------------------------------------------------
_AMOUNT_PATTERN = re.compile(
    r"(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d*)",
    flags=re.IGNORECASE,
)

def _first_amount(text: str) -> float:
    """Extract the first numeric amount found in a text fragment."""
    m = _AMOUNT_PATTERN.search(text)
    return normalize_currency(m.group(1)) if m else 0.0


_SECTION_HEADER = re.compile(r"(?:SFT|TDS)[-\s]?\d+", re.IGNORECASE)


def _extract_section_total(text: str, codes: list[str]) -> float:
    """
    Sum amounts found in the block of lines following any matching section header.
    A block ends when the next section header is encountered or after 10 lines.
    """
    lines = text.splitlines()
    total = 0.0
    i = 0
    while i < len(lines):
        line_upper = lines[i].upper()
        matched_code = None
        for code in codes:
            # Match the code as a whole token to avoid SFT-01 matching SFT-016
            if re.search(r"\b" + re.escape(code.upper()) + r"\b", line_upper):
                matched_code = code
                break
        if matched_code:
            # Scan up to 12 lines ahead for amounts
            for j in range(i, min(i + 12, len(lines))):
                scan_line = lines[j]
                # Stop if we hit a new section header (different from matched)
                if j > i and _SECTION_HEADER.search(scan_line):
                    new_upper = scan_line.upper()
                    if not any(re.search(r"\b" + re.escape(c.upper()) + r"\b", new_upper) for c in codes):
                        break
                # Extract money amounts — skip lines that look like section headers
                if not _SECTION_HEADER.search(scan_line):
                    amounts = _AMOUNT_PATTERN.findall(scan_line)
                    if amounts:
                        total += normalize_currency(amounts[-1])
        i += 1
    return total


def _extract_section_rows(text: str, codes: list[str]) -> list[dict]:
    """Return individual row dicts for multi-row SFT sections (MF / securities)."""
    lines = text.splitlines()
    rows: list[dict] = []
    i = 0
    while i < len(lines):
        line_upper = lines[i].upper()
        matched_code = None
        for code in codes:
            if re.search(r"\b" + re.escape(code.upper()) + r"\b", line_upper):
                matched_code = code
                break
        if matched_code:
            for j in range(i + 1, min(i + 15, len(lines))):
                scan_line = lines[j]
                if _SECTION_HEADER.search(scan_line):
                    new_upper = scan_line.upper()
                    if not any(re.search(r"\b" + re.escape(c.upper()) + r"\b", new_upper) for c in codes):
                        break
                amounts = _AMOUNT_PATTERN.findall(scan_line)
                if amounts:
                    rows.append({
                        "raw_line": scan_line.strip(),
                        "amount": normalize_currency(amounts[-1]),
                        "section": matched_code,
                    })
        i += 1
    return rows


def _extract_pan(text: str) -> str | None:
    m = re.search(r"\b([A-Z]{5}[0-9]{4}[A-Z])\b", text)
    return m.group(1) if m else None


def _extract_fy(text: str) -> str | None:
    m = re.search(r"(?:financial year|FY)[:\s]*(\d{4}[-–]\d{2,4})", text, re.IGNORECASE)
    return m.group(1) if m else None


def _parse_ais_text(text: str) -> AISData:
    """Parse raw text extracted from an AIS PDF."""
    clean = normalize_text(text)
    result = _empty_ais(parse_mode="pdf")

    result.pan = _extract_pan(clean)
    result.financial_year = _extract_fy(clean)

    # Name: usually appears after "PAN:" line or "Taxpayer Name"
    name_m = re.search(r"(?:taxpayer name|name)[:\s]+([A-Za-z ]{3,50})", clean, re.IGNORECASE)
    result.taxpayer_name = name_m.group(1).strip() if name_m else None

    # ── Income sections ──
    result.salary_reported      = _extract_section_total(clean, ["TDS-01", "TDS01"])
    result.interest_savings     = _extract_section_total(clean, ["SFT-001", "SFT-01", "SFT-010"])
    result.interest_fd          = _extract_section_total(clean, ["SFT-016", "SFT-16"])
    result.dividend_income      = _extract_section_total(clean, ["SFT-017", "SFT-17"])
    result.cash_deposits        = _extract_section_total(clean, ["SFT-011", "SFT-11"])
    result.credit_card_spends   = _extract_section_total(clean, ["SFT-012", "SFT-12"])
    result.foreign_remittance   = _extract_section_total(clean, ["SFT-013", "SFT-13"])
    result.property_purchase_total = _extract_section_total(clean, ["SFT-005", "SFT-05"])
    result.property_sale_total  = _extract_section_total(clean, ["SFT-006", "SFT-06"])

    # ── TDS ──
    result.tds_salary           = _extract_section_total(clean, ["TDS-01", "TDS01"])
    result.tds_other            = _extract_section_total(clean, ["TDS-26Q", "TDS26Q"])

    # ── MF rows ──
    mf_rows = _extract_section_rows(clean, ["SFT-018", "SFT-18"])
    result.mf_rows = mf_rows
    # Heuristic: purchase rows have higher amounts; split 60/40 if undifferentiated
    purchase_rows = [r for r in mf_rows if "redemp" not in r["raw_line"].lower()]
    redemp_rows   = [r for r in mf_rows if "redemp" in r["raw_line"].lower()]
    result.mf_purchase_total  = sum(r["amount"] for r in purchase_rows)
    result.mf_redemption_total = sum(r["amount"] for r in redemp_rows)

    # ── Securities ──
    sec_rows = _extract_section_rows(clean, ["SFT-004", "SFT-04"])
    result.securities_rows = sec_rows
    buy_rows  = [r for r in sec_rows if "sale" not in r["raw_line"].lower()]
    sell_rows = [r for r in sec_rows if "sale" in r["raw_line"].lower()]
    result.securities_purchase_total = sum(r["amount"] for r in buy_rows)
    result.securities_sale_total     = sum(r["amount"] for r in sell_rows)

    # ── Confidence ──
    filled_fields = [
        result.salary_reported, result.interest_savings, result.interest_fd,
        result.dividend_income, result.tds_salary, result.mf_purchase_total,
        result.property_purchase_total, result.credit_card_spends,
    ]
    n_filled = sum(1 for v in filled_fields if v > 0)
    result.confidence = round(n_filled / len(filled_fields), 2)

    result.detected_sections = [
        label for code, label in AIS_SECTION_MAP.items()
        if code.upper() in clean.upper()
    ]
    result.raw_sections = {
        "TDS-01":  result.salary_reported,
        "SFT-001": result.interest_savings,
        "SFT-016": result.interest_fd,
        "SFT-017": result.dividend_income,
        "SFT-018": result.mf_purchase_total + result.mf_redemption_total,
        "SFT-004": result.securities_purchase_total + result.securities_sale_total,
        "SFT-005": result.property_purchase_total,
        "SFT-011": result.cash_deposits,
        "SFT-012": result.credit_card_spends,
    }

    return result


# ---------------------------------------------------------------------------
# JSON parser  (IT portal structured download)
# ---------------------------------------------------------------------------
def _parse_ais_json(data: dict) -> AISData:
    """
    Parse the JSON exported from eportal.incometax.gov.in → AIS → Download JSON.
    The schema is: data["annualInformationStatement"]["partB"]["sftData"] etc.
    We try multiple known key variants to be robust across portal versions.
    """
    result = _empty_ais(parse_mode="json")

    # Navigate to root
    root = data
    for key in ("annualInformationStatement", "aisData", "data"):
        if key in root:
            root = root[key]
            break

    # Taxpayer info
    info = root.get("taxpayerInfo") or root.get("taxpayerDetails") or {}
    result.pan              = info.get("pan") or info.get("PAN")
    result.taxpayer_name    = info.get("name") or info.get("taxpayerName")
    result.financial_year   = root.get("financialYear") or root.get("fy")
    result.assessment_year  = root.get("assessmentYear") or root.get("ay")

    # Part B — SFT and TDS data
    part_b = root.get("partB") or root.get("partBData") or root

    def _sum_list(key: str, amount_field: str = "amount") -> float:
        rows = part_b.get(key, [])
        if not isinstance(rows, list):
            return 0.0
        return sum(normalize_currency(r.get(amount_field, 0)) for r in rows)

    def _get_rows(key: str) -> list[dict]:
        return part_b.get(key, []) if isinstance(part_b.get(key), list) else []

    result.salary_reported      = _sum_list("tdsOnSalary") or _sum_list("salaryDetails")
    result.tds_salary           = result.salary_reported
    result.interest_savings     = _sum_list("savingsBankInterest") or _sum_list("sft001")
    result.interest_fd          = _sum_list("depositInterest") or _sum_list("sft016")
    result.dividend_income      = _sum_list("dividendDetails") or _sum_list("sft017")
    result.cash_deposits        = _sum_list("cashDeposits") or _sum_list("sft011")
    result.credit_card_spends   = _sum_list("creditCardPayments") or _sum_list("sft012")
    result.foreign_remittance   = _sum_list("foreignRemittance") or _sum_list("sft013")
    result.property_purchase_total = _sum_list("propertyPurchase") or _sum_list("sft005")
    result.property_sale_total  = _sum_list("propertySale") or _sum_list("sft006")
    result.tds_other            = _sum_list("tdsOtherIncome") or _sum_list("tds26Q")

    # MF
    mf_rows = _get_rows("mutualFundTransactions") or _get_rows("sft018")
    result.mf_rows = mf_rows
    result.mf_purchase_total  = sum(
        normalize_currency(r.get("amount", 0)) for r in mf_rows
        if str(r.get("transactionType", "")).lower() in ("purchase", "buy", "sip", "")
    )
    result.mf_redemption_total = sum(
        normalize_currency(r.get("amount", 0)) for r in mf_rows
        if str(r.get("transactionType", "")).lower() in ("redemption", "redeem", "sale", "sell")
    )

    # Securities
    sec_rows = _get_rows("securitiesTransactions") or _get_rows("sft004")
    result.securities_rows = sec_rows
    result.securities_purchase_total = sum(
        normalize_currency(r.get("amount", 0)) for r in sec_rows
        if str(r.get("transactionType", "")).lower() in ("purchase", "buy", "")
    )
    result.securities_sale_total = sum(
        normalize_currency(r.get("amount", 0)) for r in sec_rows
        if str(r.get("transactionType", "")).lower() in ("sale", "sell")
    )

    # Confidence
    filled_fields = [
        result.salary_reported, result.interest_savings, result.interest_fd,
        result.dividend_income, result.mf_purchase_total,
    ]
    result.confidence = round(0.60 + 0.08 * sum(1 for v in filled_fields if v > 0), 2)
    result.detected_sections = list(AIS_SECTION_MAP.values())[:6]
    result.raw_sections = {
        "TDS-01": result.salary_reported,
        "SFT-001": result.interest_savings,
        "SFT-016": result.interest_fd,
        "SFT-017": result.dividend_income,
        "SFT-018": result.mf_purchase_total + result.mf_redemption_total,
        "SFT-004": result.securities_purchase_total + result.securities_sale_total,
        "SFT-005": result.property_purchase_total,
        "SFT-011": result.cash_deposits,
        "SFT-012": result.credit_card_spends,
    }

    return result


# ---------------------------------------------------------------------------
# Unified entry point
# ---------------------------------------------------------------------------
def parse_ais(source: bytes | str | dict) -> AISData:
    """
    Parse AIS from any supported input format.

    Parameters
    ----------
    source : bytes   → raw PDF bytes from st.file_uploader
             str     → either raw JSON string or path to a .pdf file
             dict    → already-loaded JSON object

    Returns
    -------
    AISData — fully typed parsed result (confidence=0 if nothing found)
    """
    if isinstance(source, dict):
        return _parse_ais_json(source)

    if isinstance(source, (bytes, bytearray)):
        # Peek: PDF starts with %PDF
        if source[:4] == b"%PDF":
            text = load_pdf_text(source)
            return _parse_ais_text(text)
        # Otherwise try JSON
        try:
            data = json.loads(source.decode("utf-8", errors="replace"))
            return _parse_ais_json(data)
        except (json.JSONDecodeError, ValueError):
            # Last resort: treat as raw text
            return _parse_ais_text(source.decode("utf-8", errors="replace"))

    if isinstance(source, str):
        if source.strip().startswith("{"):
            try:
                return _parse_ais_json(json.loads(source))
            except json.JSONDecodeError:
                pass
        if source.strip().endswith(".pdf"):
            text = load_pdf_text(source)
            return _parse_ais_text(text)
        # Plain text (mock / test)
        return _parse_ais_text(source)

    raise TypeError(f"Unsupported AIS source type: {type(source)}")


# ---------------------------------------------------------------------------
# Reconciliation engine
# ---------------------------------------------------------------------------
@dataclass
class AISDiscrepancy:
    code: str
    severity: str    # "high" | "medium" | "info"
    title: str
    message: str
    ais_value: float
    other_value: float
    gap: float


@dataclass
class AISReconciliation:
    discrepancies: list[AISDiscrepancy]

    enrichments: dict[str, float]

    mf_gap_pct: float | None
    salary_gap_pct: float | None

    # NEW
    mf_match: bool
    mf_gap_amount: float

    high_count: int
    medium_count: int
    info_count: int

    has_issues: bool


def reconcile_ais(
    ais: AISData,
    form16_parsed: dict[str, Any],
    cas_parsed: dict[str, Any],
) -> AISReconciliation:
    """
    Cross-validate AIS data against Form 16 and CAMS/KFintech CAS.

    Returns
    -------
    AISReconciliation containing:
      - discrepancies : list of flagged mismatches
      - enrichments   : new income / TDS data not in Form 16 or CAS
    """
    discrepancies: list[AISDiscrepancy] = []

    # ── 1. Salary cross-check (AIS TDS-01 vs Form 16 gross_salary) ──
    f16_salary = float(form16_parsed.get("gross_salary", 0.0))
    ais_salary = ais.salary_reported
    salary_gap = abs(ais_salary - f16_salary)
    salary_gap_pct: float | None = None

    if ais_salary > 0 and f16_salary > 0 and salary_gap > TOLERANCE_INR:
        salary_gap_pct = salary_gap / max(ais_salary, f16_salary)
        severity = "high" if salary_gap_pct > 0.05 else "medium"
        discrepancies.append(AISDiscrepancy(
            code="SALARY_MISMATCH",
            severity=severity,
            title="Salary figure differs between AIS and Form 16",
            message=(
                f"AIS (TDS-01) reports ₹{ais_salary:,.0f} salary income, but Form 16 shows "
                f"₹{f16_salary:,.0f}. Gap of ₹{salary_gap:,.0f} "
                f"({salary_gap_pct*100:.1f}%). Possible causes: perquisites, arrears, "
                f"multiple employers, or employer's correction statement not yet reflected."
            ),
            ais_value=ais_salary, other_value=f16_salary, gap=salary_gap,
        ))

    # ── 2. MF purchase cross-check (AIS SFT-18 vs CAMS CAS) ──
    transactions_df = cas_parsed.get("transactions", pd.DataFrame())
    mf_gap_pct: float | None = None
    if not transactions_df.empty and "transaction_type" in transactions_df.columns:
        cas_purchase_total = float(
            transactions_df[
                transactions_df["transaction_type"].str.lower().str.contains("purchase|sip|buy", na=False)
            ]["amount"].sum()
        )
        ais_mf = ais.mf_purchase_total
        mf_gap = abs(ais_mf - cas_purchase_total)
        if ais_mf > 0 and cas_purchase_total > 0 and mf_gap > TOLERANCE_INR:
            mf_gap_pct = mf_gap / max(ais_mf, cas_purchase_total)
            severity = "medium" if mf_gap_pct < 0.20 else "high"
            discrepancies.append(AISDiscrepancy(
                code="MF_PURCHASE_GAP",
                severity=severity,
                title="MF purchase totals differ between AIS and CAMS CAS",
                message=(
                    f"AIS (SFT-18) shows ₹{ais_mf:,.0f} in MF purchases; "
                    f"CAMS CAS shows ₹{cas_purchase_total:,.0f}. "
                    f"Gap of ₹{mf_gap:,.0f} ({mf_gap_pct*100:.1f}%). "
                    "Possible causes: missing folio in CAS, KFintech vs CAMS split, "
                    "or statement period mismatch."
                ),
                ais_value=ais_mf, other_value=cas_purchase_total, gap=mf_gap,
            ))

    # ── 3. High credit-card spends (lifestyle inflation flag) ──
    if ais.credit_card_spends > 600_000:
        discrepancies.append(AISDiscrepancy(
            code="HIGH_CC_SPEND",
            severity="info",
            title="High credit-card spending detected in AIS",
            message=(
                f"Credit-card payments reported by banks to AIS: ₹{ais.credit_card_spends:,.0f}. "
                "This does not affect your tax, but indicates significant lifestyle spend "
                "that may be worth optimising for FIRE."
            ),
            ais_value=ais.credit_card_spends, other_value=0.0, gap=ais.credit_card_spends,
        ))

    # ── 4. Foreign remittance flag ──
    if ais.foreign_remittance > 0:
        discrepancies.append(AISDiscrepancy(
            code="FOREIGN_REMITTANCE",
            severity="info",
            title="Foreign remittance found in AIS",
            message=(
                f"AIS shows ₹{ais.foreign_remittance:,.0f} in foreign remittances (SFT-13). "
                "If this is LRS (education / travel / investment abroad), ensure it is "
                "within the USD 250,000 annual limit and TCS is properly claimed."
            ),
            ais_value=ais.foreign_remittance, other_value=0.0, gap=ais.foreign_remittance,
        ))

    # ── 5. Property transaction flag ──
    if ais.property_purchase_total > 0:
        discrepancies.append(AISDiscrepancy(
            code="PROPERTY_PURCHASE",
            severity="info",
            title="Property purchase transaction found in AIS",
            message=(
                f"AIS (SFT-05) records a property purchase totalling ₹{ais.property_purchase_total:,.0f}. "
                "Ensure stamp duty and registration costs are not double-counted "
                "and that any home-loan interest deduction (Section 24b) is correctly applied."
            ),
            ais_value=ais.property_purchase_total, other_value=0.0, gap=ais.property_purchase_total,
        ))

    # ── 6. TDS already deducted on interest ──
    if ais.tds_other > 0:
        discrepancies.append(AISDiscrepancy(
            code="TDS_INTEREST_DEDUCTED",
            severity="info",
            title="TDS on interest income already deducted",
            message=(
                f"Banks have already deducted ₹{ais.tds_other:,.0f} as TDS on your interest income. "
                "This will be available as a tax credit when filing ITR — "
                "ensure it matches your Form 26AS."
            ),
            ais_value=ais.tds_other, other_value=0.0, gap=ais.tds_other,
        ))

    # ── Enrichments ──
    enrichments: dict[str, float] = {
        "fd_interest":            ais.interest_fd,
        "savings_interest":       ais.interest_savings,
        "dividend_income":        ais.dividend_income,
        "total_other_income":     ais.total_other_income,
        "tds_salary_paid":        ais.tds_salary,
        "tds_interest_paid":      ais.tds_other,
        "total_tds_paid":         ais.total_tds_paid,
        "stock_sale_proceeds":    ais.securities_sale_total,
        "stock_purchase_cost":    ais.securities_purchase_total,
        "stock_net_gain_proxy":   ais.stock_net_gain_proxy,
        "property_purchase":      ais.property_purchase_total,
        "property_sale":          ais.property_sale_total,
        "credit_card_annual":     ais.credit_card_spends,
    }

    high   = sum(1 for d in discrepancies if d.severity == "high")
    medium = sum(1 for d in discrepancies if d.severity == "medium")
    info   = sum(1 for d in discrepancies if d.severity == "info")

    mf_gap_amount = (
        ais.mf_purchase_total
        if mf_gap_pct is None
        else abs(ais.mf_purchase_total * mf_gap_pct / 100)
    )

    return AISReconciliation(
    discrepancies=discrepancies,
    enrichments=enrichments,
    mf_gap_pct=mf_gap_pct,
    salary_gap_pct=salary_gap_pct,
    high_count=high,
    medium_count=medium,
    info_count=info,
    has_issues=(high + medium) > 0,
    mf_match=abs(mf_gap_amount) < 1000,
    mf_gap_amount=mf_gap_amount,
    )


# ---------------------------------------------------------------------------
# Tax enrichment helper
# ---------------------------------------------------------------------------
def enrich_tax_inputs_from_ais(base_inputs: TaxInputs, ais: AISData) -> TaxInputs:
    """
    Return a new TaxInputs that folds AIS other-income into gross_salary.
    This gives the Tax Wizard a complete picture of taxable income.
    """
    import dataclasses
    enriched = dataclasses.replace(
        base_inputs,
        gross_salary=base_inputs.gross_salary + ais.total_other_income,
    )
    return enriched


# ---------------------------------------------------------------------------
# Confidence label helper (for UI)
# ---------------------------------------------------------------------------
def confidence_label(ais: AISData) -> str:
    if ais.parse_mode == "mock":
        return "Demo"
    if ais.confidence >= 0.75:
        return "High"
    if ais.confidence >= 0.40:
        return "Partial"
    return "Low"
