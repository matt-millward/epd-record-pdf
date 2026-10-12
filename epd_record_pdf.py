#!/usr/bin/env python3
"""EPD Engineering Solutions Limited: branded record PDF generator.

Builds a single branded PDF for an Email, Call, Meeting or Note record.
Needs only ReportLab (pip install reportlab) and the ./assets folder that
sits next to this script. No absolute paths, no other dependencies.

Use as a library:
    from epd_record_pdf import build_record_pdf
    build_record_pdf("out.pdf", "Call", "2026-10-05_Call_Client-Person_Topic",
                     "Topic of the call",
                     [["Date", "2026-10-05"], ["Job", "26022 Client Project"]],
                     [{"type": "heading", "text": "Summary"},
                      {"type": "paragraph", "text": "What was said."}])

Use from the command line:
    python epd_record_pdf.py input.json output.pdf

See README.txt for the JSON fields.
"""
import html
import json
import os
import re
import sys
import unicodedata

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as _canvas
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                Paragraph, Spacer, Table, TableStyle)

# ---------------------------------------------------------------------------
# Assets: always resolved relative to this file, never to the working folder.
# ---------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
FONT_FILES = {
    "Serif": os.path.join(ASSETS, "fonts", "DMSerifDisplay-Regular.ttf"),
    "Sans": os.path.join(ASSETS, "fonts", "SourceSans3-Reg.ttf"),
    "SansB": os.path.join(ASSETS, "fonts", "SourceSans3-Semi.ttf"),
}
WORDMARK = os.path.join(ASSETS, "wordmark.png")

# Brand colours (unchanged from the approved design).
GOLD = HexColor("#C8A45C")
CHAR = HexColor("#1C1F26")
GREY = HexColor("#6b6e76")
DARKGOLD = HexColor("#8a6d2f")

RECORD_TYPES = ("Email", "Call", "Meeting", "Note")

_fonts_ready = False
_cmaps = {}


def _register_fonts():
    """Register the three brand fonts once. Fails with a clear message."""
    global _fonts_ready
    if _fonts_ready:
        return
    for name, path in FONT_FILES.items():
        if not os.path.isfile(path):
            raise FileNotFoundError(
                "Missing font file: %s (expected in ./assets/fonts next to "
                "epd_record_pdf.py)" % path)
        pdfmetrics.registerFont(TTFont(name, path))
        _cmaps[name] = pdfmetrics.getFont(name).face.charToGlyph
    if not os.path.isfile(WORDMARK):
        raise FileNotFoundError(
            "Missing wordmark: %s (expected in ./assets next to "
            "epd_record_pdf.py)" % WORDMARK)
    _fonts_ready = True


# ---------------------------------------------------------------------------
# Text cleaning: keeps odd characters from breaking the build.
# ---------------------------------------------------------------------------
_REMOVE = dict.fromkeys(
    [0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF, 0x00AD, 0x202A,
     0x202B, 0x202C, 0x202D, 0x202E], None)


def clean(text, font="Sans"):
    """Return text safe for ReportLab and covered by the given font.

    Normalises line endings and tabs, removes invisible and control
    characters, and replaces any character the font cannot draw with '?'
    (after trying a plain-letter fallback such as a ligature or accent).
    """
    if text is None:
        return ""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", "    ").replace("\u00a0", " ")
    text = text.translate(_REMOVE)
    cmap = _cmaps[font]
    out = []
    for ch in text:
        o = ord(ch)
        if ch == "\n":
            out.append(ch)
        elif o < 32 or 0x7F <= o < 0xA0:
            continue
        elif 0xD800 <= o <= 0xDFFF:
            out.append("?")
        elif o in cmap:
            out.append(ch)
        else:
            base = unicodedata.normalize("NFKD", ch)
            if base != ch and all(ord(c) in cmap for c in base):
                out.append(base)
            else:
                out.append("?")
    return "".join(out)


def _inline(text, markup=True, font="Sans"):
    """Escape text for ReportLab and apply the light inline markup.

    markup=True  : **bold** and `code` are honoured (summaries and notes).
    markup=False : text is shown exactly as written (email bodies).
    URLs always become links.
    """
    t = html.escape(clean(text, font), quote=False)
    if markup:
        t = re.sub(r"\*\*(.+?)\*\*", r'<font name="SansB">\1</font>', t)
        t = re.sub(r"`(.+?)`", r'<font color="#8a6d2f">\1</font>', t)

    def link(m):
        url = m.group(1)
        trail = ""
        while url and url[-1] in ".,;:!?":
            trail = url[-1] + trail
            url = url[:-1]
        return '<link href="%s" color="#8a6d2f">%s</link>%s' % (
            url.replace('"', "%22"), url, trail)

    return re.sub(r"(https?://(?:(?!&lt;|&gt;)[^\s<)])+)", link, t)


def _styles():
    return {
        "title": ParagraphStyle("t", fontName="Serif", fontSize=21, leading=26,
                                textColor=CHAR, spaceAfter=4),
        "kicker": ParagraphStyle("k", fontName="Sans", fontSize=9, leading=12,
                                 textColor=DARKGOLD, spaceAfter=6),
        "h2": ParagraphStyle("h2", fontName="Serif", fontSize=13.5, leading=17,
                             textColor=CHAR, spaceBefore=14, spaceAfter=5),
        "body": ParagraphStyle("b", fontName="Sans", fontSize=10.2,
                               leading=14.6, textColor=HexColor("#22252c"),
                               spaceAfter=7),
        "bullet": ParagraphStyle("bl", fontName="Sans", fontSize=10.2,
                                 leading=14.4,
                                 textColor=HexColor("#22252c"), leftIndent=12,
                                 bulletIndent=2, spaceAfter=3),
        "mk": ParagraphStyle("mk", fontName="SansB", fontSize=8.2, leading=11.5,
                             textColor=GREY),
        "mv": ParagraphStyle("mv", fontName="Sans", fontSize=9.6, leading=12.5,
                             textColor=CHAR),
    }


# ---------------------------------------------------------------------------
# Body blocks
# ---------------------------------------------------------------------------
def _list_items(value):
    if isinstance(value, str):
        return [x for x in value.splitlines() if x.strip()]
    return [str(x) for x in (value or []) if str(x).strip()]


def _markdown_flowables(md, S):
    """Tiny markdown subset: ## heading, - bullet, 1. item, paragraphs."""
    out, para = [], []

    def flush():
        if para:
            out.append(Paragraph(_inline(" ".join(para)), S["body"]))
            para.clear()

    for ln in clean(md).split("\n"):
        if ln.startswith("## "):
            flush()
            out.append(Paragraph(_inline(ln[3:].strip(), font="Serif"), S["h2"]))
        elif ln.startswith("- ") or ln.startswith("* "):
            flush()
            out.append(Paragraph(_inline(ln[2:]), S["bullet"], bulletText="\u2022"))
        elif re.match(r"^\d+\. ", ln):
            flush()
            num = re.match(r"^(\d+)\.", ln).group(1) + "."
            out.append(Paragraph(_inline(re.sub(r"^\d+\. ", "", ln)),
                                 S["bullet"], bulletText=num))
        elif not ln.strip():
            flush()
        else:
            para.append(ln.strip())
    flush()
    return out


def _block_flowables(block, S):
    """Turn one body block into flowables.

    A block is a plain string (a paragraph) or a dict with "type":
      heading   : {"type": "heading", "text": "Summary"}
      paragraph : {"type": "paragraph", "text": "..."}   markup allowed,
                  blank line = new paragraph, single newlines joined
      text      : {"type": "text", "text": "..."}        shown exactly as
                  written, line breaks kept (use for full email bodies)
      bullets   : {"type": "bullets", "items": ["a", "b"]}
      numbered  : {"type": "numbered", "items": ["a", "b"]}
      markdown  : {"type": "markdown", "text": "## Heading\\n- point"}
    """
    if isinstance(block, str):
        block = {"type": "paragraph", "text": block}
    kind = (block.get("type") or "paragraph").lower()
    text = block.get("text", "")
    out = []
    if kind == "heading":
        out.append(Paragraph(_inline(text, font="Serif"), S["h2"]))
    elif kind == "paragraph":
        for chunk in re.split(r"\n\s*\n", clean(text)):
            if chunk.strip():
                out.append(Paragraph(_inline(" ".join(chunk.split("\n"))),
                                     S["body"]))
    elif kind == "text":
        for chunk in re.split(r"\n\s*\n", clean(text)):
            if chunk.strip():
                lines = []
                for x in chunk.strip("\n").split("\n"):
                    lead = len(x) - len(x.lstrip(" "))
                    lines.append("&nbsp;" * lead + _inline(x.lstrip(" "), markup=False))
                out.append(Paragraph("<br/>".join(lines), S["body"]))
    elif kind in ("bullets", "numbered"):
        for n, item in enumerate(_list_items(block.get("items")), 1):
            mark = "\u2022" if kind == "bullets" else "%d." % n
            out.append(Paragraph(_inline(item), S["bullet"], bulletText=mark))
    elif kind == "markdown":
        out.extend(_markdown_flowables(text, S))
    else:
        raise ValueError("Unknown body block type: %r" % kind)
    return out


# ---------------------------------------------------------------------------
# Page furniture: header band, wordmark, footer, "Page X of Y"
# ---------------------------------------------------------------------------
class _NumberedCanvas(_canvas.Canvas):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._saved = []

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self.setFillColor(GREY)
            self.setFont("Sans", 8)
            self.drawRightString(A4[0] - 16 * mm, 11 * mm,
                                 "Page %d of %d" % (self._pageNumber, total))
            super().showPage()
        super().save()


def _footer_ref(record_ref):
    """First three underscore parts of the record reference."""
    return "_".join(clean(record_ref).split("_")[:3])


def _make_page_decorator(record_ref):
    ref = _footer_ref(record_ref)

    def deco(c, doc):
        w, h = A4
        c.saveState()
        c.setFillColor(CHAR)
        c.rect(0, h - 26 * mm, w, 26 * mm, stroke=0, fill=1)
        c.setFillColor(GOLD)
        c.rect(0, h - 26 * mm - 1.2 * mm, w, 1.2 * mm, stroke=0, fill=1)
        c.drawImage(WORDMARK, 16 * mm, h - 24 * mm, 31.2 * mm, 20 * mm,
                    mask="auto")
        c.setFillColor(GOLD)
        c.setFont("SansB", 9)
        c.drawRightString(w - 16 * mm, h - 14 * mm, "JOB RECORD")
        c.setFillColor(GREY)
        c.setFont("Sans", 8)
        c.drawString(16 * mm, 11 * mm,
                     "EPD Engineering Solutions Limited  |  " + ref)
        c.setStrokeColor(GOLD)
        c.setLineWidth(0.5)
        c.line(16 * mm, 15 * mm, w - 16 * mm, 15 * mm)
        c.restoreState()

    return deco


# ---------------------------------------------------------------------------
# Public function
# ---------------------------------------------------------------------------
def _normalise_meta(meta_fields):
    """Accept a dict, a list of [key, value] pairs or a list of dicts."""
    pairs = []
    if isinstance(meta_fields, dict):
        pairs = list(meta_fields.items())
    else:
        for item in meta_fields or []:
            if isinstance(item, dict):
                pairs.append((item.get("key") or item.get("label") or "",
                              item.get("value", "")))
            else:
                pairs.append((item[0], item[1]))
    out = []
    for k, v in pairs:
        if isinstance(v, (list, tuple)):
            v = ", ".join(str(x) for x in v)
        if v is None or str(v).strip() == "":
            continue
        out.append((str(k).strip(), str(v)))
    return out


def build_record_pdf(output_path, record_type, record_ref, title, meta_fields,
                     body_blocks, attachments=None):
    """Build one branded record PDF and return output_path.

    output_path   : where to write the PDF.
    record_type   : "Email", "Call", "Meeting" or "Note".
    record_ref    : the record ID, e.g.
                    "2026-10-08_Email_DB-Structures-Janis_Meeting-minutes".
                    The footer shows its first three underscore parts.
    title         : record title. "<Type>: " is added if not already there.
    meta_fields   : ordered fields shown in the header block. "Date" and
                    "Job" (if present) also form the gold line above the
                    title; every other field appears in the table.
                    Email: Date, From, To, Cc, Subject.
                    Call/Meeting/Note: Date, Job, Participants, Source.
    body_blocks   : list of blocks (see _block_flowables).
    attachments   : optional list of file names, listed under "Attachments".
    """
    _register_fonts()
    rtype = str(record_type or "").strip().capitalize()
    if rtype not in RECORD_TYPES:
        raise ValueError("record_type must be one of %s, got %r"
                         % (", ".join(RECORD_TYPES), record_type))
    S = _styles()
    meta = _normalise_meta(meta_fields)
    lookup = {k.lower(): v for k, v in meta}

    title = clean(title or record_ref, "Serif").replace("\n", " ").strip()
    if not title.lower().startswith(rtype.lower() + ":"):
        title = "%s: %s" % (rtype, title)

    kicker = " | ".join(x for x in [rtype, lookup.get("date"), lookup.get("job")] if x)
    hidden = {"record id", "type", "date", "job"}
    rows = [[Paragraph(html.escape(clean(k, "SansB").upper()), S["mk"]),
             Paragraph(_inline(v, markup=False), S["mv"])]
            for k, v in meta if k.lower() not in hidden]

    story = []
    if kicker:
        story.append(Paragraph(html.escape(clean(kicker, "Sans").upper()), S["kicker"]))
    story.append(Paragraph(_inline(title, font="Serif"), S["title"]))
    if rows:
        kw = {}
        try:  # allows a very long To/Cc list to break across pages
            Table([[""]], splitInRow=1)
            kw["splitInRow"] = 1
        except TypeError:
            pass
        t = Table(rows, colWidths=[28 * mm, A4[0] - 32 * mm - 28 * mm],
                  hAlign="LEFT", **kw)
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, HexColor("#ddd6c6")),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story += [Spacer(1, 4), t]

    for block in body_blocks or []:
        story.extend(_block_flowables(block, S))

    names = _list_items(attachments)
    if names:
        story.append(Paragraph("Attachments", S["h2"]))
        for n in names:
            story.append(Paragraph(_inline(n, markup=False), S["bullet"],
                                   bulletText="\u2022"))

    out_dir = os.path.dirname(os.path.abspath(output_path))
    os.makedirs(out_dir, exist_ok=True)
    doc = BaseDocTemplate(output_path, pagesize=A4, title=title,
                          author="EPD Engineering Solutions Ltd",
                          leftMargin=16 * mm, rightMargin=16 * mm,
                          topMargin=34 * mm, bottomMargin=20 * mm)
    doc.addPageTemplates([PageTemplate(
        id="p",
        frames=[Frame(16 * mm, 20 * mm, A4[0] - 32 * mm, A4[1] - 54 * mm,
                      id="f", leftPadding=0, rightPadding=0, topPadding=0,
                      bottomPadding=0)],
        onPage=_make_page_decorator(record_ref))])
    doc.build(story, canvasmaker=_NumberedCanvas)
    return output_path


# ---------------------------------------------------------------------------
# Command line: python epd_record_pdf.py input.json output.pdf
# ---------------------------------------------------------------------------
def main(argv):
    if len(argv) != 3:
        sys.stderr.write("Usage: python epd_record_pdf.py input.json output.pdf\n")
        return 2
    with open(argv[1], encoding="utf-8-sig") as fh:
        data = json.load(fh)
    missing = [k for k in ("record_type", "record_ref", "title") if not data.get(k)]
    if missing:
        sys.stderr.write("Input JSON is missing: %s\n" % ", ".join(missing))
        return 2
    build_record_pdf(argv[2], data["record_type"], data["record_ref"],
                     data["title"], data.get("meta_fields"),
                     data.get("body_blocks"), data.get("attachments"))
    with open(argv[2], "rb") as fh:
        if fh.read(5) != b"%PDF-":
            sys.stderr.write("Output is not a valid PDF\n")
            return 1
    print("Wrote %s" % argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
