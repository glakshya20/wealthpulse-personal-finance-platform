<div align="center">

<img src="https://img.shields.io/badge/Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white"/>
<img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
<img src="https://img.shields.io/badge/PyMuPDF-00599C?style=for-the-badge"/>
<img src="https://img.shields.io/badge/Pandas-150458?style=for-the-badge&logo=pandas&logoColor=white"/>
<img src="https://img.shields.io/badge/Privacy--First-0b6e69?style=for-the-badge"/>

# WealthPulse — Personal Finance Intelligence Platform

**A local-first personal CFO that turns your financial documents into decisions.**  
Processes Form 16, CAMS/KFintech CAS, and the Income Tax AIS entirely on your machine — zero data leaves your device.

[Live Demo](https://wealthpulse-personal-finance-platform.streamlit.app/) · [LinkedIn](https://linkedin.com/in/lakshya-gupta7) · [GitHub](https://github.com/glakshya20)

</div>

---

## Overview

WealthPulse is a modular multi-agent personal finance platform built for salaried Indians. It reads the three documents most people receive every year — Form 16, CAMS/KFintech Consolidated Account Statement, and the Income Tax Annual Information Statement (AIS) — and produces a unified financial intelligence report with zero data transmission.

The system runs entirely on the user's machine. No backend, no database, no API calls with personal data.

---

## Features

**Tax Wizard**  
Computes tax liability under both old and new regimes for FY 2025-26. Adds Schedule OS income from AIS (FD interest, savings interest, dividends) to the taxable base, subtracts TDS already deposited by banks, and shows the exact net payable at ITR filing. Flags advance tax obligations under Section 234C when residual liability exceeds ₹10,000.

**AIS Insights** ← _core contribution_  
Parses the Income Tax Department's Annual Information Statement (PDF or JSON) entirely locally. Cross-validates it against Form 16 and CAMS to surface discrepancies — salary gaps, missing MF folios, phantom income — that most taxpayers miss. Shows every income category the IT Department already knows about and computes the tax impact.

**Portfolio X-Ray**  
Computes XIRR from dated CAMS transaction cash flows using a money-weighted return methodology. Detects regular-plan holdings and quantifies the annual drag from TER difference vs direct plans, down to the rupee.

**FIRE Planner**  
Projects retirement corpus using a 12% return / 6% inflation / 4% withdrawal model. Incorporates "found money" (tax savings + expense-ratio savings) as automatic investment input and shows the monthly gap to close.

**Money Health Score**  
Scores six dimensions — emergency fund, insurance coverage, debt-to-income, diversification, tax efficiency, and retirement gap — into a single weighted health index.

**Privacy-First Architecture**  
All computation happens in a local Python process. Documents are parsed into memory and discarded on session close. No data reaches any external server.

**Executive Summary Dashboard**
Provides a single-view financial snapshot including net worth allocation, tax optimization opportunities, retirement readiness, portfolio performance, AIS compliance status, and actionable recommendations.

**Downloadable Financial Report**
Exports a professionally formatted PDF financial report containing portfolio analysis, tax recommendations, FIRE projections, AIS findings, and personalized action items for future reference.

**🤖Advisor Chat**
Interactive AI-powered financial assistant that answers questions using insights generated from uploaded financial documents and WealthPulse analytics.

---

## AIS Integration — Technical Detail

The AIS engine (`ais_engine.py`) is the primary technical contribution of this project.

### Parser

`parse_ais(source)` accepts raw PDF bytes, a JSON string, a dict, or plain text. It auto-detects format by peeking at the first 4 bytes. The PDF parser uses a block-scanning approach — when it encounters a section header like `SFT-016`, it scans the next 12 lines for monetary amounts, which matches how IT portal PDFs are actually structured.

Supports all major AIS sections:

| Section           | Content                             |
| ----------------- | ----------------------------------- |
| TDS-01            | Salary (from employer)              |
| SFT-001 / SFT-016 | Savings + FD interest               |
| SFT-017           | Dividend income                     |
| SFT-018           | Mutual fund purchase / redemption   |
| SFT-004           | Securities (stocks) purchase / sale |
| SFT-005 / SFT-006 | Immovable property transactions     |
| SFT-011           | Cash deposits                       |
| SFT-012           | Credit card payments                |
| TDS-26Q           | TDS on non-salary income            |

### Reconciliation

`reconcile_ais(ais, form16, cas)` runs six cross-checks automatically and returns typed discrepancy objects with severity levels (`high / medium / info`):

- Salary gap between TDS-01 and Form 16 gross salary
- MF purchase gap between SFT-18 and CAMS CAS
- High credit-card spend flag (lifestyle inflation signal)
- Foreign remittance + LRS limit check
- Property purchase detection
- TDS-on-interest credit notice

### Tax Engine Integration

AIS other income flows into `TaxInputs` as four new optional fields (all defaulting to `0.0` — fully backward-compatible):

```python
ais_fd_interest: float = 0.0        # SFT-016
ais_savings_interest: float = 0.0   # SFT-001
ais_dividend_income: float = 0.0    # SFT-017
ais_tds_paid: float = 0.0           # TDS-26Q credit
```

`calculate_tax_for_regime()` places these under Schedule OS — no standard deduction applies — and returns `tds_credit` and `net_payable` alongside the existing `total_tax`. `compare_tax_regimes()` generates two new recommendations: Schedule OS declaration reminder and advance tax warning.

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                  User (browser / local)                   │
└───────────────────────┬──────────────────────────────────┘
                        │  PDF / JSON upload (stays local)
┌───────────────────────▼──────────────────────────────────┐
│              Streamlit Orchestrator  (app.py)             │
│   session state · page routing · recalculate pipeline     │
└──┬─────────────────┬─────────────────┬───────────────────┘
   │                 │                 │
   ▼                 ▼                 ▼
Form 16           CAMS CAS           AIS
Parser            Parser             Parser
   │                 │                 │
   └─────────┬────────┴───────┬──────────┘
      Finance Engine      AIS Engine│
                    │
                    │
      ┌─────────────┼───────────────────────────────────┐
      ▼             ▼            ▼            ▼          ▼
 Tax Wizard   Portfolio X-Ray  FIRE Planner Money Health Advisor Chat
                    │
                    ▼
          Report Generator (PDF Export)
```

### Agent Components

- **Document Parser Agent** — PyMuPDF text extraction with regex field detection and confidence scoring
- **AIS Agent** — Block-scanning PDF/JSON parser, 6-point reconciliation, TaxInputs enrichment
- **Tax Wizard Agent** — Dual-regime slab computation, Schedule OS income, TDS credit, advance tax detection
- **Portfolio X-Ray Agent** — XIRR from dated cash flows, expense-ratio drag by fund
- **FIRE Planner Agent** — PMT-based corpus projection with found-money routing
- **Money Health Agent** — Six-dimension weighted scoring
- **Orchestrator Agent** — Streamlit session state, pipeline coordination, manual fallback system

---

## Project Structure

```
wealthpulse-personal-finance-platform/
├── app.py                   # Streamlit UI, orchestration, all pages
├── finance_engine.py        # Tax engine, XIRR, FIRE, health score
├── ais_engine.py            # AIS parser, reconciler, tax enrichment
├── mock_data_generator.py   # Demo data with realistic AIS scenario'
├──report_generator.py       # Generates PDF financial report
├── requirements.txt
├── demo_docs/
│   ├── demo_form16.pdf
│   ├── demo_cams_statement.pdf
│   └── demo_ais.pdf
└── README.md
```

---

## Setup

```bash
git clone https://github.com/glakshya20/wealthpulse-personal-finance-platform.git
cd wealthpulse-personal-finance-platform

python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt
streamlit run app.py
```

App runs at [http://localhost:8501](http://localhost:8501). Demo mode loads automatically — no uploads required to explore all features.

### Getting your AIS

1. Go to [eportal.incometax.gov.in](https://eportal.incometax.gov.in)
2. Login → **Services → Annual Information Statement (AIS)**
3. **Download** → PDF or JSON (both supported)
4. Upload in the WealthPulse sidebar under "Upload AIS"

---

## Privacy

Documents are processed in Python memory within the local Streamlit session. Nothing is written to disk. No third-party service receives any data. Closing the tab discards everything.

Running locally (`streamlit run app.py`) gives the strongest guarantee — no data leaves your computer at all.

---

## Tech Stack

`Python`·`Streamlit` · `Pandas` · `NumPy` · `NumPy-Financial` · `pyxirr` · `PyMuPDF` · `Matplotlib` · `ReportLab (PDF generation)`

---

## Limitations

- AIS PDF parsing accuracy depends on the IT portal's layout, which varies by FY and download format
- Securities and property rows from AIS are used as tax signals, not for exact STCG/LTCG computation
- Non-MF assets (direct equity, NPS, PPF, crypto) require manual entry in the portfolio fallback panel

---

## Author

**Lakshya Gupta**  
[github.com/glakshya20](https://github.com/glakshya20) · [linkedin.com/in/lakshya-gupta7](https://linkedin.com/in/lakshya-gupta7) · [leetcode.com/u/glakshya](https://leetcode.com/u/glakshya/)
