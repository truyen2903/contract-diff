import pytest
from pathlib import Path

from app.parsers.contract_parser import parse_contract_pages
from experiments.evaluate_structure import (char_iou, evaluate, match_units,
                                            precision_recall_f1, split_allowed)


WEIGHTS = {("p", 1): 10, ("p", 2): 10, ("p", 3): 10, ("p", 4): 70}


def unit(*lines):
    return frozenset(("p", line) for line in lines)


def test_char_iou_weights_lines_by_length():
    assert char_iou(unit(1, 2), unit(1, 2), WEIGHTS) == 1.0
    assert char_iou(unit(1, 4), unit(4), WEIGHTS) == pytest.approx(70 / 80)
    assert char_iou(unit(1), unit(2), WEIGHTS) == 0.0


def test_match_is_one_to_one_and_prefers_higher_overlap():
    predicted = [unit(1, 2, 3, 4)]
    gold = [unit(4), unit(1, 2, 3, 4)]

    assert match_units(predicted, gold, WEIGHTS, 0.9) == [(0, 1)]


def test_exact_match_requires_identical_line_sets():
    assert match_units([unit(1, 4)], [unit(4)], WEIGHTS, 1.0) == []
    assert match_units([unit(1, 4)], [unit(4)], WEIGHTS, 0.8) == [(0, 0)]


def test_precision_recall_f1_with_empty_sets():
    assert precision_recall_f1(0, 0, 0) == (1.0, 1.0, 1.0)
    assert precision_recall_f1(0, 2, 0) == (0.0, 1.0, 0.0)
    assert precision_recall_f1(3, 4, 6) == pytest.approx((0.75, 0.5, 0.6))


def test_layout_lines_leaking_into_nodes_are_penalized():
    text = (Path(__file__).parent / "fixtures/publication/multipage.txt").read_text(encoding="utf-8")
    pages = [{"page_number": index, "text": page}
             for index, page in enumerate(text.split("\f"), 1)]
    gold = {
        "nodes": [
            {"gold_id": "article-1", "node_type": "ARTICLE", "parent": None,
             "lines": [{"page": 1, "start": 1, "end": 2}]},
            {"gold_id": "article-2", "node_type": "ARTICLE", "parent": None,
             "lines": [{"page": 2, "start": 1, "end": 2}]},
        ],
        "layout_lines": [{"page": page, "line_index": line}
                         for page in (1, 2) for line in (0, 3)],
    }

    scores = evaluate(parse_contract_pages(pages, "PLAIN_TEXT"), gold, pages)

    # Text input retains page furniture, so the exact metric must penalize it.
    assert scores["ARTICLE_exact"]["tp"] < scores["ARTICLE_exact"]["gold"]
    assert scores["ARTICLE_exact"]["gold"] == 2
    assert scores["layout_lines"] == 4


def test_holdout_is_not_allowed_without_an_explicit_flag():
    assert split_allowed("dev_train")
    assert split_allowed("dev_val")
    assert not split_allowed("test_holdout")
    assert split_allowed("test_holdout", include_holdout=True)
