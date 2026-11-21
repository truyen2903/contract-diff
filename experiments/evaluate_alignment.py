"""Run a controlled Oracle Tree / End-to-End comparison: python -m experiments.evaluate_alignment."""

import argparse
import json
from pathlib import Path

from app.engines.alignment_budget import AlignmentBudgetError, StructureTooLargeError
from app.engines.assignment import components, hungarian
from app.engines.clause_aligner import align_documents
from app.parsers.contract_parser import parse_contract_pages, parse_contract_text
from experiments.evaluate_structure import SCORED_TYPES, precision_recall_f1
from experiments.generate_pairs import engineering_example
from experiments.reference_labels import reference_moves


def metrics(predicted, expected):
    tp = len(predicted & expected)
    p, r, f = precision_recall_f1(tp, len(predicted), len(expected))
    return {"tp": tp, "fp": len(predicted) - tp, "fn": len(expected) - tp, "precision": p, "recall": r, "f1": f}


def false_alignment_rate(predicted_count, true_positive):
    return (predicted_count - true_positive) / predicted_count if predicted_count else 0.0


def metrics_by_type(rows, gold, old_types, projection=None):
    gold = set(gold)
    expected = {node_type: {edge for edge in gold if old_types.get(edge[0]) == node_type}
                for node_type in SCORED_TYPES}
    predicted = {node_type: set() for node_type in SCORED_TYPES}
    for row in rows:
        if row.get("node_type") not in predicted or None in (row.get("old_node_id"), row.get("new_node_id")):
            continue
        edge = row["old_node_id"], row["new_node_id"]
        if projection is not None:
            edge = projection[0].get(edge[0]), projection[1].get(edge[1])
        if None not in edge:
            predicted[row["node_type"]].add(edge)
    return {node_type: metrics(predicted[node_type], expected[node_type]) for node_type in SCORED_TYPES}


def rejected_case_rate(results):
    return sum(result.get("rejection") is not None for result in results) / len(results) if results else 0.0


def evaluate_edges(rows, gold, convention_moves, edit_moves, projection=None):
    gold, convention_moves, edit_moves = map(set, (gold, convention_moves, edit_moves))
    if not (convention_moves | edit_moves) <= gold:
        raise ValueError("gold moves must reference matched endpoints")
    predicted, moved = set(), set()
    for row in rows:
        edge = row["old_node_id"], row["new_node_id"]
        if row["node_type"] not in SCORED_TYPES or None in edge:
            continue
        if projection is not None:
            edge = tuple(mapping.get(node, ("unmapped", node)) for node, mapping in zip(edge, projection))
        predicted.add(edge)
        if row["category"] in ("MOVED", "MOVED_AND_MODIFIED"):
            moved.add(edge)
    return {"F1_align": metrics(predicted, gold), "F1_move_convention": metrics(moved, convention_moves),
            "F1_move_edit_op": metrics(moved, edit_moves)}


def evaluate_baseline_rows(rows, gold):
    if not any(row.get("node_type") in SCORED_TYPES for row in rows):
        return {"status": "N/A", "reason": "baseline endpoints are not ARTICLE/CLAUSE nodes"}
    return {"status": "MEASURED", **evaluate_edges(rows, gold, set(), set())}


def range_iou(left, right):
    # Source ranges are ordered, disjoint half-open intervals in the same normalized document.
    i = j = overlap = 0
    while i < len(left) and j < len(right):
        a, b = left[i]
        c, d = right[j]
        overlap += max(0, min(b, d) - max(a, c))
        if b <= d:
            i += 1
        else:
            j += 1
    union = sum(b - a for ranges in (left, right) for a, b in ranges) - overlap
    return overlap / union if union else 0.


def evaluation_gate(*, data_folder=None, locked_manifest_sha256=None, engineering_only=False,
                    split=None, allow_test_holdout=False):
    if split == "test_holdout" and not allow_test_holdout:
        raise ValueError("holdout evaluation requires --allow-test-holdout")
    if engineering_only:
        return {"engineering_only": True, "research_eligible": False, "dataset_gate": None}
    from experiments.check_alignment_data import check_data

    if data_folder is None:
        report = check_data(locked_manifest_sha256=locked_manifest_sha256)
    else:
        report = check_data(data_folder, locked_manifest_sha256=locked_manifest_sha256)
    if not report["eligible"]:
        raise ValueError("dataset gate failed: research evaluation requires an eligible locked manifest")
    return {"engineering_only": False, "research_eligible": True, "dataset_gate": report}


def project_nodes(predicted, gold):
    def units(nodes, key):
        owned = {n["node_id"]: key(n) for n in nodes}
        result = {}
        for n in nodes:
            if n["node_type"] in SCORED_TYPES:
                ranges = list(owned[n["node_id"]])
                for child in n["children"]:
                    ranges.extend(owned[child])
                result[n["node_id"]] = (n["node_type"], sorted(ranges))
        return result

    actual = units(predicted, lambda n: [(s["clean_char_start"], s["clean_char_end"]) for s in n["source_spans"]])
    targets = units(gold, lambda n: n["clean_ranges"])
    result = {}
    for node_type in sorted(SCORED_TYPES):
        actual_ids = sorted(node_id for node_id, (kind, _) in actual.items() if kind == node_type)
        target_ids = sorted(node_id for node_id, (kind, _) in targets.items() if kind == node_type)
        candidates = []
        for row, node_id in enumerate(actual_ids):
            for column, target_id in enumerate(target_ids):
                score = range_iou(actual[node_id][1], targets[target_id][1])
                if score >= .8:
                    candidates.append((row, column, score))
        for left, right in components([(row, column) for row, column, _ in candidates]):
            size = max(len(left), len(right))
            bonus = size * 1_000_000 + 1
            weights = [[0] * size for _ in range(size)]
            for row, column, score in candidates:
                if row in left and column in right:
                    weights[left.index(row)][right.index(column)] = bonus + round(score * 1_000_000)
            for row, column in hungarian(weights):
                if weights[row][column]:
                    result[actual_ids[left[row]]] = target_ids[right[column]]
    return result


def evaluate_case(case, mode, budget=None):
    gold_old, gold_new = case["old_nodes"], case["new_nodes"]
    types = {n["node_id"]: n["node_type"] for n in gold_old}
    gold = {(u, v) for u, v in case["edges"] if types[u] in SCORED_TYPES}
    convention = reference_moves(case)
    edits = {(u, v) for u, v in case["edit_moves"] if types[u] in SCORED_TYPES}
    projection = None
    if mode == "oracle":
        old, new = gold_old, gold_new
    elif mode == "end_to_end":
        trees = []
        for side in ("old", "new"):
            if side + "_pages" in case:
                trees.append(parse_contract_pages(case[side + "_pages"], case["source_type"]))
            else:
                trees.append(parse_contract_text(case[side + "_text"]))
        old, new = (tree["nodes"] for tree in trees)
        projection = project_nodes(old, gold_old), project_nodes(new, gold_new)
    else:
        raise ValueError("unknown evaluation mode")
    candidates = dict(gold)
    if projection is not None:
        reverse_old, reverse_new = ({v: k for k, v in mapping.items()} for mapping in projection)
        candidates = {reverse_old[u]: reverse_new[v] for u, v in gold if u in reverse_old and v in reverse_new}
    passed = {key: set() for key in ("structure", "budget", "threshold")}

    def observe(event, left, right, scores):
        right = set(right)
        for u in left:
            v = candidates.get(u)
            if v not in right:
                continue
            passed["structure"].add(u)
            if event == "anchor":
                passed["budget"].add(u)
                passed["threshold"].add(u)
            elif event == "scored":
                passed["budget"].add(u)
                score, eligible, threshold, _ = scores[u][v]
                if eligible and score >= threshold:
                    passed["threshold"].add(u)

    failure = None
    try:
        rows = align_documents(old, new, budget=budget, observe=observe)
    except (AlignmentBudgetError, StructureTooLargeError) as error:
        failure, rows = error.code, []
    recall = {key: len(survivors) / len(gold) if gold else 1. for key, survivors in passed.items()}
    return {**evaluate_edges(rows, gold, convention, edits, projection),
            "metrics_by_type": metrics_by_type(rows, gold, types, projection),
            "candidate_recall": recall, "rejection": failure}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, help="independently annotated pair JSON")
    parser.add_argument("--engineering-only", action="store_true")
    parser.add_argument("--data-folder", type=Path)
    parser.add_argument("--locked-manifest-sha256")
    parser.add_argument("--allow-test-holdout", action="store_true")
    args = parser.parse_args()
    case = json.loads(args.case.read_text(encoding="utf-8")) if args.case else engineering_example()
    gate = evaluation_gate(data_folder=args.data_folder, locked_manifest_sha256=args.locked_manifest_sha256,
                           engineering_only=args.engineering_only or args.case is None,
                           split=case.get("assigned_split"), allow_test_holdout=args.allow_test_holdout)
    print(json.dumps({"usage": case["usage"], **gate, **{mode: evaluate_case(case, mode)
                     for mode in ("oracle", "end_to_end")}}, indent=2))
