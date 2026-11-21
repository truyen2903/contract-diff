"""Job thuần chạy trong worker con: không import FastAPI, nhận đường dẫn và giới hạn tường minh."""

import json
import pickle

from app.core import config
from app.engines.alignment_budget import AlignmentResultTooLargeError, StructureTooLargeError
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


def check_compact_size(result):
    # Include the same envelope and default pickle protocol used by the multiprocessing pipe.
    if len(pickle.dumps(("ok", result))) > config.MAX_COMPACT_BYTES:
        raise AlignmentResultTooLargeError("compact pickle exceeds 8 MiB")
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > config.MAX_COMPACT_BYTES:
        raise AlignmentResultTooLargeError("compact JSON exceeds 8 MiB")


def structured_job(old_input, new_input, source_type, max_text_chars, max_pages=None):
    from app.engines.compact_alignment import build_result
    from app.extractors.pdf_extractor import extract_pdf_lines
    from app.parsers.contract_parser import parse_contract_pages

    trees = []
    for side, value in (("old", old_input), ("new", new_input)):
        try:
            if source_type == "PDF_DIGITAL":
                with open(value, "rb") as stream:
                    pages = extract_pdf_lines(stream, max_pages)
            else:
                pages = [{"page_number": 1, "text": value}]
            length = sum(len(p["text"]) for p in pages) + 2 * max(0, len(pages) - 1)
            if length > max_text_chars:
                raise TextTooLongError(f"văn bản vượt quá {max_text_chars} ký tự")
            tree = parse_contract_pages(pages, source_type)
            if len(tree["nodes"]) > config.MAX_STRUCTURE_NODES:
                raise StructureTooLargeError(f"structure exceeds {config.MAX_STRUCTURE_NODES} nodes")
            trees.append(tree)
        except ValueError as error:
            error.side = side
            raise
    result = build_result(*trees)
    check_compact_size(result)
    return result


def compare_structured_texts(old_text, new_text, max_text_chars=config.MAX_TEXT_CHARS):
    return structured_job(old_text, new_text, "PLAIN_TEXT", max_text_chars)


def compare_structured_pdf_files(old_path, new_path, max_pages=config.MAX_PDF_PAGES,
                                 max_text_chars=config.MAX_TEXT_CHARS):
    return structured_job(old_path, new_path, "PDF_DIGITAL", max_text_chars, max_pages)
