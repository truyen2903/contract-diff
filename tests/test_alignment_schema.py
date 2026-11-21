import copy

import pytest
from pydantic import ValidationError

from app.engines.compact_alignment import build_result, source_locations
from app.parsers.contract_parser import parse_contract_pages, parse_contract_text
from app.schemas.alignment import StructuredComparisonResponse


def compact(old, new, **kwargs):
    return build_result(parse_contract_text(old), parse_contract_text(new), **kwargs)


def test_compact_renumber_and_sources():
    result = compact("ĐIỀU I: Tên\n1.1 Một khoản giống nguyên văn.",
                     "Điều 2: Tên\n2.1 Một khoản giống nguyên văn.")
    StructuredComparisonResponse.model_validate(result)
    assert {row["category"] for row in result["alignments"]} == {"RENUMBERED"}
    assert all(row["word_changes"] == [] for row in result["alignments"])
    for doc in ("old_document", "new_document"):
        assert result[doc]["side"] == doc.split("_")[0]
        assert "lines" not in result[doc] and "normalized_text" not in result[doc]
        for node in result[doc]["nodes"]:
            assert "subtree_text" not in node
            assert node["own_text"][node["body_offset"]:].startswith(("Tên", "Một"))


def test_word_change_clean_map_across_gap_pages_and_nonexact_raw():
    pages = [{"page_number": 1, "text": "Giữ nguyên a\u0301x\r\n\r\nhai"},
             {"page_number": 2, "text": "ba\nkết thúc."}]
    old = parse_contract_pages(pages, "PLAIN_TEXT")
    new = parse_contract_text("Giữ nguyên khác\nkết thúc.")
    result = build_result(old, new)
    StructuredComparisonResponse.model_validate(result)
    node = result["old_document"]["nodes"][0]
    assert node["raw_offsets_exact"] is False
    change, = result["alignments"][0]["word_changes"]
    span = change["old_span"]
    assert node["own_text"][span["start"]:span["end"]] == "áx\nhai\nba"
    locations = source_locations(node["source_segments"], span)
    assert [old["normalized_text"][s["clean_start"]:s["clean_end"]] for s in locations] == ["áx", "hai", "ba"]
    assert [s["page"] for s in locations] == [1, 1, 2]
    assert locations[0]["raw_exact"] is False
    assert pages[0]["text"][locations[0]["raw_start"]:locations[0]["raw_end"]] == "Giữ nguyên a\u0301x"
    assert locations[2]["raw_exact"] is True


def test_reordered_combining_marks_equal_length():
    result = compact("x\u0315\u0300", "x")
    assert result["old_document"]["nodes"][0]["raw_offsets_exact"] is False


@pytest.mark.parametrize("corrupt", ["side", "missing", "duplicate", "coverage", "parent", "candidate",
                                     "offset", "source", "category", "spurious", "convention", "span"])
def test_reject_bad_reference_or_invariant(corrupt):
    result = compact("Điều 1: Phạm vi\n1. Các bên thống nhất mua hàng.",
                     "Điều 1: Phạm vi\n1. Các bên thống nhất bán hàng.")
    records = result["alignments"]
    node = result["old_document"]["nodes"][1]
    if corrupt == "side":
        result["new_document"]["side"] = "old"
    elif corrupt == "missing":
        records[0]["new_node_id"] = "missing"
    elif corrupt == "duplicate":
        records.append(copy.deepcopy(records[0]))
    elif corrupt == "coverage":
        records.pop()
    elif corrupt == "parent":
        records[1]["parent_status"] = "CHANGED"
    elif corrupt == "candidate":
        records[1]["alternative_candidates"] = [{"candidate_side": "new", "node_id": "missing", "score": .5}]
    elif corrupt == "offset":
        node["body_offset"] = 10000
    elif corrupt == "source":
        node["source_segments"][0]["clean_end"] += 2
    elif corrupt == "category":
        records[0]["category"] = "ADDED"
    elif corrupt == "spurious":
        node["subtree_text"] = "duplicated"
    elif corrupt == "convention":
        result["config"]["move_convention"] = "future"
    else:
        records[1]["word_changes"][0]["new_span"]["end"] = 98765
    with pytest.raises(ValidationError):
        StructuredComparisonResponse.model_validate(result)


@pytest.mark.parametrize("old,new", [("Mặt hàng là màu xanh.", "Mặt hàng là màu vàng."), ("abc", ""), ("", "abc")])
def test_source_words_cannot_disappear_without_an_opcode(old, new):
    result = compact(old, new)
    row = result["alignments"][0]
    if old and new:
        row["category"] = "UNCHANGED"
    row["word_changes"] = []
    with pytest.raises(ValidationError):
        StructuredComparisonResponse.model_validate(result)


def test_reject_overlapping_source_ownership():
    result = compact("Điều 1: A\n1. Ghi nhớ", "Điều 1: A\n1. Ghi nhớ")
    part = result["old_document"]["nodes"][1]["source_segments"][0]
    for coord in ("clean", "raw"):
        part[coord + "_end"] -= part[coord + "_start"]
        part[coord + "_start"] = 0
    with pytest.raises(ValidationError):
        StructuredComparisonResponse.model_validate(result)


def test_review_inherited_and_source_coordinates_verified():
    result = compact("plain text", "more plain text")
    result["old_document"]["needs_review"] = False
    with pytest.raises(ValidationError):
        StructuredComparisonResponse.model_validate(result)

    old = parse_contract_text("Alpha\n\nBravo")
    old["nodes"][0]["own_text"] = "Delta\nFalse"  # same length as the owned lines
    with pytest.raises(ValueError, match="source"):
        build_result(old, parse_contract_text("text"))


def test_sided_stage_and_scores_must_agree():
    result = compact("Điều 1: Dịch vụ vận chuyển bằng đường bộ.", "")
    result["alignments"][0]["similarity_score"] = 1.
    with pytest.raises(ValidationError):
        StructuredComparisonResponse.model_validate(result)


def test_second_unreported_edit_is_rejected():
    result = compact("Thời gian giao thứ hai, trả phí vào thứ ba.",
                     "Thời gian giao thứ tư, trả phí vào thứ sáu.")
    changes = result["alignments"][0]["word_changes"]
    assert len(changes) == 2
    changes.pop()
    with pytest.raises(ValidationError):
        StructuredComparisonResponse.model_validate(result)


def test_edit_gaps_must_match_at_each_operation():
    result = compact("Từ đầu xanh giữa đoạn rồi kết.", "Từ đầu giữa đoạn vàng rồi kết.")
    row = result["alignments"][0]
    delete, insert = row["word_changes"]
    row["word_changes"] = [{"type": "replace", "old_span": delete["old_span"], "new_span": insert["new_span"]}]
    with pytest.raises(ValidationError):
        StructuredComparisonResponse.model_validate(result)


def test_generator_checks_unique_and_complete_line_ownership():
    tree = parse_contract_text("Điều 1: A\n1. Nội dung giống.\n1. Nội dung giống.")
    tree["nodes"][2]["source_spans"] = tree["nodes"][1]["source_spans"]
    with pytest.raises(ValueError, match="ownership"):
        build_result(tree, tree)
    tree = parse_contract_text("Điều 1: A\nĐiều 2: B")
    tree["nodes"].pop()
    with pytest.raises(ValueError, match="ownership"):
        build_result(tree, tree)


def test_masked_page_number_remains_a_gap_in_source_map():
    pages = [{"page_number": 1, "text": "Nội dung đầu\nTrang 1\nNội dung cuối", "height": 100,
              "line_boxes": [{"top": 20, "bottom": 30, "x0": 0, "x1": 10},
                             {"top": 0, "bottom": 4, "x0": 0, "x1": 10},
                             {"top": 40, "bottom": 45, "x0": 0, "x1": 10}]}]
    doc = parse_contract_pages(pages, "PDF_DIGITAL")
    assert doc["lines"][1]["masked"]
    result = build_result(doc, doc)
    node = result["old_document"]["nodes"][0]
    parts = source_locations(node["source_segments"], {"start": 0, "end": len(node["own_text"])})
    assert [pages[0]["text"][p["raw_start"]:p["raw_end"]] for p in parts] == ["Nội dung đầu", "Nội dung cuối"]
