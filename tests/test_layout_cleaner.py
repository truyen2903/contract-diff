import unicodedata
from io import BytesIO
from pathlib import Path

import pytest

from app.extractors.layout_cleaner import clean_layout, page_quality_warnings
from app.extractors.pdf_extractor import extract_pdf_lines, page_line_boxes


FIXTURES = Path(__file__).resolve().parent / "fixtures"
HEIGHT = 800.0


def box(top, x0=50.0):
    return {"x0": x0, "top": top, "x1": 500.0, "bottom": top + 10.0}


def pdf_page(page_number, rows):
    """rows: danh sách (text, top); top=None là dòng trắng."""
    return {
        "page_number": page_number,
        "text": "\n".join(text for text, _ in rows),
        "width": 600.0,
        "height": HEIGHT,
        "line_boxes": [None if top is None else box(top) for _, top in rows],
        "image_coverage": 0.0,
        "warnings": [],
    }


def text_page(text, page_number=1):
    return {"page_number": page_number, "text": text, "width": None, "height": None,
            "line_boxes": None, "image_coverage": 0.0, "warnings": []}


def masked_texts(layout):
    return [line["text"] for line in layout["lines"] if line["masked"]]


def assert_ledger_valid(layout, pages):
    """Mọi dòng nguồn còn trong sổ dòng; offset thô và offset chuẩn hóa khớp nhau."""
    by_page = {page["page_number"]: page["text"] for page in pages}
    normalized = layout["normalized_text"]
    for line in layout["lines"]:
        raw = by_page[line["page_number"]][line["raw_start"]:line["raw_end"]]
        assert "\n" not in raw and "\r" not in raw
        assert unicodedata.normalize("NFC", raw) == line["text"]
        assert normalized[line["clean_start"]:line["clean_end"]] == line["text"]
    per_page = [line["page_number"] for line in layout["lines"]]
    assert per_page == sorted(per_page)


# ── sổ dòng và chuẩn hóa ─────────────────────────────────

def test_plain_text_is_one_logical_page_without_geometry():
    layout = clean_layout([text_page("Điều 1. A\n\nNội dung")], "PLAIN_TEXT")

    assert layout["page_count"] == 1
    assert [line["text"] for line in layout["lines"]] == ["Điều 1. A", "", "Nội dung"]
    assert all(line["bbox"] is None for line in layout["lines"])
    assert layout["normalized_text"] == "Điều 1. A\n\nNội dung"


def test_nfd_is_normalized_per_line_with_raw_offsets_kept():
    raw = unicodedata.normalize("NFD", "Điều 1. Thanh toán\nBên A trả tiền")
    pages = [text_page(raw)]

    layout = clean_layout(pages, "PLAIN_TEXT")

    assert layout["lines"][0]["text"] == "Điều 1. Thanh toán"
    assert layout["lines"][0]["raw_end"] > len("Điều 1. Thanh toán")
    assert_ledger_valid(layout, pages)


def test_crlf_line_endings():
    pages = [text_page("A\r\nB\rC\n")]

    layout = clean_layout(pages, "PLAIN_TEXT")

    assert [line["text"] for line in layout["lines"]] == ["A", "B", "C", ""]
    assert layout["normalized_text"] == "A\nB\nC\n"
    assert_ledger_valid(layout, pages)


def test_pages_joined_by_double_newline_before_masking():
    pages = [pdf_page(1, [("Nội dung 1", 300.0), ("Trang 1", 780.0)]),
             pdf_page(2, [("Nội dung 2", 300.0), ("Trang 2", 780.0)])]

    with_mask = clean_layout(pages, "PDF_DIGITAL")
    without_mask = clean_layout(pages, "PDF_DIGITAL", enable_layout_cleaning=False)

    assert with_mask["normalized_text"] == "Nội dung 1\nTrang 1\n\nNội dung 2\nTrang 2"
    assert with_mask["normalized_text"] == without_mask["normalized_text"]
    assert [l["clean_start"] for l in with_mask["lines"]] == [l["clean_start"] for l in without_mask["lines"]]
    assert masked_texts(without_mask) == []
    assert_ledger_valid(with_mask, pages)


# ── Quy tắc A: số trang ──────────────────────────────────

def test_page_number_in_edge_zone_is_masked_even_for_one_page():
    pages = [pdf_page(1, [("Điều 1. A", 100.0), ("Trang 1 / 1", 785.0)])]

    layout = clean_layout(pages, "PDF_DIGITAL")

    assert masked_texts(layout) == ["Trang 1 / 1"]
    assert layout["lines"][1]["mask_reason"] == "PAGE_NUMBER"


def test_page_number_text_in_body_is_kept():
    pages = [pdf_page(1, [("Trang 2", 400.0), ("- 3 -", 300.0)])]

    assert masked_texts(clean_layout(pages, "PDF_DIGITAL")) == []


def test_without_geometry_page_number_is_only_a_candidate():
    pages = [text_page("Điều 1. A\nTrang 1/3")]

    layout = clean_layout(pages, "PLAIN_TEXT")

    assert masked_texts(layout) == []
    assert "LAYOUT_CANDIDATE" in layout["page_warnings"][0]["warnings"]


# ── Quy tắc B: header/footer lặp ─────────────────────────

def three_pages(header_top=10.0, header="CÔNG TY DEMO - HỢP ĐỒNG"):
    return [pdf_page(n, [(header, header_top), (f"Nội dung trang {n}.", 300.0)]) for n in (1, 2, 3)]


def test_repeated_header_is_masked_from_three_pages():
    layout = clean_layout(three_pages(), "PDF_DIGITAL")

    assert masked_texts(layout) == ["CÔNG TY DEMO - HỢP ĐỒNG"] * 3


def test_header_slightly_below_seven_percent_is_masked():
    # Header thực tế của fixture nằm tới 8,8% chiều cao trang.
    assert len(masked_texts(clean_layout(three_pages(header_top=60.0), "PDF_DIGITAL"))) == 3


def test_repeated_line_outside_edge_zone_is_kept():
    assert masked_texts(clean_layout(three_pages(header_top=200.0), "PDF_DIGITAL")) == []


def test_repeated_line_with_money_or_heading_is_kept():
    for header in ["Giá trị: 10.000.000 đồng", "Điều 1. Phạm vi", "Bên B phải bàn giao"]:
        assert masked_texts(clean_layout(three_pages(header=header), "PDF_DIGITAL")) == [], header


def test_repeated_header_is_not_masked_on_two_pages():
    pages = three_pages()[:2]

    assert masked_texts(clean_layout(pages, "PDF_DIGITAL")) == []


def test_two_page_footer_with_matching_page_numbers_is_masked():
    pages = [pdf_page(n, [("Nội dung.", 300.0), (f"Tài liệu mẫu. Trang {n} / 2", 770.0)]) for n in (1, 2)]

    assert masked_texts(clean_layout(pages, "PDF_DIGITAL")) == ["Tài liệu mẫu. Trang 1 / 2", "Tài liệu mẫu. Trang 2 / 2"]


def test_two_page_footer_with_wrong_page_numbers_is_kept():
    pages = [pdf_page(n, [("Nội dung.", 300.0), ("Tài liệu mẫu. Trang 1 / 2", 770.0)]) for n in (1, 2)]

    assert masked_texts(clean_layout(pages, "PDF_DIGITAL")) == []


# ── chất lượng trang ─────────────────────────────────────

def test_empty_pdf_page_is_flagged_but_signature_page_is_not():
    assert "EMPTY_OR_SCANNED_PAGE" in page_quality_warnings("   ", 0.0, "PDF_DIGITAL")
    assert page_quality_warnings("ĐẠI DIỆN BÊN A", 0.0, "PDF_DIGITAL") == []
    assert "EMPTY_OR_SCANNED_PAGE" in page_quality_warnings("Ảnh quét " * 4, 0.9, "PDF_DIGITAL")
    assert page_quality_warnings("   ", 0.0, "PLAIN_TEXT") == []


def test_garbled_text_threshold():
    clean = "a" * 1000
    assert page_quality_warnings(clean + "(cid:123)", 0.0, "PDF_DIGITAL") == []
    assert "GARBLED_TEXT_ENCODING" in page_quality_warnings(clean + "(cid:1)" * 3, 0.0, "PDF_DIGITAL")
    assert "GARBLED_TEXT_ENCODING" in page_quality_warnings("ab\ufffd" * 10, 0.0, "PLAIN_TEXT")


def test_page_warnings_are_independent_of_masking():
    pages = [pdf_page(1, [("", None)])]

    with_mask = clean_layout(pages, "PDF_DIGITAL")
    without_mask = clean_layout(pages, "PDF_DIGITAL", enable_layout_cleaning=False)

    assert with_mask["page_warnings"] == without_mask["page_warnings"]
    assert "EMPTY_OR_SCANNED_PAGE" in with_mask["page_warnings"][0]["warnings"]


# ── PDF thật ─────────────────────────────────────────────

def test_extract_pdf_lines_matches_extract_text_and_has_geometry():
    pages = extract_pdf_lines(BytesIO((FIXTURES / "contract_old.pdf").read_bytes()), 100)

    assert len(pages) == 2
    for page in pages:
        lines = page["text"].split("\n")
        assert len(page["line_boxes"]) == len(lines)
        assert all(box is not None for line, box in zip(lines, page["line_boxes"]) if line.strip())
        assert page["height"] > 0


def test_fixture_footer_is_masked_and_header_is_known_limitation():
    pages = extract_pdf_lines(BytesIO((FIXTURES / "contract_old.pdf").read_bytes()), 100)

    layout = clean_layout(pages, "PDF_DIGITAL")

    footers = [t for t in masked_texts(layout) if "Trang" in t]
    assert len(footers) == 2
    # Header 3 dòng không có số trang, tài liệu 2 trang: không mask (giới hạn đã chấp nhận).
    assert not any(t.startswith("CONTRACTDIFF") for t in masked_texts(layout))
    assert_ledger_valid(layout, pages)


# ── hồi quy từ code review ───────────────────────────────

def test_currency_code_before_number_is_protected():
    assert masked_texts(clean_layout(three_pages(header="Giá thuê: USD 100"), "PDF_DIGITAL")) == []
    pages = [pdf_page(n, [("Nội dung.", 300.0), (f"Giá thuê: USD 100 Trang {n} / 2", 770.0)]) for n in (1, 2)]
    assert masked_texts(clean_layout(pages, "PDF_DIGITAL")) == []


def test_signature_line_in_edge_zone_is_protected():
    assert masked_texts(clean_layout(three_pages(header="ĐẠI DIỆN BÊN A"), "PDF_DIGITAL")) == []


def test_bare_trailing_numbers_are_not_page_numbers():
    pages = [pdf_page(n, [(f"Xác nhận đợt {n}", 10.0), ("Nội dung.", 300.0)]) for n in (1, 2, 3)]

    assert masked_texts(clean_layout(pages, "PDF_DIGITAL")) == []


def test_geometry_is_dropped_when_line_counts_disagree():
    page = pdf_page(1, [("Nội dung A\rNội dung B", 300.0), ("Trang 1", 785.0)])

    layout = clean_layout([page], "PDF_DIGITAL")

    assert all(line["bbox"] is None for line in layout["lines"])
    assert masked_texts(layout) == []
    assert "LINE_GEOMETRY_UNAVAILABLE" in layout["page_warnings"][0]["warnings"]


def test_quality_warnings_use_normalized_text():
    nfd = unicodedata.normalize("NFD", "ĐẠI DIỆN BÊN A")
    assert page_quality_warnings(nfd, 0.0, "PDF_DIGITAL") == []
    assert page_quality_warnings("đồng\u00adý " * 10, 0.0, "PLAIN_TEXT") == []


def test_edge_zone_ratio_is_a_parameter():
    pages = three_pages(header_top=60.0)

    assert masked_texts(clean_layout(pages, "PDF_DIGITAL", edge_zone_ratio=0.05)) == []
    assert len(masked_texts(clean_layout(pages, "PDF_DIGITAL", edge_zone_ratio=0.10))) == 3


def test_page_line_boxes_uses_the_same_line_breaks():
    lines = [{"text": "A", "x0": 1, "top": 2, "x1": 3, "bottom": 4}, {"text": "B", "x0": 1, "top": 5, "x1": 3, "bottom": 6}]

    assert page_line_boxes("A\rB", lines) is not None
    assert page_line_boxes("A\nB\nC", lines) is None


# ── hồi quy từ code review vòng 2 ────────────────────────

def test_every_signature_heading_is_protected():
    assert masked_texts(clean_layout(three_pages(header="ĐẠI DIỆN CÁC BÊN"), "PDF_DIGITAL")) == []
    pages = [pdf_page(n, [("Nội dung.", 300.0), (f"ĐẠI DIỆN CÁC BÊN Trang {n} / 2", 770.0)]) for n in (1, 2)]
    assert masked_texts(clean_layout(pages, "PDF_DIGITAL")) == []


def test_dates_are_not_page_numbers():
    pages = [pdf_page(n, [(f"Hiệu lực từ 15/0{n}/2026", 10.0), ("Nội dung.", 300.0)]) for n in (1, 2, 3)]

    assert masked_texts(clean_layout(pages, "PDF_DIGITAL")) == []


def test_currency_code_glued_to_number_is_protected():
    assert masked_texts(clean_layout(three_pages(header="Giá thuê USD100"), "PDF_DIGITAL")) == []


# ── hồi quy từ review vòng 3 ─────────────────────────────

@pytest.mark.parametrize("date", ["15/ 0{n}/2026", "15 / 0{n} / 2026"])
def test_dates_with_spaces_are_protected(date):
    pages = [pdf_page(n, [("Nội dung.", 300.0), ("Hiệu lực từ " + date.format(n=n), 780.0)]) for n in (1, 2, 3)]

    assert masked_texts(clean_layout(pages, "PDF_DIGITAL")) == []


@pytest.mark.parametrize("header", ["Giá thuê 100USD", "Phí 500.000VNĐ"])
def test_currency_code_after_number_is_protected(header):
    assert masked_texts(clean_layout(three_pages(header=header), "PDF_DIGITAL")) == []


def test_any_signature_heading_page_is_not_scanned():
    assert page_quality_warnings("ĐẠI DIỆN CÁC BÊN", 0.0, "PDF_DIGITAL") == []
