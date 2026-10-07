"""
streamlit/pdf_export.py
-----------------------
PDF export utility for Auris regulatory reports.

Uses fpdf2 to generate professional PDFs with:
- Branded header (Auris logo text, report type, metadata)
- Structured body: shaded section headings, indented bullets, body paragraphs
- Paginated footer with confidentiality notice

Fixes applied:
  1. _safe() strips all non-latin-1 / emoji chars so Helvetica never errors.
  2. set_x(LEFT_MARGIN) before every multi_cell so we never start at x=200.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from fpdf import FPDF


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------
LEFT  = 10   # mm left margin / x anchor
RIGHT = 200  # mm right edge (A4 = 210 mm; fpdf default right margin = 10 mm)
WIDTH = RIGHT - LEFT  # usable body width = 190 mm


# ---------------------------------------------------------------------------
# Colour palette (RGB tuples)
# ---------------------------------------------------------------------------
_NAVY       = (10,  25,  60)
_WHITE      = (255, 255, 255)
_ACCENT     = (0,   102, 204)
_LIGHT_GRAY = (240, 244, 250)
_MID_GRAY   = (120, 130, 150)
_DARK_TEXT  = (20,  30,  50)


# ---------------------------------------------------------------------------
# Unicode / emoji safety
# ---------------------------------------------------------------------------

_SAFE_MAP: dict[str, str] = {
    "\u26a1": "[!]",  # ⚡
    "\u2705": "[OK]", # ✅
    "\u274c": "[X]",  # ❌
    "\u2713": "[OK]", # ✓
    "\u2022": "-",    # •
    "\u2014": "--",   # —
    "\u2013": "-",    # –
    "\u2019": "'",    # '
    "\u2018": "'",    # '
    "\u201c": '"',    # "
    "\u201d": '"',    # "
    "\u20b9": "Rs.",  # ₹
    "\u00a0": " ",    # nbsp
    "\u2026": "...",  # …
    "\u00b7": "-",    # ·
    "\u2192": "->",   # →
    "\u2190": "<-",   # ←
    "\u2248": "~",    # ≈
    "\u2260": "!=",   # ≠
    "\u25cf": "-",    # ●
    "\u25cb": "o",    # ○
    "\u25b6": ">",    # ▶
    "\u00b0": "deg",  # °
    "\u00d7": "x",    # ×
    "\u00f7": "/",    # ÷
    "\u221e": "inf",  # ∞
    "\u00ae": "(R)",  # ®
    "\u00a9": "(C)",  # ©
    "\u2122": "(TM)", # ™
}


def _safe(text: str) -> str:
    """Return a Helvetica-safe (latin-1) version of *text*."""
    text = unicodedata.normalize("NFC", str(text))
    for ch, rep in _SAFE_MAP.items():
        text = text.replace(ch, rep)
    # Remove any remaining code-points above U+00FF
    return "".join(c if ord(c) < 256 else "?" for c in text)


# ---------------------------------------------------------------------------
# Markdown → plain-text stripper
# ---------------------------------------------------------------------------

_MD_PATTERNS: list[tuple[re.Pattern, str]] = [
    # Headings → keep label text only
    (re.compile(r"^#{1,6}\s+(.+)$", re.M),  r"\1:"),
    (re.compile(r"\*\*(.+?)\*\*"),           r"\1"),
    (re.compile(r"\*(.+?)\*"),               r"\1"),
    (re.compile(r"`(.+?)`"),                 r"\1"),
    (re.compile(r"```[\s\S]*?```"),          ""),
    (re.compile(r"!\[.*?\]\(.*?\)"),         ""),
    (re.compile(r"\[(.+?)\]\(.+?\)"),        r"\1"),
    (re.compile(r"^\s*[-*+]\s+", re.M),     "- "),
    (re.compile(r"^\s*\d+\.\s+", re.M),     "- "),
    (re.compile(r"\|.+\|", re.M),           ""),
    (re.compile(r"^\s*[-=]{3,}\s*$", re.M), ""),
    (re.compile(r"&nbsp;"),                  " "),
    (re.compile(r"&amp;"),                   "&"),
]


def _strip_markdown(text: str) -> str:
    for pat, rep in _MD_PATTERNS:
        text = pat.sub(rep, text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# ---------------------------------------------------------------------------
# Line-type helpers
# ---------------------------------------------------------------------------

def _is_heading(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    return (len(s) < 90 and s.endswith(":")) or (s.isupper() and len(s) < 80)


def _is_bullet(line: str) -> bool:
    s = line.strip()
    return s.startswith("- ") or s.startswith("* ")


# ---------------------------------------------------------------------------
# FPDF subclass
# ---------------------------------------------------------------------------

class _AurisPDF(FPDF):
    def __init__(self, report_type: str, generated_by: str, period: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.report_type  = _safe(report_type)[:55]
        self.generated_by = _safe(generated_by)
        self.period       = _safe(period)
        self.generated_at = datetime.now(tz=timezone.utc).strftime("%d %b %Y, %H:%M UTC")
        self.set_auto_page_break(auto=True, margin=25)

    # ── Header ────────────────────────────────────────────────────────────
    def header(self) -> None:
        # Navy bar
        self.set_fill_color(*_NAVY)
        self.rect(0, 0, 210, 28, style="F")

        # Logo text
        self.set_font("Helvetica", style="B", size=15)
        self.set_text_color(*_WHITE)
        self.set_xy(10, 6)
        self.cell(50, 8, "Auris AI", ln=False)

        # Tagline
        self.set_font("Helvetica", size=7)
        self.set_text_color(180, 200, 240)
        self.set_xy(10, 16)
        self.cell(80, 5, "Compliance Copilot for Banking & NBFC Teams", ln=False)

        # Report type right
        self.set_font("Helvetica", style="B", size=9)
        self.set_text_color(*_WHITE)
        self.set_xy(105, 6)
        self.cell(95, 6, self.report_type, align="R", ln=False)

        # Period right
        self.set_font("Helvetica", size=7)
        self.set_text_color(180, 200, 240)
        self.set_xy(105, 13)
        self.cell(95, 5, f"Period: {self.period} | By: {self.generated_by}", align="R")

        # Accent rule
        self.set_draw_color(*_ACCENT)
        self.set_line_width(0.8)
        self.line(0, 28, 210, 28)
        self.set_xy(LEFT, 34)

    # ── Footer ────────────────────────────────────────────────────────────
    def footer(self) -> None:
        self.set_y(-18)
        self.set_draw_color(*_MID_GRAY)
        self.set_line_width(0.3)
        self.line(LEFT, self.get_y(), RIGHT, self.get_y())
        self.set_y(-15)
        self.set_font("Helvetica", size=7)
        self.set_text_color(*_MID_GRAY)
        self.set_x(LEFT)
        self.cell(60, 5, f"Generated: {self.generated_at}", align="L", ln=False)
        self.set_x(70)
        self.cell(90, 5, "Generated by Auris  |  CONFIDENTIAL - Internal Use Only", align="C", ln=False)
        self.set_x(160)
        self.cell(40, 5, f"Page {self.page_no()} / {{nb}}", align="R")


# ---------------------------------------------------------------------------
# Body rendering helpers
# ---------------------------------------------------------------------------

def _render_heading(pdf: FPDF, text: str) -> None:
    """Shaded heading bar with left accent stripe."""
    pdf.set_x(LEFT)
    pdf.ln(3)
    y = pdf.get_y()
    # Light gray fill
    pdf.set_fill_color(*_LIGHT_GRAY)
    pdf.rect(LEFT, y, WIDTH, 7.5, style="F")
    # Blue left stripe
    pdf.set_fill_color(*_ACCENT)
    pdf.rect(LEFT, y, 3, 7.5, style="F")
    # Heading text
    pdf.set_font("Helvetica", style="B", size=10)
    pdf.set_text_color(*_ACCENT)
    pdf.set_xy(LEFT + 5, y)
    pdf.cell(WIDTH - 5, 7.5, _safe(text.strip().rstrip(":")), ln=True)
    pdf.set_x(LEFT)
    pdf.ln(2)
    pdf.set_text_color(*_DARK_TEXT)


def _render_bullet(pdf: FPDF, text: str) -> None:
    """Indented bullet point with dash symbol."""
    body = _safe(text.strip().lstrip("-").lstrip("*").strip())
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(*_DARK_TEXT)
    # bullet dash
    pdf.set_x(16)
    pdf.cell(4, 5.5, "-", ln=False)
    # bullet text — width = 190 - 20 = 170 mm
    pdf.set_x(20)
    pdf.multi_cell(WIDTH - 10, 5.5, body)
    pdf.set_x(LEFT)


def _render_paragraph(pdf: FPDF, text: str) -> None:
    """Normal body paragraph, always anchored at LEFT margin."""
    pdf.set_font("Helvetica", size=9)
    pdf.set_text_color(*_DARK_TEXT)
    pdf.set_x(LEFT)
    pdf.multi_cell(WIDTH, 5.5, _safe(text.strip()))
    pdf.set_x(LEFT)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_report_to_pdf(
    report_content: str,
    report_type: str,
    generated_by: str,
    period: str,
) -> bytes:
    """
    Generate a professional PDF and return raw bytes for st.download_button.

    Parameters
    ----------
    report_content : str
        Body text (Markdown or plain text). Markdown stripped before render.
    report_type : str
        Human-readable type, e.g. "AML Summary Report".
    generated_by : str
        Username of the requesting officer.
    period : str
        Reporting period string, e.g. "01-10-2026 - 31-10-2026".

    Returns
    -------
    bytes
    """
    pdf = _AurisPDF(report_type=report_type, generated_by=generated_by, period=period)
    pdf.alias_nb_pages()
    pdf.add_page()

    # ── Title block ───────────────────────────────────────────────────────
    pdf.set_x(LEFT)
    pdf.set_font("Helvetica", style="B", size=14)
    pdf.set_text_color(*_ACCENT)
    pdf.cell(WIDTH, 9, _safe(report_type), ln=True)

    pdf.set_x(LEFT)
    pdf.set_font("Helvetica", size=8)
    pdf.set_text_color(*_MID_GRAY)
    meta = _safe(f"Period: {period}   |   Prepared by: {generated_by}   |   {datetime.now().strftime('%d %b %Y')}")
    pdf.cell(WIDTH, 5, meta, ln=True)

    # Accent underline
    pdf.set_draw_color(*_ACCENT)
    pdf.set_line_width(0.5)
    pdf.line(LEFT, pdf.get_y() + 2, RIGHT, pdf.get_y() + 2)
    pdf.ln(7)

    # ── Body ──────────────────────────────────────────────────────────────
    plain = _safe(_strip_markdown(report_content))
    for line in plain.split("\n"):
        raw = line.rstrip()

        if not raw.strip():
            pdf.ln(2)
            continue

        if _is_heading(raw):
            _render_heading(pdf, raw)
        elif _is_bullet(raw):
            _render_bullet(pdf, raw)
        else:
            _render_paragraph(pdf, raw)

    return bytes(pdf.output())
