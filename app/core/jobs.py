"""Job thuần chạy trong worker con: không import FastAPI, nhận đường dẫn và giới hạn tường minh."""

from app.engines.text_diff import diff_words
from app.engines.text_mapping import build_document_text, span_to_page_locations
from app.extractors.pdf_extractor import extract_pdf


class TextTooLongError(ValueError):
    pass


def extract_pdf_file(path, max_pages):
    with open(path, "rb") as file_stream:
        return extract_pdf(file_stream, max_pages)


def compare_pdf_files(old_path, new_path, max_pages, max_text_chars):
    # Kiểm tra xong tệp old mới parse tệp new (new có thể hỏng hoặc gây treo).
    # Lỗi input mang theo side ("old"/"new") để parent gắn đúng tên tệp.
    pages = {}
    data = {}
    for side, path in (("old", old_path), ("new", new_path)):
        try:
            pages[side] = extract_pdf_file(path, max_pages)
            data[side] = build_document_text(pages[side])
            if len(data[side]["fulltext"]) > max_text_chars:
                raise TextTooLongError(f"văn bản trích xuất vượt quá {max_text_chars} ký tự")
        except ValueError as error:
            error.side = side
            raise

    changes = diff_words(data["old"]["fulltext"], data["new"]["fulltext"])
    for change in changes:
        change["old_locations"] = span_to_page_locations(change["old_span"], data["old"]["page_ranges"])
        change["new_locations"] = span_to_page_locations(change["new_span"], data["new"]["page_ranges"])
    return pages["old"], pages["new"], changes
