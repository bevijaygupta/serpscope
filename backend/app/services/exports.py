"""Export helpers. All cell values are sanitised against spreadsheet injection."""
from __future__ import annotations

import io
import json
from typing import Any, Iterable

from app.core.url_utils import safe_csv_value


def _rows_to_dicts(rows: Iterable[Any], columns: list[str]) -> list[dict]:
    out = []
    for row in rows:
        if isinstance(row, dict):
            out.append({c: row.get(c) for c in columns})
        else:
            out.append({c: safe_value(getattr(row, c, None)) for c in columns})
    return out


def safe_value(value: Any) -> Any:
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def export_csv(rows: Iterable[Any], columns: list[str], filename: str = "export.csv") -> tuple[bytes, str, str]:
    import csv

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for item in _rows_to_dicts(rows, columns):
        writer.writerow({k: safe_csv_value(safe_value(v)) for k, v in item.items()})
    return buf.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", filename


def export_json(rows: Iterable[Any], columns: list[str], filename: str = "export.json") -> tuple[bytes, str, str]:
    payload = _rows_to_dicts(rows, columns)
    return (
        json.dumps(payload, default=str, ensure_ascii=False, indent=2).encode("utf-8"),
        "application/json",
        filename,
    )


def export_xlsx(rows: Iterable[Any], columns: list[str], filename: str = "export.xlsx") -> tuple[bytes, str, str]:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(columns)
    for item in _rows_to_dicts(rows, columns):
        ws.append([safe_csv_value(safe_value(item.get(c))) for c in columns])
    ws.freeze_panes = "A2"
    stream = io.BytesIO()
    wb.save(stream)
    return (
        stream.getvalue(),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename,
    )


def export_pdf_report(title: str, sections: list[dict], filename: str = "report.pdf") -> tuple[bytes, str, str]:
    """Simple text-based PDF report. `sections` = [{heading, lines: []}]."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    stream = io.BytesIO()
    doc = SimpleDocTemplate(stream, pagesize=A4, title=title)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, styles["Title"]), Spacer(1, 12)]
    for section in sections:
        story.append(Paragraph(section.get("heading", ""), styles["Heading2"]))
        for line in section.get("lines", []):
            safe = str(line).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(safe, styles["BodyText"]))
        story.append(Spacer(1, 8))
    doc.build(story)
    return stream.getvalue(), "application/pdf", filename


def export_pptx_report(title: str, slides: list[dict], filename: str = "audit.pptx") -> tuple[bytes, str, str]:
    """Generate an editable PowerPoint deck from structured audit sections.

    `slides` = [{"title": str, "bullets": [str], "note": str}]. Text-only slides
    keep the deck small and ensure every claim remains traceable to the audit.
    """
    from pptx import Presentation
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    title_layout = prs.slide_layouts[0]
    body_layout = prs.slide_layouts[1]

    cover = prs.slides.add_slide(title_layout)
    cover.shapes.title.text = title
    if len(cover.placeholders) > 1:
        cover.placeholders[1].text = "SERPScope · source-tracked public-evidence audit"

    for item in slides[:60]:
        slide = prs.slides.add_slide(body_layout)
        slide.shapes.title.text = str(item.get("title", "Slide"))[:120]
        body = slide.placeholders[1].text_frame
        body.clear()
        bullets = item.get("bullets") or []
        for index, line in enumerate(bullets[:10]):
            paragraph = body.paragraphs[0] if index == 0 else body.add_paragraph()
            paragraph.text = str(line)[:500]
            paragraph.level = 0
            for run in paragraph.runs:
                run.font.size = Pt(15)
        note = str(item.get("note") or "").strip()
        if note:
            box = slide.shapes.add_textbox(Inches(0.7), Inches(6.55), Inches(11.9), Inches(0.55))
            frame = box.text_frame
            frame.word_wrap = True
            frame.text = note[:500]
            for paragraph in frame.paragraphs:
                for run in paragraph.runs:
                    run.font.size = Pt(9)
    stream = io.BytesIO()
    prs.save(stream)
    return (
        stream.getvalue(),
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename,
    )


def make_export(fmt: str, rows: Iterable[Any], columns: list[str], base: str, pdf_sections: list[dict] | None = None):
    fmt = (fmt or "csv").lower()
    if fmt == "json":
        return export_json(rows, columns, f"{base}.json")
    if fmt == "xlsx":
        return export_xlsx(rows, columns, f"{base}.xlsx")
    if fmt == "pdf":
        sections = pdf_sections or [{"heading": base, "lines": [str(r) for r in rows][:200]}]
        return export_pdf_report(base.replace("_", " ").title(), sections, f"{base}.pdf")
    if fmt == "csv":
        return export_csv(rows, columns, f"{base}.csv")
    raise ValueError(f"Unsupported export format: {fmt}")
