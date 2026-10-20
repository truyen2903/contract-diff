import pdfplumber
def extract_pdf(file_stream) -> list[dict]:
    pages = []
    with pdfplumber.open(file_stream) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            warnings = []  
            if "\x00" in text:
                warnings.append("NULL_CHARACTER")
            if not text.strip():
                warnings.append("EMPTY_TEXT")
            pages.append({
                "page_number": page_number,
                "text": text,
                "warnings": warnings,
            })
    return pages