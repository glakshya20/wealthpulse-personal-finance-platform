from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
)
from reportlab.lib.units import inch


def money(v):
    try:
        return f"Rs. {float(v):,.0f}"
    except Exception:
        return str(v)


def generate_financial_report(
    output_path,
    tax_summary,
    portfolio_summary,
    fire_plan,
    health,
    ais_parsed=None,
    ais_reconciliation=None,
):
    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(output_path)

    story = []

    story.append(Paragraph("<b>ET WealthPulse AI Financial Report</b>", styles["Title"]))
    story.append(Spacer(1, 0.25 * inch))

    story.append(
        Paragraph(
            "Automatically generated financial health report.",
            styles["Normal"],
        )
    )

    story.append(Spacer(1, 0.25 * inch))

    # ---------------------------------------------------
    # Executive Summary
    # ---------------------------------------------------

    story.append(Paragraph("<b>Executive Summary</b>", styles["Heading1"]))

    story.append(
        Paragraph(
            f"Money Health Score: <b>{health['total_score']}/100</b>",
            styles["Normal"],
        )
    )

    story.append(
        Paragraph(
            f"Tax Alpha: <b>{money(tax_summary['tax_alpha'])}</b>",
            styles["Normal"],
        )
    )

    story.append(
        Paragraph(
            f"Portfolio XIRR: <b>{portfolio_summary['portfolio_xirr']}</b>",
            styles["Normal"],
        )
    )

    story.append(
        Paragraph(
            f"FIRE Target Corpus: <b>{money(fire_plan['target_corpus'])}</b>",
            styles["Normal"],
        )
    )

    story.append(Spacer(1, 0.25 * inch))

    # ---------------------------------------------------
    # Tax
    # ---------------------------------------------------

    story.append(Paragraph("<b>Tax Wizard</b>", styles["Heading1"]))

    story.append(
        Paragraph(
            f"Recommended Regime: <b>{tax_summary['better_regime'].title()}</b>",
            styles["Normal"],
        )
    )

    story.append(
        Paragraph(
            f"Annual Tax Saving Opportunity: <b>{money(tax_summary['tax_alpha'])}</b>",
            styles["Normal"],
        )
    )

    story.append(Spacer(1, 0.25 * inch))

    # ---------------------------------------------------
    # FIRE
    # ---------------------------------------------------

    story.append(Paragraph("<b>FIRE Planner</b>", styles["Heading1"]))

    story.append(
        Paragraph(
            f"Required Monthly Investment: {money(fire_plan['required_total_monthly'])}",
            styles["Normal"],
        )
    )

    story.append(
        Paragraph(
            f"Additional Monthly Needed: {money(fire_plan['additional_monthly_needed'])}",
            styles["Normal"],
        )
    )

    story.append(Spacer(1, 0.25 * inch))

    # ---------------------------------------------------
    # Money Health
    # ---------------------------------------------------

    story.append(Paragraph("<b>Money Health</b>", styles["Heading1"]))

    for d in health["dimensions"]:

        story.append(
            Paragraph(
                f"{d['dimension']} : {d['score']:.1f}/100",
                styles["Normal"],
            )
        )

    story.append(Spacer(1, 0.25 * inch))

    # ---------------------------------------------------
    # AIS
    # ---------------------------------------------------

    if ais_parsed:

        story.append(Paragraph("<b>AIS Summary</b>", styles["Heading1"]))

        story.append(
            Paragraph(
                f"Salary : {money(ais_parsed.salary_reported)}",
                styles["Normal"],
            )
        )

        story.append(
            Paragraph(
                f"Other Income : {money(ais_parsed.total_other_income)}",
                styles["Normal"],
            )
        )

        story.append(
            Paragraph(
                f"TDS : {money(ais_parsed.total_tds_paid)}",
                styles["Normal"],
            )
        )

        if ais_reconciliation:

            story.append(Spacer(1, 0.15 * inch))

            story.append(
                Paragraph(
                    "<b>AIS Cross Verification</b>",
                    styles["Heading2"],
                )
            )

            if ais_reconciliation.discrepancies:

                for d in ais_reconciliation.discrepancies:

                    story.append(
                        Paragraph(
                            f"• {d.title}",
                            styles["Normal"],
                        )
                    )

            else:

                story.append(
                    Paragraph(
                        "No reconciliation issues detected.",
                        styles["Normal"],
                    )
                )

    doc.build(story)
    #oknow
