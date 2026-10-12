EPD RECORD PDF GENERATOR
========================
Builds the EPD branded record PDF (charcoal header band, gold rule, EPD
wordmark, "JOB RECORD" label, footer with record reference and Page X of Y)
for Email, Call, Meeting and Note records. ReportLab only. No laptop paths.

FOLDER LAYOUT
-------------
epd-record-pdf/
  epd_record_pdf.py        the script (library and command line)
  README.txt               this file
  assets/
    wordmark.png           EPD Engineering Solutions Limited wordmark (gold, transparent)
    fonts/
      DMSerifDisplay-Regular.ttf   titles and section headings
      SourceSans3-Reg.ttf          body text
      SourceSans3-Semi.ttf         bold text and labels
      OFL.txt                      font licences (SIL Open Font License 1.1)
  samples/
    call_input.json / call_output.pdf
    email_input.json / email_output.pdf

The script finds ./assets relative to its own location, so the folder can be
unzipped anywhere and run from any working directory.

INSTALL (fresh Linux, Python 3.8 or newer)
------------------------------------------
  pip install reportlab
(on a managed system: pip install --break-system-packages reportlab)

RUN
---
  python epd_record_pdf.py input.json output.pdf

From Python:
  from epd_record_pdf import build_record_pdf
  build_record_pdf(output_path, record_type, record_ref, title,
                   meta_fields, body_blocks, attachments=None)

JSON FIELDS
-----------
record_type   Email, Call, Meeting or Note (required)
record_ref    the record ID, for example
              2026-10-08_Email_DB-Structures-Janis_Meeting-minutes
              (required). The footer shows its first three underscore parts.
title         record title (required). "Email: " or "Call: " etc. is added
              if the title does not already start with it.
meta_fields   ordered list of [label, value] pairs (a plain object also works).
              Date and Job also form the gold line above the title. Every
              other field is shown in the header table. Empty values are
              skipped. A list value is joined with commas.
                Email:               Date, From, To, Cc, Subject
                Call/Meeting/Note:   Date, Job, Participants, Source
              "Record ID" and "Type" are accepted and not displayed.
body_blocks   list of blocks, each a plain string (a paragraph) or an object:
                {"type": "heading",   "text": "Summary"}
                {"type": "paragraph", "text": "..."}   blank line = new
                     paragraph; **bold** and `code` allowed
                {"type": "text",      "text": "..."}   shown exactly as
                     written with line breaks kept; use for full email bodies
                {"type": "bullets",   "items": ["a", "b"]}
                {"type": "numbered",  "items": ["a", "b"]}
                {"type": "markdown",  "text": "## Heading\n- point"}
attachments   optional list of file names, listed under "Attachments"

Typical Call/Meeting/Note body: heading "Summary" then paragraph, heading
"Key points" then bullets, heading "Decisions" then bullets, heading
"Actions" then bullets.

BEHAVIOUR NOTES
---------------
- Pound signs, curly quotes, accents and similar characters are supported.
- Characters the fonts cannot draw (emoji, Arabic, Chinese and so on) are
  printed as "?" so a record never fails to build. Invisible characters and
  control codes are removed. Tabs become four spaces.
- Long text wraps, long unbroken strings and URLs are broken to fit, and
  emails run across as many pages as needed. The header band and footer are
  repeated on every page.
- Web addresses in the text become clickable links.
- Exit code 0 means a PDF was written. Missing fields or a wrong record_type
  stop the run with a message.
