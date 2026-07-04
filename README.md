



ET WEALTHPULSE
---
ET WealthPulse is a local-first personal finance intelligence platform that acts as a personal CFO. It analyzes Form 16 and Consolidated Account Statement (CAS) to generate actionable insights on tax savings, portfolio performance, and retirement planning — all while ensuring complete data privacy.

The system is built using a modular multi-agent architecture and runs entirely on the user's machine.

---

## Overview

ET WealthPulse transforms raw financial documents into structured insights by combining document parsing, financial modeling, and interactive visualization.

It provides:
- Tax optimization insights (Tax Alpha)
- Portfolio performance analysis (XIRR)
- Expense ratio savings detection
- FIRE (Financial Independence) planning
- Financial health scoring

All processing is performed locally with zero data transmission.

---

## Key Features

- Document Intelligence  
  Extracts structured data from Form 16 and CAMS/KFintech CAS PDFs  

- Tax Wizard  
  Compares old vs new tax regimes for FY 2025–26 and identifies optimal choice  

- Portfolio X-Ray  
  Computes XIRR, evaluates fund performance, and detects expense inefficiencies  

- FIRE Planner  
  Projects retirement corpus and calculates required investment gap  

- Money Health Score  
  Scores financial health across six key dimensions  

- Privacy-First Architecture  
  No storage, no APIs, no external data transfer  

- Interactive Dashboard  
  Multi-page Streamlit interface with detailed analytics  

- Manual Fallback System  
  Handles parsing failures with dynamic user input panels  

---

## System Architecture

ET WealthPulse follows a modular multi-agent design where each component performs a specific financial task.

### Agent Components

- Document Parser Agent  
  Extracts financial data from PDFs  

- Tax Wizard Agent  
  Computes tax liability and savings  

- Portfolio X-Ray Agent  
  Analyzes transactions and returns  

- FIRE Planner Agent  
  Models retirement projections  

- Money Health Agent  
  Evaluates overall financial health  

- Orchestrator Agent  
  Coordinates agents, manages state, and drives UI  
<img width="748" height="806" alt="image" src="https://github.com/user-attachments/assets/612ed36d-a40b-416e-ad17-5760f649d120" />


---

## How It Works

1. User selects Demo Mode or uploads Form 16 and CAS PDFs  
2. Document Parser extracts structured data  
3. Analysis agents process financial information  
4. Orchestrator compiles results  
5. Insights are displayed in the dashboard  

---

## Technical Highlights

- Fully local execution with zero data leakage  
- Confidence-based document parsing with fallback handling  
- Accurate financial modeling:
  - Latest tax slabs (FY 2025–26)  
  - XIRR computation  
  - FIRE projections (12% return, 6% inflation, 4% withdrawal)  
- Detection of “hidden savings” via expense ratio optimization  
- Modular design enabling future extensibility  

---

## Tech Stack

- Streamlit (UI & orchestration)  
- Pandas, NumPy (data processing)  
- NumPy-Financial, pyxirr (financial calculations)  
- PyMuPDF (PDF parsing)  
- Matplotlib (visualization)  

---

## Setup and Usage

### Clone Repository

```bash
git clone https://github.com/jainharshil34/ET-WealthPulse.git
cd ET-WealthPulse
````

### Install Dependencies

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Run Application

```bash
streamlit run app.py
```

Application runs at: [http://localhost:8501](http://localhost:8501)

---

## Demo Mode

Includes a built-in demo system with realistic financial data for testing without uploading personal documents.

---

## Project Structure

```
ET-WealthPulse/
├── app.py
├── finance_engine.py
├── mock_data_generator.py
├── requirements.txt
├── demo_docs/
├── .devcontainer/
└── README.md
```

---

## Error Handling & Resilience

* Confidence thresholds for document parsing
* Automatic fallback to manual input
* Safe defaults for missing data
* Handling of edge cases (empty portfolios, invalid inputs)
* Cached pipeline for performance

---

## Privacy

* No data storage
* No external APIs
* Fully local computation

---

## Limitations

* Parsing accuracy depends on document format
* Limited support for non-mutual fund assets
* Some manual intervention may be required

---

## Future Work

* Support for additional asset classes (stocks, crypto)
* Improved parsing robustness
* Real-time integrations
* Web deployment with secure local processing
* Advanced recommendation systems

---

## Contributing

Fork the repository and submit a pull request.

---

## Author

Harshil Jain
GitHub: [https://github.com/jainharshil34](https://github.com/jainharshil34)

---

## Acknowledgements

* Open-source Python ecosystem
* Financial analytics libraries
* Streamlit community

```



That pushes it into *top 1% GitHub projects*.
```
