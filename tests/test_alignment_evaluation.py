import pytest

from experiments.baselines import (flat_alignment, flat_hungarian_alignment, greedy_alignment,
                                    monotonic_alignment, whole_text)
from experiments.evaluate_alignment import (evaluate_baseline_rows, evaluate_case, evaluate_edges,
                                             evaluation_gate, false_alignment_rate, project_nodes,
                                             metrics_by_type, rejected_case_rate)
from experiments.generate_pairs import engineering_example
from experiments.reference_labels import reference_moves


def test_wrong_move_edge_is_false_positive_and_two_standards_differ():
    gold = {("a", "c"), ("b", "d")}
    predicted = [{"old_node_id": a, "new_node_id": b, "node_type": "ARTICLE", "category": "MOVED"}
                 for a, b in [("a", "c"), ("b", "e")]]
    metrics = evaluate_edges(predicted, gold, {("a", "c")}, {("b", "d")})
    assert metrics["F1_move_convention"] == dict(tp=1, fp=1, fn=0, precision=.5, recall=1., f1=2/3)
    assert metrics["F1_move_edit_op"]["f1"] == 0
    assert evaluate_edges([], set(), set(), set())["F1_align"]["f1"] == 1
    assert evaluate_edges([], gold, set(), set())["F1_align"]["f1"] == 0
    assert false_alignment_rate(1, 0) == 1.0
    assert false_alignment_rate(0, 0) == 0.0


def test_controlled_pair_oracle_and_end_to_end():
    case = engineering_example()
    assert case["usage"] == "ENGINEERING_ONLY"
    for mode in ("oracle", "end_to_end"):
        metrics = evaluate_case(case, mode)
        assert metrics["F1_align"]["f1"] == metrics["F1_move_convention"]["f1"] == 1
        assert metrics["F1_move_edit_op"]["f1"] == 0
        assert metrics["candidate_recall"]["threshold"] == 1
    assert reference_moves(case) != set(map(tuple, case["edit_moves"]))


def test_baselines_segmentation():
    assert whole_text("a b", "a c")[0]["type"] == "replace"
    old, new = "a\nb\n\nc", "a\nb\n\nc"
    assert len(flat_alignment(old, new, "paragraph")) == 2
    assert len(flat_alignment(old, new, "line")) == 3
    with pytest.raises(ValueError):
        flat_alignment(old, new, "sentences")


def test_paragraph_baseline_normalizes_line_endings():
    assert len(flat_alignment("a\r\n\r\nb", "a\r\n\r\nb", "paragraph")) == 2
    assert len(flat_alignment("a\r\rb", "a\r\rb", "paragraph")) == 2


def test_node_baselines_have_explicit_matching_strategies():
    old = [{"own_text": "same"}, {"own_text": "old only"}]
    new = [{"own_text": "same"}, {"own_text": "new only"}]
    for baseline in (greedy_alignment, monotonic_alignment, flat_hungarian_alignment):
        assert [(left, right) for left, right, _ in baseline(old, new, threshold=.4)] == [(0, 0)]


def test_incompatible_flat_baseline_is_reported_as_na():
    rows = flat_alignment("same", "same", "line")
    report = evaluate_baseline_rows(rows, set())
    assert report == {"status": "N/A", "reason": "baseline endpoints are not ARTICLE/CLAUSE nodes"}


def test_alignment_metrics_are_reported_by_node_type_and_rejection_rate():
    rows = [{"old_node_id": "a", "new_node_id": "b", "node_type": "ARTICLE", "category": "UNCHANGED"},
            {"old_node_id": "c", "new_node_id": "d", "node_type": "CLAUSE", "category": "MODIFIED"}]
    assert metrics_by_type(rows, {("a", "b"), ("c", "x")}, {"a": "ARTICLE", "c": "CLAUSE"})["ARTICLE"]["f1"] == 1
    assert rejected_case_rate([{"rejection": None}, {"rejection": "BUDGET"}]) == .5


def test_end_to_end_unmapped_node_still_counts_as_false_positive():
    case = engineering_example()
    case["old_nodes"][0]["clean_ranges"] = [[100000, 100100]]
    result = evaluate_case(case, "end_to_end")
    assert result["F1_align"]["fp"] and result["F1_align"]["fn"]
    assert result["candidate_recall"]["structure"] < 1


def test_end_to_end_projection_maximizes_cardinality_before_iou(monkeypatch):
    scores = {(1, 11): .95, (1, 12): .90, (2, 11): .90, (2, 12): .70}
    monkeypatch.setattr("experiments.evaluate_alignment.range_iou",
                        lambda left, right: scores[(left[0][0], right[0][0])])
    predicted = [
        {"node_id": "p1", "node_type": "CLAUSE", "children": [],
         "source_spans": [{"clean_char_start": 1, "clean_char_end": 2}]},
        {"node_id": "p2", "node_type": "CLAUSE", "children": [],
         "source_spans": [{"clean_char_start": 2, "clean_char_end": 3}]},
    ]
    gold = [
        {"node_id": "g1", "node_type": "CLAUSE", "children": [], "clean_ranges": [[11, 12]]},
        {"node_id": "g2", "node_type": "CLAUSE", "children": [], "clean_ranges": [[12, 13]]},
    ]
    assert project_nodes(predicted, gold) == {"p1": "g2", "p2": "g1"}


def test_rejected_pair_stays_in_denominator():
    case = engineering_example()
    from app.engines.alignment_budget import AlignmentBudget
    result = evaluate_case(case, "oracle", budget=AlignmentBudget(max_pairs=0))
    assert result["rejection"] == "ALIGNMENT_BUDGET_EXCEEDED"
    assert result["F1_align"]["fn"] == len(case["edges"])
    assert result["candidate_recall"]["structure"] == 1


def test_annotation_preflight_reports_pending_development_families(tmp_path):
    import hashlib
    import json
    from experiments.check_alignment_data import check_data
    rows = []
    for i in range(6):
        key = f"synthetic-{i}"
        folder = tmp_path / "raw_templates" / key
        folder.mkdir(parents=True)
        text = key.encode()
        (folder / "source.txt").write_bytes(text)
        digest = hashlib.sha256(text).hexdigest()
        (folder / "gold_tree.json").write_text(json.dumps({"review_status": "PENDING_AUTHOR_REVIEW",
            "transcript": "source.txt", "transcript_sha256": digest}))
        rows.append({"template_id": key, "root_family_id": key, "assigned_split": "dev_train",
                     "gold_review_status": "PENDING_AUTHOR_REVIEW", "sha256_text": digest,
                     "license_confirmed_by_author": False})
    (tmp_path / "dataset_manifest.json").write_text(json.dumps(rows))
    report = check_data(tmp_path)
    assert report["eligible"] is False and report["families"] == 6
    assert report["missing_families"] == 24
    assert len(report["pending_gold"]) == len(report["pending_license"]) == 6
    assert report["hash_mismatches"] == []


def test_research_evaluation_requires_an_eligible_dataset_gate(tmp_path):
    (tmp_path / "dataset_manifest.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="dataset gate failed"):
        evaluation_gate(data_folder=tmp_path)
    assert evaluation_gate(data_folder=tmp_path, engineering_only=True)["engineering_only"] is True


def test_holdout_case_requires_explicit_evaluation_flag(tmp_path):
    (tmp_path / "dataset_manifest.json").write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="holdout evaluation requires"):
        evaluation_gate(data_folder=tmp_path, split="test_holdout", engineering_only=True)
    assert evaluation_gate(data_folder=tmp_path, split="test_holdout", allow_test_holdout=True,
                           engineering_only=True)["engineering_only"] is True
