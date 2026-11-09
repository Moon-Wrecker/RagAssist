"""Document fixtures, built in code so the repository carries no binary files.

``pdf_document`` writes a valid PDF with a correct cross-reference table, one page per string.
"""

from __future__ import annotations

MARKDOWN_SAMPLE = """# Billing guide

## Invoices

Invoices are issued on the first day of each month. Café owners receive a PDF copy.

| plan | price |
|---|---|
| pro | 490 |
| enterprise | 2400 |

## Examples

```python
def total(items):
    return sum(items)
```
""".encode()

HTML_SAMPLE = (
    "<html><head><title>Billing guide</title><script>alert('x')</script></head>"
    "<body><h1>Billing guide</h1><h2>Invoices</h2>"
    "<p>Invoices are issued monthly. Café owners get copies.</p>"
    "<table><tr><th>plan</th><th>price</th></tr><tr><td>pro</td><td>490</td></tr></table>"
    "</body></html>"
).encode()

CSV_SAMPLE = "plan,price,currency\nCafé,490,EUR\npro,2400,USD\n".encode()

PDF_PAGES = ["Billing guide page one.", "Invoices page two."]

CORRUPT_PDF = b"%PDF-1.4\nthis is not a real document"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def pdf_document(pages: list[str]) -> bytes:
    """A minimal, valid PDF: catalog, page tree, one page and content stream per page, one font."""
    count = len(pages)
    font_id = 3 + 2 * count
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(count))
    objects: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode(),
        font_id: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for i, text in enumerate(pages):
        page_id, content_id = 3 + 2 * i, 4 + 2 * i
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 144] /Contents {content_id} 0 R "
            f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
        ).encode()
        stream = f"BT /F1 18 Tf 20 80 Td ({_escape(text)}) Tj ET".encode()
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"
    xref_at = len(out)
    size = font_id + 1
    out += f"xref\n0 {size}\n0000000000 65535 f \n".encode()
    for number in range(1, size):
        out += f"{offsets[number]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode()
    return bytes(out)


PDF_SAMPLE = pdf_document(PDF_PAGES)
