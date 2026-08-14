"""Renders PDF summaries for the "Upload to Drive" bulk action (all 10 MGA
workflows) — the same field set already used for that workflow's Sheets export
row, turned into a real document instead of a spreadsheet row. See
docs/CONNECTORS_NANGO.md.
"""

from __future__ import annotations

import io

from reportlab.pdfgen import canvas

_PAGE_WIDTH = 612  # US Letter, points
_PAGE_HEIGHT = 792
_MARGIN = 54
_LINE_HEIGHT = 20


def _draw_summary_page(c: canvas.Canvas, title: str, fields: list[tuple[str, str]]) -> None:
    y = _PAGE_HEIGHT - _MARGIN

    c.setFont("Helvetica-Bold", 16)
    c.drawString(_MARGIN, y, title)
    y -= int(_LINE_HEIGHT * 1.5)

    c.setFont("Helvetica", 11)
    for label, value in fields:
        c.drawString(_MARGIN, y, f"{label}: {value}")
        y -= _LINE_HEIGHT


def render_summary_pdf(title: str, fields: list[tuple[str, str]]) -> bytes:
    """A title line followed by one "Label: value" line per field. No fancier
    layout is needed for a v1 approval summary."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(_PAGE_WIDTH, _PAGE_HEIGHT))
    _draw_summary_page(c, title, fields)
    c.save()
    return buf.getvalue()


def render_bulk_summary_pdf(title: str, rows: list[list[tuple[str, str]]]) -> bytes:
    """One page per item, each headed by ``title`` (e.g. "Submission Triage —
    SUB-1") — used by the bulk "Upload to Drive" action, which exports every
    item currently in a workflow's list in one PDF/one click. An empty ``rows``
    still produces a valid single-page PDF stating there's nothing to export,
    rather than a blank/broken file."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(_PAGE_WIDTH, _PAGE_HEIGHT))
    if not rows:
        _draw_summary_page(c, title, [("", "No items to export")])
    else:
        for i, fields in enumerate(rows):
            _draw_summary_page(c, title, fields)
            if i < len(rows) - 1:
                c.showPage()
    c.save()
    return buf.getvalue()
