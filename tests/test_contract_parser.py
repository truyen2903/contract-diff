import json
import random
import unicodedata
from pathlib import Path

import pytest

from app.core.worker import run_in_worker
from app.parsers.contract_parser import parse_contract_pages, parse_contract_text
from app.schemas.structure import DocumentStructure, StructuralNode


DATA = Path(__file__).resolve().parent / "fixtures" / "publication"
HEIGHT = 800.0


def normalize_source(raw):
    return unicodedata.normalize("NFC", raw.replace("\r\n", "\n").replace("\r", "\n"))


def span_lines(result, span):
    return [
        line for line in result["lines"]
        if line["page_number"] == span["page_number"]
        and span["clean_char_start"] <= line["clean_start"] and line["clean_end"] <= span["clean_char_end"]
    ]


def assert_structure_invariants(result, pages):
    """Sáu bất biến của Phase B1 (round3-consensus.md §3)."""
    lines, nodes = result["lines"], result["nodes"]
    normalized = result["normalized_text"]
    page_texts = {page["page_number"]: page["text"] for page in pages}
    key = lambda line: (line["page_number"], line["line_index"])

    # 1–2. Bảo toàn và sở hữu duy nhất trên tập vị trí dòng.
    content = {key(line) for line in lines if not line["masked"] and line["text"].strip()}
    owned = []
    owner_lines = {}
    for node in nodes:
        node_lines = []
        for span in node["source_spans"]:
            in_span = span_lines(result, span)
            assert in_span, span
            node_lines += in_span
        owner_lines[node["node_id"]] = node_lines
        owned += [key(line) for line in node_lines]
    assert len(owned) == len(set(owned)), "một dòng thuộc nhiều node"
    assert set(owned) == content, "mất dòng hoặc sở hữu dòng mask/trắng"

    # 3–4. Cha–con hợp lệ, không chu trình.
    index = {node["node_id"]: i for i, node in enumerate(nodes)}
    assert len(index) == len(nodes)
    for i, node in enumerate(nodes):
        parent = node["parent_id"]
        if node["node_type"] == "CLAUSE":
            assert parent is not None and nodes[index[parent]]["node_type"] == "ARTICLE"
        else:
            assert parent is None
        if parent is not None:
            assert index[parent] < i
        assert node["children"] == [n["node_id"] for n in nodes if n["parent_id"] == node["node_id"]]

    # 5. Source mapping.
    for node in nodes:
        slices = []
        for span in node["source_spans"]:
            raw = page_texts[span["page_number"]]
            assert 0 <= span["raw_char_start"] < span["raw_char_end"] <= len(raw)
            piece = normalized[span["clean_char_start"]:span["clean_char_end"]]
            assert normalize_source(raw[span["raw_char_start"]:span["raw_char_end"]]) == piece
            slices.append(piece)
            if result["source_type"] == "PLAIN_TEXT":
                assert span["bbox"] is None
        assert node["own_text"] == "\n".join(slices)
        subtree = [node] + [n for n in nodes if n["parent_id"] == node["node_id"]]
        assert node["subtree_text"] == "\n".join(n["own_text"] for n in subtree)
        subtree_pages = {line["page_number"] for n in subtree for line in owner_lines[n["node_id"]]}
        assert node["page_numbers"] == sorted(subtree_pages)
        if result["source_type"] == "PLAIN_TEXT":
            assert node["bboxes"] == []


def parse(text):
    result = parse_contract_text(text)
    assert_structure_invariants(result, [{"page_number": 1, "text": text}])
    DocumentStructure.model_validate(result)
    return result


def summary(result):
    return [(n["node_type"], n["number_label"]) for n in result["nodes"]]


def node_by_label(result, label):
    return next(n for n in result["nodes"] if n["number_label"] == label)


# ── ca bắt buộc ──────────────────────────────────────────

def test_single_article():
    result = parse("Điều 1. Phạm vi\nBên A thuê Bên B.")

    assert summary(result) == [("ARTICLE", "Điều 1")]
    assert result["nodes"][0]["title"] == "Phạm vi"
    assert result["nodes"][0]["own_text"] == "Điều 1. Phạm vi\nBên A thuê Bên B."


def test_articles_and_clauses():
    result = parse(
        "Điều 1. Phạm vi\n1.1. Bên B cung cấp dịch vụ.\n1.2 Dịch vụ gồm bảo trì.\n"
        "Điều 2. Thanh toán\n1. Bên A trả tiền.\n2) Bên B xuất hóa đơn.\nKhoản 3. Phí phạt."
    )

    assert summary(result) == [
        ("ARTICLE", "Điều 1"), ("CLAUSE", "1.1"), ("CLAUSE", "1.2"),
        ("ARTICLE", "Điều 2"), ("CLAUSE", "1"), ("CLAUSE", "2"), ("CLAUSE", "Khoản 3"),
    ]
    article = result["nodes"][0]
    assert article["own_text"] == "Điều 1. Phạm vi"
    assert article["children"] == [result["nodes"][1]["node_id"], result["nodes"][2]["node_id"]]
    assert article["subtree_text"] == "Điều 1. Phạm vi\n1.1. Bên B cung cấp dịch vụ.\n1.2 Dịch vụ gồm bảo trì."


def test_article_without_clauses_keeps_its_body():
    result = parse("Điều 1. Thời hạn\nHợp đồng có hiệu lực đến ngày 31/12/2026.\nĐiều 2. Khác\nKhông.")

    assert summary(result) == [("ARTICLE", "Điều 1"), ("ARTICLE", "Điều 2")]
    assert result["nodes"][0]["own_text"].endswith("31/12/2026.")


def test_non_consecutive_clause_numbers_are_kept_with_warning():
    result = parse("Điều 1. A\nKhoản 1. Một.\nKhoản 2. Hai.\nKhoản 4. Bốn.")

    assert summary(result)[1:] == [("CLAUSE", "Khoản 1"), ("CLAUSE", "Khoản 2"), ("CLAUSE", "Khoản 4")]
    assert "NON_CONSECUTIVE_CLAUSE_NUMBER" in result["nodes"][3]["warnings"]


def test_duplicate_clause_numbers_are_separate_nodes():
    result = parse("Điều 1. A\n1. Một.\n2. Hai.\n2. Hai nữa.")

    assert summary(result)[1:] == [("CLAUSE", "1"), ("CLAUSE", "2"), ("CLAUSE", "2")]
    assert result["nodes"][2]["node_id"] != result["nodes"][3]["node_id"]
    assert "DUPLICATE_CLAUSE_NUMBER" in result["nodes"][3]["warnings"]


def test_article_title_on_next_line():
    result = parse("ĐIỀU III:\nGIÁ THUÊ VÀ THANH TOÁN\nKhoản 1. Giá thuê là 8.000.000 đồng.")

    article = result["nodes"][0]
    assert article["number_label"] == "ĐIỀU III"
    assert article["title"] == "GIÁ THUÊ VÀ THANH TOÁN"
    assert article["own_text"] == "ĐIỀU III:\nGIÁ THUÊ VÀ THANH TOÁN"


def test_body_line_after_bare_article_is_not_a_title():
    result = parse("Điều 1\nBên A thanh toán theo thỏa thuận\ntrong vòng ba ngày.")

    article = result["nodes"][0]
    assert article["title"] is None
    assert "ARTICLE_TITLE_UNRESOLVED" in article["warnings"]
    assert article["own_text"].endswith("trong vòng ba ngày.")


def test_text_before_first_article_is_preamble():
    result = parse("CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nHỢP ĐỒNG\n\nĐiều 1. A\nNội dung.")

    assert summary(result) == [("PREAMBLE", None), ("ARTICLE", "Điều 1")]
    assert result["nodes"][0]["own_text"] == "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nHỢP ĐỒNG"


def test_signature_block():
    result = parse("Điều 1. A\n1. Nội dung.\n\nĐẠI DIỆN BÊN A\n(Ký, ghi rõ họ tên)\nĐẠI DIỆN BÊN B")

    assert summary(result)[-1] == ("SIGNATURE", None)
    assert result["nodes"][-1]["own_text"] == "ĐẠI DIỆN BÊN A\n(Ký, ghi rõ họ tên)\nĐẠI DIỆN BÊN B"


def test_article_after_signature_reopens_structure():
    result = parse("Điều 1. A\nNội dung.\nĐẠI DIỆN BÊN A\nPHỤ LỤC 01\nĐiều 1. Danh mục\nKhoản 1. Máy chiếu.")

    assert summary(result) == [
        ("ARTICLE", "Điều 1"), ("SIGNATURE", None), ("PARAGRAPH", None), ("ARTICLE", "Điều 1"), ("CLAUSE", "Khoản 1"),
    ]
    assert result["nodes"][3]["section_context"] == "PHỤ LỤC 01"


def test_nfd_and_nfc_give_the_same_structure():
    text = "Điều 1. Quyền và nghĩa vụ\n1. Bên A phải thanh toán.\nĐIỀU 2. HIỆU LỰC"

    nfc = parse(text)
    nfd = parse(unicodedata.normalize("NFD", text))

    assert summary(nfd) == summary(nfc)
    assert [n["own_text"] for n in nfd["nodes"]] == [n["own_text"] for n in nfc["nodes"]]


def test_clause_spanning_pages():
    pages = [{"page_number": 1, "text": "Điều 1. A\n1. Bên A giao hàng"},
             {"page_number": 2, "text": "trong vòng 20 ngày.\n2. Bên B nhận hàng."}]

    result = parse_contract_pages(pages, "PLAIN_TEXT")
    assert_structure_invariants(result, pages)

    clause = result["nodes"][1]
    assert clause["own_text"] == "1. Bên A giao hàng\ntrong vòng 20 ngày."
    assert [span["page_number"] for span in clause["source_spans"]] == [1, 2]
    assert result["nodes"][0]["page_numbers"] == [1, 2]


def test_repeated_header_and_footer_are_not_owned():
    rows = lambda n: [("CÔNG TY DEMO - HỢP ĐỒNG", 10.0), (f"Điều {n}. Nội dung {n}", 300.0),
                      (f"Bên A thực hiện nghĩa vụ {n}.", 320.0), (f"Trang {n} / 3", 780.0)]
    pages = []
    for n in (1, 2, 3):
        texts = rows(n)
        pages.append({"page_number": n, "text": "\n".join(t for t, _ in texts), "width": 600.0, "height": HEIGHT,
                      "line_boxes": [{"x0": 50.0, "top": top, "x1": 500.0, "bottom": top + 10.0} for _, top in texts],
                      "image_coverage": 0.0, "warnings": []})

    result = parse_contract_pages(pages, "PDF_DIGITAL")
    assert_structure_invariants(result, pages)

    assert summary(result) == [("ARTICLE", "Điều 1"), ("ARTICLE", "Điều 2"), ("ARTICLE", "Điều 3")]
    assert all("CÔNG TY DEMO" not in n["own_text"] and "Trang" not in n["own_text"] for n in result["nodes"])
    assert all(len(n["bboxes"]) == 1 for n in result["nodes"])


@pytest.mark.parametrize("line", [
    "100.000.000 đồng cho mỗi lần vi phạm.",
    "15. ngày sau khi bàn giao.",
    "1.25 tỷ đồng được thanh toán.",
    "1.000 USD thanh toán đợt 1.",
    "2026. là năm đầu tiên.",
    "01.01.2026 Hai bên ký kết.",
    "2. USD 100 cho mỗi lần.",
    "3. 000 đồng.",
])
def test_money_and_dates_are_not_clauses(line):
    result = parse(f"Điều 1. Phạt\n1. Bên nhận phải bồi thường.\n{line}")

    assert summary(result) == [("ARTICLE", "Điều 1"), ("CLAUSE", "1")]
    assert result["nodes"][1]["own_text"].endswith(line)


def test_capitalized_value_words_can_still_start_clauses():
    result = parse("Điều 5. Thanh toán\n1. Ngày thanh toán là ngày 05.\n2. Đồng tiền thanh toán là VNĐ.")

    assert summary(result) == [("ARTICLE", "Điều 5"), ("CLAUSE", "1"), ("CLAUSE", "2")]


def test_unknown_structure_becomes_one_paragraph():
    result = parse("BIÊN BẢN\n\nI. MỤC ĐÍCH\nHợp tác.\n30. ngày sau bàn giao.")

    assert summary(result) == [("PARAGRAPH", None)]
    assert "NO_STRUCTURE_DETECTED" in result["warnings"]
    assert result["needs_review"] is True


def test_empty_input_has_no_nodes():
    assert parse("")["nodes"] == []
    assert parse("\n  \n")["nodes"] == []


# ── nhận diện đầu mục (round3-consensus C8, M3–M5) ───────

@pytest.mark.parametrize("line, label", [
    ("Điều 5a. Thanh toán", "Điều 5a"),
    ("ĐIỀU V: TRÁCH NHIỆM", "ĐIỀU V"),
    ("Điều XL: Khác", "Điều XL"),
    ("Điều 1000. Cuối", "Điều 1000"),
    ("ĐIỀU 1 ĐỐI TƯỢNG HỢP ĐỒNG", "ĐIỀU 1"),
    ("Điều 7 — Hiệu lực", "Điều 7"),
    ("Điều 8.", "Điều 8"),
])
def test_article_headings(line, label):
    assert summary(parse(f"Mở đầu.\n{line}\nNội dung.")) == [("PREAMBLE", None), ("ARTICLE", label)]


@pytest.mark.parametrize("line", [
    "Điều 2 của Hợp đồng này hoặc theo yêu cầu.",
    "điều 3 của Hợp đồng này",
    "Điều 5 này có hiệu lực kể từ ngày ký.",
    "Điều 5.1 quy định rõ.",
    "Điều 100.000.000 đồng",
    "Điều IVX. Sai",
    "Điều 1 Đối tượng hợp đồng",
])
def test_article_like_lines_inside_clause_are_kept(line):
    result = parse(f"Điều 1. A\n1. Bên B không tiết lộ dữ liệu, trừ trường hợp tại\n{line}")

    assert summary(result) == [("ARTICLE", "Điều 1"), ("CLAUSE", "1")]


@pytest.mark.parametrize("line", ["Khoản 1 của Điều này quy định.", "Khoản 1.2 quy định rõ.", "phần 1 của dự án"])
def test_reference_lines_are_not_headings(line):
    assert summary(parse(f"Điều 1. A\nKhoản 1. Một.\n{line}")) == [("ARTICLE", "Điều 1"), ("CLAUSE", "Khoản 1")]


def test_points_stay_inside_clause():
    result = parse("Điều 1. A\n1.2. Dịch vụ gồm:\na) Sửa lỗi;\nb) Cập nhật;\n1.2.1 Chi tiết.\n1.3. Khác.")

    assert summary(result) == [("ARTICLE", "Điều 1"), ("CLAUSE", "1.2"), ("CLAUSE", "1.3")]
    assert node_by_label(result, "1.2")["own_text"].count("\n") == 3


def test_clause_needs_a_boundary_before_it():
    result = parse("Điều 1. A\n1. Bên A giữ lại theo quy định tại Khoản\n2. Bên B có quyền.")

    assert summary(result) == [("ARTICLE", "Điều 1"), ("CLAUSE", "1")]
    assert "AMBIGUOUS_CLAUSE_CANDIDATE" in result["nodes"][1]["warnings"]


def test_short_list_without_punctuation_is_split():
    result = parse("Điều 1. A\n1. Bàn giao sản phẩm đúng hạn\n2. Bảo hành 12 tháng")

    assert summary(result) == [("ARTICLE", "Điều 1"), ("CLAUSE", "1"), ("CLAUSE", "2")]


def test_clauses_with_stale_article_prefix():
    result = parse("Điều 5. Thanh toán\n4.1. Đợt 1 trả 50%.\n4.2. Đợt 2 trả 50%.")

    assert summary(result) == [("ARTICLE", "Điều 5"), ("CLAUSE", "4.1"), ("CLAUSE", "4.2")]
    assert "NUMBERING_PARENT_MISMATCH" in result["nodes"][1]["warnings"]


def test_single_stale_prefix_line_stays_text():
    result = parse("Điều 5. Thanh toán\n5.1. Đợt 1 trả 50%.\n3.15 Mức phạt theo phụ lục.")

    assert summary(result) == [("ARTICLE", "Điều 5"), ("CLAUSE", "5.1")]
    assert "NUMBERING_PARENT_MISMATCH" in result["nodes"][1]["warnings"]


def test_section_heading_is_a_root_paragraph():
    result = parse("Mở đầu.\nCHƯƠNG I. QUY ĐỊNH CHUNG\nĐiều 1. A\n1. Một.\nCHƯƠNG II QUY ĐỊNH KHÁC\nĐiều 2. B")

    assert summary(result) == [
        ("PREAMBLE", None), ("PARAGRAPH", None), ("ARTICLE", "Điều 1"), ("CLAUSE", "1"),
        ("PARAGRAPH", None), ("ARTICLE", "Điều 2"),
    ]
    assert result["nodes"][2]["section_context"] == "CHƯƠNG I. QUY ĐỊNH CHUNG"
    assert result["nodes"][5]["section_context"] == "CHƯƠNG II QUY ĐỊNH KHÁC"


# ── tất định và bất biến trên input ngẫu nhiên ───────────

FRAGMENTS = [
    "Điều 1. Phạm vi", "ĐIỀU II:", "GIÁ THUÊ", "Điều 5a. Thanh toán", "1. Bên A trả tiền.", "1.1 Nội dung",
    "2) Bên B nhận.", "a) Điểm con;", "Khoản 3. Phạt.", "100.000.000 đồng.", "15. ngày", "CHƯƠNG I. CHUNG",
    "ĐẠI DIỆN BÊN A", "", "   ", "Điều 2 của Hợp đồng này", "Trang 1/2", "\ufffd(cid:12)", "4.1. Lệch số.",
    unicodedata.normalize("NFD", "Điều 9. Hiệu lực"), "Bên B phải bàn giao\r", "1.2.3 Chi tiết",
]


def test_invariants_hold_on_seeded_random_documents():
    rng = random.Random(20261120)
    for _ in range(250):
        pages = [
            {"page_number": n, "text": "\n".join(rng.choice(FRAGMENTS) for _ in range(rng.randint(0, 12)))}
            for n in range(1, rng.randint(1, 3) + 1)
        ]
        assert_structure_invariants(parse_contract_pages(pages, "PLAIN_TEXT"), pages)


def test_parsing_is_deterministic_across_processes():
    text = (DATA / "service.txt").read_text(encoding="utf-8")

    local = parse_contract_text(text)
    remote = run_in_worker(parse_contract_text, text)

    assert json.dumps(remote, sort_keys=True, ensure_ascii=False) == json.dumps(local, sort_keys=True, ensure_ascii=False)


@pytest.mark.parametrize("template", ["service", "equipment", "appendix", "signature", "unstructured"])
def test_invariants_hold_on_dataset(template):
    text = (DATA / f"{template}.txt").read_text(encoding="utf-8")
    pages = [{"page_number": n, "text": page} for n, page in enumerate(text.split("\f"), start=1)]

    assert_structure_invariants(parse_contract_pages(pages, "PLAIN_TEXT"), pages)


# ── hồi quy từ code review (phase-b1/code-review-*.md) ───

def test_huge_numbers_do_not_crash():
    digits = "9" * 4500
    result = parse(f"Điều 1. A\n1. Nội dung.\nĐiều {digits}. B\n{digits}. Bên A.\nKhoản {digits}. C")

    assert summary(result) == [("ARTICLE", "Điều 1"), ("CLAUSE", "1")]


@pytest.mark.parametrize("line", ["Điều 2) của Hợp đồng này.", "Khoản 2) của Điều này."])
def test_reference_in_parentheses_is_not_a_heading(line):
    assert summary(parse(f"Điều 1. A\n1. Thực hiện theo (xem\n{line}")) == [("ARTICLE", "Điều 1"), ("CLAUSE", "1")]


def test_no_break_space_and_bom_in_headings():
    result = parse("\ufeffĐiều\u00a01. Phạm vi\nNội dung.\nĐiều\u00a02. Khác\n1.\u00a0Bên A trả tiền.")

    assert summary(result) == [("ARTICLE", "Điều 1"), ("ARTICLE", "Điều 2"), ("CLAUSE", "1")]


def test_section_after_signature_is_flagged():
    result = parse("Điều 1. A\nĐẠI DIỆN BÊN A\nPHỤ LỤC 1\nĐiều 2. B")

    assert summary(result)[-1] == ("ARTICLE", "Điều 2")
    assert any("STRUCTURE_AFTER_SIGNATURE" in node["warnings"] for node in result["nodes"])
    assert result["needs_review"] is True


def test_loose_article_after_signature_section_is_not_accepted():
    result = parse("Điều 1. A\nĐẠI DIỆN BÊN A\nPHỤ LỤC 1\nĐIỀU 2 PHẠM VI")

    assert [node_type for node_type, _ in summary(result)].count("ARTICLE") == 1


def test_stale_prefix_needs_two_candidates_passing_the_boundary():
    result = parse("Điều 5. A\n4.1. Một.\nNội dung đang dẫn chiếu tại Khoản\n4.2. Hai.")

    assert summary(result) == [("ARTICLE", "Điều 5")]


def test_stale_prefix_does_not_count_lines_in_signature():
    result = parse("Điều 5. A\n4.1. Một.\nĐẠI DIỆN BÊN A\n4.2. Hai.")

    assert summary(result) == [("ARTICLE", "Điều 5"), ("SIGNATURE", None)]


def test_caps_article_heading_with_trailing_period():
    assert summary(parse("Mở đầu.\nĐIỀU 1 PHẠM VI.\nNội dung.")) == [("PREAMBLE", None), ("ARTICLE", "ĐIỀU 1")]


def test_caps_title_line_with_trailing_period():
    assert parse("Điều 1\nPHẠM VI.\nNội dung.")["nodes"][0]["title"] == "PHẠM VI."


def test_point_line_is_not_a_title():
    article = parse("Điều 1\n1.1.1 CHI TIẾT")["nodes"][0]

    assert article["title"] is None
    assert "ARTICLE_TITLE_UNRESOLVED" in article["warnings"]


def test_bare_article_at_end_of_document_is_flagged():
    assert "ARTICLE_TITLE_UNRESOLVED" in parse("Điều 1")["nodes"][0]["warnings"]


def pdf_pages(rows_by_page):
    pages = []
    for page_number, rows in enumerate(rows_by_page, start=1):
        pages.append({
            "page_number": page_number,
            "text": "\n".join(text for text, _, _ in rows),
            "width": 600.0,
            "height": HEIGHT,
            "line_boxes": [{"x0": x0, "top": top, "x1": 500.0, "bottom": top + 10.0} for _, top, x0 in rows],
            "image_coverage": 0.0,
            "warnings": [],
        })
    return pages


def test_clause_indent_mismatch_is_flagged():
    pages = pdf_pages([[("Điều 1. A", 100.0, 50.0), ("1. Bên A trả.", 120.0, 50.0), ("2. Bên B nhận.", 140.0, 70.0)]])

    result = parse_contract_pages(pages, "PDF_DIGITAL")

    assert summary(result) == [("ARTICLE", "Điều 1"), ("CLAUSE", "1"), ("CLAUSE", "2")]
    assert "CLAUSE_INDENT_MISMATCH" in result["nodes"][2]["warnings"]
    assert "CLAUSE_INDENT_MISMATCH" not in result["nodes"][1]["warnings"]


def test_document_with_only_masked_lines_needs_review():
    pages = pdf_pages([[("CÔNG TY DEMO - HỢP ĐỒNG MẪU", 10.0, 50.0)]] * 3)

    result = parse_contract_pages(pages, "PDF_DIGITAL")

    assert result["nodes"] == []
    assert "ALL_CONTENT_MASKED" in result["warnings"]
    assert result["needs_review"] is True


def test_article_carries_quality_warnings_of_its_clauses():
    pages = [{"page_number": 1, "text": "Điều 1. A\n1. Bên A trả."},
             {"page_number": 2, "text": "2. Bên B nhận \ufffd\ufffd\ufffd."}]

    result = parse_contract_pages(pages, "PLAIN_TEXT")

    assert "GARBLED_TEXT_ENCODING" in result["nodes"][0]["warnings"]
    assert "GARBLED_TEXT_ENCODING" not in result["nodes"][1]["warnings"]


def test_result_has_exactly_the_schema_fields():
    result = parse("Điều 1. A\n1. Bên A trả.")

    assert set(result) == set(DocumentStructure.model_fields)
    for node in result["nodes"]:
        assert set(node) == set(StructuralNode.model_fields)


def test_invariants_hold_on_seeded_random_pdf_documents():
    rng = random.Random(20261121)
    for _ in range(150):
        rows_by_page = []
        for _ in range(rng.randint(1, 4)):
            rows = []
            for _ in range(rng.randint(0, 10)):
                text = rng.choice(FRAGMENTS).replace("\r", "")
                rows.append((text, rng.choice([10.0, 300.0, 400.0, 785.0]), rng.choice([50.0, 70.0])))
            rows_by_page.append(rows)
        pages = pdf_pages(rows_by_page)
        result = parse_contract_pages(pages, "PDF_DIGITAL")
        assert_structure_invariants(result, pages)
        DocumentStructure.model_validate(result)


# ── hồi quy từ code review vòng 2 ────────────────────────

@pytest.mark.parametrize("text", [
    "ĐIỀU 5:\nTHANH TOÁN\n4.1. Đợt 1 trả 50%.\n4.2. Đợt 2 trả 50%.",
    "Điều 5. A\nKhoản 1. Bàn giao\n4.1. Một\n4.2. Hai",
])
def test_stale_prefix_count_follows_titles_and_explicit_clauses(text):
    labels = [label for node_type, label in summary(parse(text)) if node_type == "CLAUSE"]

    assert labels[-2:] == ["4.1", "4.2"]


@pytest.mark.parametrize("line, label", [
    ("Điều XXXVIII. Hiệu lực", "Điều XXXVIII"),
    ("Điều MCMXCIV. PHẠM VI", "Điều MCMXCIV"),
])
def test_long_roman_numerals_are_still_headings(line, label):
    assert summary(parse(f"Mở đầu.\n{line}\nNội dung.")) == [("PREAMBLE", None), ("ARTICLE", label)]


def test_indent_is_checked_on_every_page_of_an_article():
    pages = pdf_pages([
        [("Điều 1. A", 100.0, 50.0), ("1. Bên A trả.", 120.0, 50.0)],
        [("2. Bên B nhận.", 120.0, 50.0), ("3. Bên C xác nhận.", 140.0, 80.0)],
    ])

    result = parse_contract_pages(pages, "PDF_DIGITAL")

    assert summary(result) == [("ARTICLE", "Điều 1"), ("CLAUSE", "1"), ("CLAUSE", "2"), ("CLAUSE", "3")]
    assert "CLAUSE_INDENT_MISMATCH" in result["nodes"][3]["warnings"]
    assert "CLAUSE_INDENT_MISMATCH" not in result["nodes"][2]["warnings"]


def test_bom_only_line_does_not_break_title_or_boundary():
    result = parse("Điều 1.\nPHẠM VI\n\ufeff\n1. Bên A trả.")

    assert summary(result) == [("ARTICLE", "Điều 1"), ("CLAUSE", "1")]
    assert result["nodes"][0]["title"] == "PHẠM VI"


def test_bom_only_line_between_article_and_title_is_invisible():
    result = parse("ĐIỀU 5:\nBOM\nTHANH TOÁN\n4.1. Đợt 1 trả 50%.\n4.2. Đợt 2 trả 50%.".replace("BOM", chr(0xFEFF)))

    assert result["nodes"][0]["title"] == "THANH TOÁN"
    assert summary(result) == [("ARTICLE", "ĐIỀU 5"), ("CLAUSE", "4.1"), ("CLAUSE", "4.2")]
