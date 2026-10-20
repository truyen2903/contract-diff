from app.extractors.pdf_extractor import extract_pdf

def extract_document(filename, file_stream):
    pages= extract_pdf(file_stream)
    page_count = len(pages)
    return {
    "filename":filename,
    "page_count":page_count,
    "pages":pages
            }

