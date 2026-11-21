import re
from itertools import islice

import pdfplumber
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfparser import PDFParser
from pdfplumber.utils.exceptions import PdfminerException

INVALID_PDF_MESSAGE = "Tệp PDF hỏng hoặc cần mật khẩu"
# Lỗi phía server, không phải lỗi dữ liệu PDF: luôn để lan ra (HTTP 500).
SERVER_ERRORS = (OSError, MemoryError)


class InvalidPDFError(ValueError):
    pass


class PDFPageLimitError(ValueError):
    pass


def raise_invalid_pdf(error):
    # pdfplumber bọc mọi lỗi trong PdfminerException; xét lỗi gốc bên trong.
    cause = error
    if isinstance(error, PdfminerException) and error.args:
        cause = error.args[0]
    if isinstance(cause, SERVER_ERRORS):
        raise error
    raise InvalidPDFError(INVALID_PDF_MESSAGE) from error


def count_pdf_pages(file_stream, max_pages: int) -> int:
    # Đếm bằng pdfminer trước khi mở pdfplumber: dừng ở trang max_pages + 1,
    # vì PDF.close() của pdfplumber dựng lại mọi trang.
    try:
        document = PDFDocument(PDFParser(file_stream), password="")
        return sum(1 for _ in islice(PDFPage.create_pages(document), max_pages + 1))
    except Exception as error:
        # Khối try chỉ gọi thư viện trên dữ liệu không tin cậy.
        raise_invalid_pdf(error)


def read_page_texts(file_stream) -> list[str]:
    try:
        with pdfplumber.open(file_stream) as pdf:
            return [page.extract_text() or "" for page in pdf.pages]
    except Exception as error:
        raise_invalid_pdf(error)


def check_page_count(file_stream, max_pages: int):
    file_stream.seek(0)
    page_count = count_pdf_pages(file_stream, max_pages)
    if page_count == 0:
        raise InvalidPDFError("Tệp PDF không có trang nào")
    if page_count > max_pages:
        raise PDFPageLimitError(f"Tệp PDF vượt quá {max_pages} trang")
    file_stream.seek(0)


def text_warnings(text) -> list[str]:
    warnings = []
    if "\x00" in text:
        warnings.append("NULL_CHARACTER")
    if not text.replace("\x00", "").strip():
        warnings.append("EMPTY_TEXT")
    return warnings


def extract_pdf(file_stream, max_pages: int) -> list[dict]:
    check_page_count(file_stream, max_pages)
    pages = []
    for page_number, text in enumerate(read_page_texts(file_stream), start=1):
        pages.append({
            "page_number": page_number,
            "text": text,
            "warnings": text_warnings(text),
        })
    return pages


def page_line_boxes(text, text_lines):
    # Ghép tọa độ theo thứ tự các dòng không trắng; lệch ở bất kỳ dòng nào thì không gắn tọa độ nào.
    # Tách dòng giống layout_cleaner để chỉ số dòng của hai tầng luôn khớp.
    lines = re.split(r"\r\n|\r|\n", text)
    filled = [index for index, line in enumerate(lines) if line.strip()]
    if len(filled) != len(text_lines):
        return None
    boxes = [None] * len(lines)
    for index, text_line in zip(filled, text_lines):
        if text_line["text"].strip() != lines[index].strip():
            return None
        boxes[index] = {key: float(text_line[key]) for key in ("x0", "top", "x1", "bottom")}
    return boxes


def image_coverage(images, width, height) -> float:
    # Tỷ lệ diện tích của ảnh lớn nhất (không cộng các ảnh chồng nhau).
    area = width * height
    if area <= 0:
        return 0.0
    largest = 0.0
    for image in images:
        image_width = max(0.0, min(image["x1"], width) - max(image["x0"], 0.0))
        image_height = max(0.0, min(image["bottom"], height) - max(image["top"], 0.0))
        largest = max(largest, image_width * image_height)
    return min(1.0, float(largest / area))


def read_page_layouts(file_stream) -> list[dict]:
    # Khối try chỉ gọi thư viện trên dữ liệu không tin cậy; xử lý kết quả nằm ngoài
    # để lỗi lập trình không bị dán nhãn thành "PDF hỏng".
    try:
        with pdfplumber.open(file_stream) as pdf:
            raw_pages = [{
                "text": page.extract_text() or "",
                "text_lines": page.extract_text_lines(strip=False, return_chars=False),
                "images": page.images,
                "width": float(page.width),
                "height": float(page.height),
            } for page in pdf.pages]
    except Exception as error:
        raise_invalid_pdf(error)
    return [{
        "text": page["text"],
        "width": page["width"],
        "height": page["height"],
        "line_boxes": page_line_boxes(page["text"], page["text_lines"]),
        "image_coverage": image_coverage(page["images"], page["width"], page["height"]),
    } for page in raw_pages]


def extract_pdf_lines(file_stream, max_pages: int) -> list[dict]:
    """Như extract_pdf, thêm kích thước trang, tọa độ từng dòng (khi ghép khớp) và độ phủ ảnh."""
    check_page_count(file_stream, max_pages)
    pages = []
    for page_number, layout in enumerate(read_page_layouts(file_stream), start=1):
        warnings = text_warnings(layout["text"])
        if layout["line_boxes"] is None and layout["text"].strip():
            warnings.append("LINE_GEOMETRY_UNAVAILABLE")
        pages.append({"page_number": page_number, **layout, "warnings": warnings})
    return pages
