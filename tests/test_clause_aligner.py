import copy
import random
from pathlib import Path

import pytest

from app.engines import clause_aligner as aligner
from app.engines.alignment_budget import AlignmentBudget, AlignmentBudgetError
from app.parsers.contract_parser import parse_contract_pages, parse_contract_text
from experiments.reference_labels import lis_oracle, reference_stable


def nodes(text):
    return parse_contract_text(text)["nodes"]


def align(old, new, **kwargs):
    return aligner.align_documents(nodes(old), nodes(new), **kwargs)


SOURCES = sorted((Path(__file__).resolve().parent / "fixtures/publication").glob("*.txt"))
assert len(SOURCES) >= 6


@pytest.mark.parametrize("source", SOURCES)
def test_identity_and_labels(source):
    pages = [{"page_number": i, "text": page} for i, page in
             enumerate(source.read_text(encoding="utf-8").split("\f"), 1)]
    tree = parse_contract_pages(pages, "PLAIN_TEXT")["nodes"]
    before = copy.deepcopy(tree)
    records = aligner.align_documents(tree, tree)
    assert tree == before
    assert len(records) == len(tree)
    assert all(row["category"] == "UNCHANGED" for row in records)
    assert all(row["old_node_id"] == row["new_node_id"] for row in records)
    assert all("LABEL_NOT_AT_START" not in row["warnings"] for row in records)


def test_weighted_lis_independent_of_dp():
    rng = random.Random(1441)
    for m, n in [(2, 3), (3, 5)] + [(rng.randint(1, 12), rng.randint(1, 12)) for _ in range(150)]:
        k = rng.randint(0, min(m, n))
        edges = list(zip(sorted(rng.sample(range(m), k)), rng.sample(range(n), k),
                         rng.choices([1, 2, 5, 9], k=k)))
        assert aligner.weighted_lis(edges, m, n) == lis_oracle(edges, m, n)
    assert aligner.weighted_lis([(0, 1, 2), (1, 0, 2), (2, 2, 2)], 3, 3) == {(0, 1), (2, 2)}
    edges = [(i, (i+2) % 6, 2 if i < 4 else 10) for i in range(6)]
    assert aligner.weighted_lis(edges, 6, 6) == {(4, 0), (5, 1)}
    assert aligner.weighted_lis([(0, 2, 1), (1, 0, 1)], 2, 3) == {(1, 0)}
    assert aligner.weighted_lis([(0, 3, 1), (2, 1, 1)], 3, 5) == {(2, 1)}


def test_large_reference_stable_preserves_both_reading_orders():
    edges = [(0, 0, 1), (2, 1, 10), (1, 2, 10)]
    edges.extend((index, index, 1) for index in range(3, 13))
    result = reference_stable(edges, 13, 13)
    assert all(left < next_left and right < next_right
               for (left, right), (next_left, next_right) in zip(sorted(result), sorted(result)[1:]))


def test_large_reference_stable_rejects_duplicate_source_edges():
    edges = [(0, 0, 3), (0, 1, 4)]
    edges.extend((index, index, 1) for index in range(1, 12))
    result = reference_stable(edges, 12, 12)
    assert len([edge for edge in result if edge[0] == 0]) <= 1


def test_real_move_repeat_renumber_and_blocks():
    old = "ĐIỀU I: Thanh toán\n1. Một điều khoản bảo mật đủ dài.\nĐiều 2: Vận chuyển"
    new = "Điều 1: Thanh toán\nĐiều 2: Vận chuyển\n2. Một điều khoản bảo mật đủ dài."
    rows = align(old, new)
    moved = next(row for row in rows if row["node_type"] == "CLAUSE")
    assert (moved["category"], moved["parent_status"]) == ("MOVED", "CHANGED")
    assert "CROSS_ARTICLE_CLAUSE_MOVE" in moved["warnings"]
    assert rows[0]["category"] == "RENUMBERED"
    assert "CLAUSE_STRUCTURE_MISMATCH" in rows[0]["warnings"]
    rows = align("Văn bản cũ có một đoạn.", "Văn bản mới có một đoạn.")
    assert [(r["category"], r["alignment_stage"]) for r in rows] == [("MODIFIED", "STAGE1_BLOCK")]
    text = "Điều 1: Bảo mật\n1. Điều khoản giống nhau và đủ dài.\n2. Điều khoản giống nhau và đủ dài."
    repeated = [r for r in align(text, text) if r["node_type"] == "CLAUSE"]
    assert len(repeated) == 2
    assert all("AMBIGUOUS_CLAUSE_ALIGNMENT" in r["warnings"] for r in repeated)
    assert all(r["alignment_stage"] != "EXACT_ANCHOR" for r in repeated)


def test_q5_reopens_weak_local_pairs(monkeypatch):
    old = "Điều 1: Alpha\n1. LeftAA.\nĐiều 2: Omega\n1. LeftZZ."
    new = "Điều 1: Alpha\n1. RightAA.\nĐiều 2: Omega\n1. RightZZ."
    original = aligner.lexical_similarity
    def controlled(left, right):
        if left[0].startswith("left") and right[0].startswith("right"):
            return .55 if left[0][-3:] == right[0][-3:] else .95
        return original(left, right)
    monkeypatch.setattr(aligner, "lexical_similarity", controlled)
    rows = [r for r in align(old, new) if r["node_type"] == "CLAUSE"]
    assert len(rows) == 2
    assert all(r["category"] == "MOVED_AND_MODIFIED" and r["similarity_score"] == .95 for r in rows)
    with pytest.raises(AlignmentBudgetError, match="STAGE2"):
        align(old, new, budget=AlignmentBudget(max_pairs=6))


def test_5a_5b_and_orphan_fail_closed(monkeypatch):
    old = "Điều 1: Red\n1. Hai bên thống nhất thực hiện theo quy định của pháp luật Việt Nam."
    new = "Điều 2: Blue\n1. Các bên cam kết thực hiện theo quy định của pháp luật hiện hành."
    monkeypatch.setattr(aligner, "lexical_similarity",
                        lambda a, b: .5562 if a[0].startswith("hai bên") else 0)
    rows = align(old, new)
    assert {r["category"] for r in rows} == {"ADDED", "DELETED"}
    monkeypatch.setattr(aligner, "lexical_similarity",
                        lambda a, b: .85 if a[0].startswith("hai bên") else 0)
    row = next(r for r in align(old, new) if r["node_type"] == "CLAUSE")
    assert (row["parent_status"], row["category"]) == ("UNKNOWN", "MODIFIED")
    assert "PARENT_ALIGNMENT_UNKNOWN" in row["warnings"]
    with pytest.raises(AlignmentBudgetError, match="STAGE2"):
        align(old, new, budget=AlignmentBudget(max_pairs=1))


def test_preflight_before_scoring(monkeypatch):
    def bomb(*args):
        pytest.fail("scoring before budget check")
    monkeypatch.setattr(aligner, "lexical_similarity", bomb)
    example = nodes("Điều 1: Alpha")[0]
    old = [dict(example, node_id=str(i)) for i in range(1000)]
    with pytest.raises(AlignmentBudgetError, match="1000000"):
        aligner.align_documents(old, old)


def test_appendix_and_one_sided_nodes():
    old = "Điều 1: Dịch vụ\nPHỤ LỤC I: Bổ sung\nĐiều 1: Bảng giá"
    rows = align(old, "Điều 1: Dịch vụ")
    assert [r["category"] for r in rows] == ["UNCHANGED", "DELETED", "DELETED"]
    assert rows[-1]["new_node_id"] is None
    assert align("", "") == []


def test_orphan_tie_uses_complete_reading_order(monkeypatch):
    def group(names):
        return {s: {"key": (s * 21 if s in "abc" else s), "title": None} for s in names}
    level = aligner.MatchingLevel(group("abcz"), group("xabyc"), aligner.ALIGNMENT_CONFIG, AlignmentBudget())
    monkeypatch.setattr(level, "score", lambda *args: (.75, .75))
    level.recover()
    assert level.matches["z"][0] == "y"


def test_one_sided_residual_competes_with_anchor():
    old = "Điều 1: fish\n1. Các bên mua hàng chịu tiền phí.\nĐiều 2: sunflower\n1. Các bên mua hàng chịu tiền phí mới."
    new = "Điều 3: giao nhận\n1. Các bên mua hàng chịu tiền phí."
    row = next(r for r in align(old, new) if r["category"] == "DELETED" and r["node_type"] == "CLAUSE")
    assert row["alternative_candidates"][0]["candidate_side"] == "new"


def test_article_anchor_respects_body_boundaries():
    rows = align("Điều 1: Nội dung\n1. ABC DEF GHI JKL MNOP rõ ràng.",
                 "Điều 1: Nội dung ABC DEF\n1. GHI JKL MNOP rõ ràng.")
    assert rows[0]["category"] == "MODIFIED"
    assert rows[0]["alignment_stage"] != "EXACT_ANCHOR"


def test_heading_only_renumber_needs_review():
    assert align("Điều 1", "Điều 99")[0]["needs_review"]


def test_engine_rejects_ambiguous_or_non_string_node_ids():
    tree = nodes("Điều 1: A")
    for invalid in ([dict(tree[0], node_id=123)], tree * 2):
        with pytest.raises(ValueError):
            aligner.align_documents(invalid, tree)


def test_orphan_competes_with_strong_local_for_confidence(monkeypatch):
    def node(key):
        return {"key": key, "title": None}
    level = aligner.MatchingLevel({"x": node("x"), "y": node("y")}, {"v": node("v")},
                                  aligner.ALIGNMENT_CONFIG, AlignmentBudget())
    monkeypatch.setattr(level, "score", lambda u, *args: (.9, .9) if u == "x" else (.97, .97))
    level.assign(["x"], ["v"], aligner.LOCAL)
    level.recover()
    assert level.alternatives("y", None) == [{"candidate_side": "new", "node_id": "v", "score": .97}]


def test_feature_fit_guard(monkeypatch):
    monkeypatch.setattr(aligner, "fit_lexical", lambda *args: pytest.fail("vectorized over budget"))
    with pytest.raises(AlignmentBudgetError, match="vector"):
        align("Điều 1: Alpha", "Điều 2: Beta", budget=AlignmentBudget(max_score_work=1))


def test_unique_reorder_and_inverse_against_reference_categories():
    from experiments.reference_labels import category_oracle
    rng = random.Random(763)
    for _ in range(50):
        keys = ["Clause text " + str(i) + " extra" * (2**i) for i in range(5)]
        shuffled = rng.sample(keys, len(keys))
        def render(order):
            return "\n".join(f"Điều {i}: {s}" for i, s in enumerate(order, 1))
        old, new = render(keys), render(shuffled)
        rows = align(old, new)
        reverse = {(r["new_node_id"], r["old_node_id"]): r["category"] for r in align(new, old)}
        edges = [(i, shuffled.index(k), 2 * len(k.split())) for i, k in enumerate(keys)]
        stable = lis_oracle(edges, 5, 5)
        for row, (i, j, _) in zip(rows, edges):
            expected = category_oracle({"body": keys[i], "label": i}, {"body": shuffled[j], "label": j},
                                       None, (i, j) in stable, "ARTICLE")
            assert row["category"] == expected == reverse[row["old_node_id"], row["new_node_id"]]


def test_orphan_component_overflow_and_local_fallback(monkeypatch):
    def group(keys):
        return {k: {"key": k, "title": None} for k in keys}
    level = aligner.MatchingLevel(group("ab"), group("xy"), aligner.ALIGNMENT_CONFIG,
                                 AlignmentBudget(max_dimension=1))
    monkeypatch.setattr(level, "score", lambda *args: (.8, .8))
    with pytest.raises(AlignmentBudgetError, match="STAGE2_ORPHAN_CLAUSE: component"):
        level.recover()
    level = aligner.MatchingLevel(group("a"), group("x"), aligner.ALIGNMENT_CONFIG, AlignmentBudget())
    monkeypatch.setattr(level, "score", lambda *args: (.51, .49))
    level.assign(["a"], ["x"], aligner.LOCAL)
    level.recover()
    assert "a" not in level.matches


@pytest.mark.parametrize("score", [.55, .59])
def test_weak_local_edge_is_not_resurrected_below_orphan_threshold(monkeypatch, score):
    def group(keys):
        return {key: {"key": key, "title": None} for key in keys}

    level = aligner.MatchingLevel(group("u"), group("v"), aligner.ALIGNMENT_CONFIG, AlignmentBudget())
    monkeypatch.setattr(level, "score", lambda *args: (score, score))
    level.assign(["u"], ["v"], aligner.LOCAL)
    level.recover()
    assert level.matches == {}
