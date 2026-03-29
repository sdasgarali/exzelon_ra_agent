"""PDF invoice generator using reportlab."""
import os
from pathlib import Path
from datetime import date
import structlog

logger = structlog.get_logger()

# Anchor to backend/ directory
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent.parent


def generate_invoice_pdf(invoice, line_items, tenant) -> str:
    """Generate a PDF invoice and return the file path.

    Args:
        invoice: Invoice model instance
        line_items: list of InvoiceLineItem instances
        tenant: Tenant model instance

    Returns:
        Relative path to generated PDF file
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
    from app.core.config import settings

    # Create output directory
    invoice_dir = _BACKEND_DIR / "data" / "invoices" / str(invoice.tenant_id)
    invoice_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{invoice.invoice_number}.pdf"
    filepath = invoice_dir / filename

    doc = SimpleDocTemplate(
        str(filepath),
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    elements = []

    # Custom styles
    title_style = ParagraphStyle(
        "InvoiceTitle", parent=styles["Heading1"],
        fontSize=24, textColor=HexColor("#1e293b"), spaceAfter=4,
    )
    company_style = ParagraphStyle(
        "Company", parent=styles["Normal"],
        fontSize=10, textColor=HexColor("#475569"), leading=14,
    )
    section_header = ParagraphStyle(
        "SectionHeader", parent=styles["Heading3"],
        fontSize=11, textColor=HexColor("#64748b"), spaceAfter=6,
        spaceBefore=16,
    )
    normal_style = ParagraphStyle(
        "NormalText", parent=styles["Normal"],
        fontSize=10, textColor=HexColor("#334155"), leading=14,
    )
    bold_style = ParagraphStyle(
        "BoldText", parent=styles["Normal"],
        fontSize=10, textColor=HexColor("#1e293b"), leading=14,
        fontName="Helvetica-Bold",
    )
    right_style = ParagraphStyle(
        "RightText", parent=styles["Normal"],
        fontSize=10, textColor=HexColor("#334155"), leading=14,
        alignment=TA_RIGHT,
    )
    right_bold = ParagraphStyle(
        "RightBold", parent=styles["Normal"],
        fontSize=11, textColor=HexColor("#1e293b"), leading=14,
        alignment=TA_RIGHT, fontName="Helvetica-Bold",
    )

    # ── Company Header ──
    company_name = settings.BILLING_COMPANY_NAME or settings.APP_NAME
    header_parts = []

    # Logo
    logo_path = settings.BILLING_COMPANY_LOGO_PATH
    if logo_path and os.path.isfile(logo_path):
        try:
            logo = Image(logo_path, width=1.5 * inch, height=0.75 * inch)
            logo.hAlign = "LEFT"
            header_parts.append(logo)
        except Exception:
            pass

    elements.append(Paragraph(company_name, title_style))

    contact_lines = []
    if settings.BILLING_COMPANY_ADDRESS:
        contact_lines.append(settings.BILLING_COMPANY_ADDRESS)
    contact_info = []
    if settings.BILLING_COMPANY_PHONE:
        contact_info.append(settings.BILLING_COMPANY_PHONE)
    if settings.BILLING_COMPANY_EMAIL:
        contact_info.append(settings.BILLING_COMPANY_EMAIL)
    if settings.BILLING_COMPANY_WEBSITE:
        contact_info.append(settings.BILLING_COMPANY_WEBSITE)
    if contact_info:
        contact_lines.append(" | ".join(contact_info))
    if contact_lines:
        elements.append(Paragraph("<br/>".join(contact_lines), company_style))

    elements.append(Spacer(1, 0.25 * inch))

    # ── Invoice Info ──
    inv_date = invoice.created_at.strftime("%B %d, %Y") if invoice.created_at else date.today().strftime("%B %d, %Y")
    due_str = invoice.due_date.strftime("%B %d, %Y") if invoice.due_date else "N/A"
    status_str = invoice.status.value.upper() if hasattr(invoice.status, 'value') else str(invoice.status).upper()

    inv_info = [
        [Paragraph("INVOICE", ParagraphStyle("InvLabel", parent=styles["Heading2"],
                   fontSize=16, textColor=HexColor("#1e293b"))),
         Paragraph(f"#{invoice.invoice_number}", right_bold)],
        [Paragraph("Date:", bold_style), Paragraph(inv_date, right_style)],
        [Paragraph("Due Date:", bold_style), Paragraph(due_str, right_style)],
        [Paragraph("Status:", bold_style), Paragraph(status_str, right_style)],
    ]
    inv_table = Table(inv_info, colWidths=[3.5 * inch, 3.5 * inch])
    inv_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(inv_table)
    elements.append(Spacer(1, 0.15 * inch))

    # ── Bill To ──
    elements.append(Paragraph("BILL TO", section_header))
    bill_to_lines = [tenant.name]
    if tenant.billing_email:
        bill_to_lines.append(tenant.billing_email)
    elif hasattr(tenant, 'domain') and tenant.domain:
        bill_to_lines.append(tenant.domain)
    if tenant.billing_address_json:
        import json
        try:
            addr = json.loads(tenant.billing_address_json) if isinstance(tenant.billing_address_json, str) else tenant.billing_address_json
            parts = []
            if addr.get("line1"):
                parts.append(addr["line1"])
            city_state = ", ".join(filter(None, [addr.get("city"), addr.get("state")]))
            if city_state:
                if addr.get("zip"):
                    city_state += f" {addr['zip']}"
                parts.append(city_state)
            if addr.get("country") and addr["country"] != "US":
                parts.append(addr["country"])
            bill_to_lines.extend(parts)
        except Exception:
            pass
    elements.append(Paragraph("<br/>".join(bill_to_lines), normal_style))
    elements.append(Spacer(1, 0.2 * inch))

    # ── Line Items Table ──
    def _fmt_cents(c):
        return f"${c / 100:,.2f}"

    table_data = [
        [Paragraph("<b>Description</b>", bold_style),
         Paragraph("<b>Qty</b>", ParagraphStyle("CB", parent=bold_style, alignment=TA_CENTER)),
         Paragraph("<b>Unit Price</b>", ParagraphStyle("RB", parent=bold_style, alignment=TA_RIGHT)),
         Paragraph("<b>Total</b>", ParagraphStyle("RB2", parent=bold_style, alignment=TA_RIGHT))],
    ]
    for item in line_items:
        item_type_val = item.item_type.value if hasattr(item.item_type, 'value') else str(item.item_type)
        if item_type_val == "tax":
            table_data.append([
                Paragraph(item.description, normal_style),
                Paragraph("", normal_style),
                Paragraph("", normal_style),
                Paragraph(_fmt_cents(item.total_cents), right_style),
            ])
        else:
            table_data.append([
                Paragraph(item.description, normal_style),
                Paragraph(str(item.quantity), ParagraphStyle("C", parent=normal_style, alignment=TA_CENTER)),
                Paragraph(_fmt_cents(item.unit_price_cents), right_style),
                Paragraph(_fmt_cents(item.total_cents), right_style),
            ])

    items_table = Table(table_data, colWidths=[3.5 * inch, 0.75 * inch, 1.25 * inch, 1.5 * inch])
    items_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HexColor("#f1f5f9")),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor("#1e293b")),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 6),
        ("TOPPADDING", (0, 1), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, 0), 1, HexColor("#cbd5e1")),
        ("LINEBELOW", (0, -1), (-1, -1), 1, HexColor("#e2e8f0")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(items_table)
    elements.append(Spacer(1, 0.2 * inch))

    # ── Totals ──
    totals_data = [
        [Paragraph("Subtotal:", right_style), Paragraph(_fmt_cents(invoice.subtotal_cents), right_bold)],
    ]
    if invoice.tax_cents > 0:
        totals_data.append([
            Paragraph("Tax:", right_style),
            Paragraph(_fmt_cents(invoice.tax_cents), right_bold),
        ])
    totals_data.append([
        Paragraph("<b>TOTAL:</b>", ParagraphStyle("TotalLabel", parent=right_bold, fontSize=13)),
        Paragraph(f"<b>{_fmt_cents(invoice.total_cents)}</b>",
                  ParagraphStyle("TotalVal", parent=right_bold, fontSize=13, textColor=HexColor("#059669"))),
    ])
    totals_table = Table(totals_data, colWidths=[5.25 * inch, 1.75 * inch])
    totals_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, HexColor("#1e293b")),
        ("TOPPADDING", (0, -1), (-1, -1), 8),
    ]))
    elements.append(totals_table)
    elements.append(Spacer(1, 0.4 * inch))

    # ── Footer ──
    footer_style = ParagraphStyle(
        "Footer", parent=styles["Normal"],
        fontSize=9, textColor=HexColor("#94a3b8"), alignment=TA_CENTER,
    )
    elements.append(Paragraph(f"Payment Terms: Due on {due_str}", footer_style))
    elements.append(Paragraph("Thank you for your business!", footer_style))

    # Build PDF
    doc.build(elements)

    # Return relative path from backend dir
    rel_path = str(filepath.relative_to(_BACKEND_DIR))
    logger.info("Invoice PDF generated", path=rel_path, invoice=invoice.invoice_number)
    return rel_path
