from __future__ import annotations

import json

from app.services.exports import export_csv, export_json, export_pdf_report, export_xlsx, make_export


ROWS = [
    {"url": "https://example.com/a", "title": "=CMD('calc')", "metrics": {"clicks": 10}},
    {"url": "https://example.com/b", "title": "Normal", "metrics": {"clicks": 4}},
]
COLUMNS = ["url", "title", "metrics"]


def test_csv_export_escapes_formula_and_keeps_columns():
    content, mime, filename = export_csv(ROWS, COLUMNS, "urls.csv")
    text = content.decode("utf-8-sig")
    assert mime.startswith("text/csv")
    assert filename == "urls.csv"
    assert "url,title,metrics" in text
    assert "'=CMD('calc')" in text or "\"'=CMD('calc')\"" in text


def test_json_export_contains_sanitised_nested_values():
    content, mime, _ = export_json(ROWS, COLUMNS)
    assert mime == "application/json"
    data = json.loads(content)
    assert data[0]["metrics"] == {"clicks": 10}
    assert data[1]["title"] == "Normal"


def test_xlsx_and_pdf_exports_produce_readable_files():
    xlsx, mime, _ = export_xlsx(ROWS, COLUMNS, "urls.xlsx")
    assert xlsx[:2] == b"PK"
    assert "spreadsheet" in mime
    pdf, mime, _ = export_pdf_report("SEO Report", [{"heading": "Summary", "lines": ["<b>escaped</b> & safe"]}], "r.pdf")
    assert pdf.startswith(b"%PDF")
    assert mime == "application/pdf"


def test_make_export_dispatches_formats():
    assert make_export("csv", ROWS, COLUMNS, "base")[2] == "base.csv"
    assert make_export("json", ROWS, COLUMNS, "base")[2] == "base.json"
    assert make_export("xlsx", ROWS, COLUMNS, "base")[2] == "base.xlsx"
    assert make_export("pdf", ROWS, COLUMNS, "base")[2] == "base.pdf"
