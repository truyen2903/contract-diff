import math
import json
from pathlib import Path
import unicodedata

import pytest

from app.engines.similarity import (body_start, combine_scores, content_key, fit_lexical,
                                    lexical_similarity, position_similarity, title_similarity,
                                    unique_anchors)


def test_keys_offsets_and_global_uniqueness():
    text = "\ufeff  ĐIỀU\u00a0 I : Trách  nhiệm\nBên A"
    offset, warning = body_start(text, "ĐIỀU I")
    assert (text[offset:], warning) == ("Trách  nhiệm\nBên A", None)
    assert body_start("1.23 Clause", "1.2") == (0, "LABEL_NOT_AT_START")
    assert content_key(text[offset:]) == "Trách nhiệm Bên A"
    assert content_key(" A ") != content_key("a")
    key = "Một nội dung đủ dài để làm neo"
    assert unique_anchors([key, key, "short"], [key, "short"]) == []
    assert unique_anchors([key, "short"], ["short", key]) == [(0, 1)]


def test_tfidf_against_hand_computed_smooth_idf():
    vectors = fit_lexical(["a b", "a"])
    rare = 1 + math.log(3 / 2)
    # word features a, b, (a b); short char_wb features are padded once.
    expected = .6 / math.sqrt(1 + 2 * rare**2) + .4 / math.sqrt(1 + rare**2)
    assert lexical_similarity(*vectors) == pytest.approx(expected, abs=1e-12)


def test_unicode_empty_symmetric_no_mutation():
    texts = ["", "  ", "ĐIỀU 1", unicodedata.normalize("NFD", "Điều 1"), "!", "x"]
    original = texts.copy()
    vectors = fit_lexical(texts)
    for left in vectors:
        assert lexical_similarity(left, left) == 1
        for right in vectors:
            score = lexical_similarity(left, right)
            assert 0 <= score <= 1
            assert score == lexical_similarity(right, left)
    assert lexical_similarity(vectors[2], vectors[3]) == 1
    assert texts == original


def test_adaptive_score_and_title():
    assert title_similarity("AB", "ac") == .25
    assert title_similarity("ĐIỀU", "điều") == 1
    assert title_similarity("a", None) is None
    assert title_similarity("a", None, "half") == .5
    assert title_similarity("a", None, "zero") == 0
    assert title_similarity(None, None, "zero") is None
    assert position_similarity(1, 3, 2, 5) == 1
    assert combine_scores(.45, None, .8) == pytest.approx((.65*.45 + .1*.8)/.75)
    assert combine_scores(.45, None, None) == .45
    assert combine_scores(1, 1, 1) == 1


def test_frozen_sklearn_scipy_oracles():
    from app.engines.assignment import solve_assignment
    fixture = json.loads((Path(__file__).parent / "fixtures/b2-oracles.json").read_text(encoding="utf-8"))
    vectors = fit_lexical(fixture["texts"])
    for i, vector in enumerate(vectors):
        assert [lexical_similarity(vector, other) for other in vectors] == pytest.approx(fixture["lexical"][i], abs=1e-12)
    for case in fixture["assignments"]:
        assert solve_assignment(case["matrix"]) == list(map(tuple, case["pairs"]))
