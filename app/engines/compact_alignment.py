"""Compact own_text spans and their piecewise mapping to the B1 line ledger."""

from bisect import bisect_left, bisect_right
import re

from app.core import config
from app.engines.alignment_budget import AlignmentBudget, AlignmentBudgetError, AlignmentResultTooLargeError
from app.engines.clause_aligner import ALIGNMENT_CONFIG, align_documents
from app.engines.entity_delta import pair_entities
from app.engines.entity_extractor import extract_entities
from app.engines.legal_tokens import tokenize_legal_spans
from app.engines.review_priority import classify_pair
from app.engines.similarity import body_start
from app.engines.text_diff import diff_words, tokenize_with_spans


def source_segments(node, lines, starts, claimed):
    result = []
    own = 0
    for span in node["source_spans"]:
        first = bisect_left(starts, span["clean_char_start"])
        stop = bisect_left(starts, span["clean_char_end"])
        if (first == stop or lines[first]["clean_start"] != span["clean_char_start"]
                or lines[stop - 1]["clean_end"] != span["clean_char_end"]):
            raise ValueError("source span does not follow line boundaries")
        for i in range(first, stop):
            line = lines[i]
            end = own + len(line["text"])
            if (claimed[i] or node["own_text"][own:end] != line["text"] or line["page_number"] != span["page_number"]
                    or line["masked"] or not line["text"].strip()):
                raise ValueError("source line ownership mismatch")
            claimed[i] = 1
            segment = {"own_start": own, "own_end": end, "page": line["page_number"],
                       "clean_start": line["clean_start"], "clean_end": line["clean_end"],
                       "raw_start": line["raw_start"], "raw_end": line["raw_end"],
                       "raw_exact": line.get("raw_offsets_exact", False)}
            last = result[-1] if result else None
            if (last and last["page"] == segment["page"] and last["raw_exact"] and segment["raw_exact"]
                    and last["clean_end"] + 1 == segment["clean_start"]
                    and last["raw_end"] + 1 == segment["raw_start"]):
                for field in ("own_end", "clean_end", "raw_end"):
                    last[field] = segment[field]
            else:
                result.append(segment)
            own = end + 1
    if max(0, own - 1) != len(node["own_text"]):
        raise ValueError("source map does not cover own_text")
    return result


def source_locations(segments, span):
    if span is None:
        return []
    result = []
    first = bisect_right(segments, span["start"], key=lambda segment: segment["own_end"])
    for i in range(first, len(segments)):
        segment = segments[i]
        if segment["own_start"] >= span["end"]:
            break
        start = max(segment["own_start"], span["start"]) - segment["own_start"]
        end = min(segment["own_end"], span["end"]) - segment["own_start"]
        if start < end:
            exact = segment["raw_exact"]
            result.append({"page": segment["page"], "clean_start": segment["clean_start"] + start,
                           "clean_end": segment["clean_start"] + end, "raw_exact": exact,
                           "raw_start": segment["raw_start"] + start if exact else segment["raw_start"],
                           "raw_end": segment["raw_start"] + end if exact else segment["raw_end"]})
    return result


def compact_document(tree, side):
    lines = tree["lines"]
    starts = [line["clean_start"] for line in lines]
    claimed = bytearray(len(lines))
    nodes = []
    for node in tree["nodes"]:
        item = {k: node[k] for k in ("node_id", "node_type", "parent_id", "section_context",
                                      "number_label", "title", "own_text", "warnings")}
        item["body_offset"], _ = body_start(node["own_text"], node["number_label"])
        segments = source_segments(node, lines, starts, claimed)
        item["source_segments"] = segments
        item["raw_offsets_exact"] = all(s["raw_exact"] for s in segments)
        nodes.append(item)
    if any(not used and not line["masked"] and line["text"].strip() for used, line in zip(claimed, lines)):
        raise ValueError("incomplete source line ownership")
    return {"side": side, "nodes": nodes, "source_type": tree["source_type"], "page_count": tree["page_count"],
            "warnings": tree["warnings"], "page_warnings": tree["page_warnings"], "needs_review": tree["needs_review"]}


def add_local_changes(records, old, new, budget):
    total_opcodes = 0
    for row in records:
        changes = []
        row["word_changes"] = changes
        if row["category"] not in ("MODIFIED", "MOVED_AND_MODIFIED", "ADDED", "DELETED"):
            continue
        pair = (old.get(row["old_node_id"]), new.get(row["new_node_id"]))
        offsets = [n["body_offset"] if n else 0 for n in pair]
        bodies = [n["own_text"][offset:] if n else "" for n, offset in zip(pair, offsets)]
        product = len(tokenize_with_spans(bodies[0])) * len(tokenize_with_spans(bodies[1]))
        if product > config.MAX_DIFF_PAIR_WORK:
            raise AlignmentBudgetError(f"local diff: {product} > {config.MAX_DIFF_PAIR_WORK}")
        budget.charge("diff_total", product, "local diff")
        for change in diff_words(*bodies):
            total_opcodes += 1
            if total_opcodes > config.MAX_CHANGE_OPCODES:
                raise AlignmentResultTooLargeError("too many change opcodes")
            item = {"type": change["type"]}
            for side, offset in zip(("old_span", "new_span"), offsets):
                span = change[side]
                item[side] = {k: value + offset for k, value in span.items()} if span else None
            changes.append(item)


def add_semantic_entities(records, old, new, budget):
    """Run the bounded B3 stage after B2 local diff and before result aggregation."""
    renumbered_targets = {}
    for item in records:
        if item["category"] != "RENUMBERED" or not item.get("old_node_id") or not item.get("new_node_id"):
            continue
        before = old.get(item["old_node_id"])
        after = new.get(item["new_node_id"])
        if before and after and item["node_type"] == "ARTICLE" and before.get("number_label") and after.get("number_label"):
            renumbered_targets[before["number_label"].strip().upper()] = after["number_label"].strip().upper()
        if before and after and item["node_type"] == "CLAUSE" and before.get("number_label") and after.get("number_label"):
            before_article = old.get(before.get("parent_id"))
            after_article = new.get(after.get("parent_id"))
            if before_article and after_article and before_article.get("number_label") and after_article.get("number_label"):
                old_target = f"KHOẢN {before['number_label']} {before_article['number_label']}".upper()
                new_target = f"KHOẢN {after['number_label']} {after_article['number_label']}".upper()
                renumbered_targets[old_target] = new_target
    for row in records:
        row.setdefault("old_entities", [])
        row.setdefault("new_entities", [])
        row.setdefault("entity_deltas", [])
        row.setdefault("semantic_signals", [])
        row.setdefault("review_priority", "LOW")
        row.setdefault("review_reasons", [])
        old_node = old.get(row.get("old_node_id"))
        new_node = new.get(row.get("new_node_id"))
        old_parent = old.get(old_node.get("parent_id")) if old_node and old_node.get("parent_id") else None
        new_parent = new.get(new_node.get("parent_id")) if new_node and new_node.get("parent_id") else None
        if old_node:
            budget.charge("b3_token_ops", len(tokenize_legal_spans(old_node["own_text"])), "B3 tokenization")
            row["old_entities"] = extract_entities(old_node, old_parent)
        if new_node:
            budget.charge("b3_token_ops", len(tokenize_legal_spans(new_node["own_text"])), "B3 tokenization")
            row["new_entities"] = extract_entities(new_node, new_parent)
        budget.charge("b3_entities", len(row["old_entities"]) + len(row["new_entities"]), "B3 extraction")
        if row["category"] in ("UNCHANGED", "RENUMBERED"):
            deltas = []
        else:
            deltas = pair_entities(row["old_entities"], row["new_entities"], row["word_changes"],
                                    max_candidates=budget.max_b3_pair_candidates)
        budget.charge("b3_pair_candidates_total", len(row["old_entities"]) * len(row["new_entities"]), "B3 pairing")
        row["entity_deltas"] = deltas
        classification = classify_pair(row["category"], row["node_type"], row.get("parent_changed"),
                                       row["warnings"], deltas, row["old_entities"], row["new_entities"],
                                       parent_status=row.get("parent_status"))
        row.update(classification)
        cross_refs = [entity for entity in row["old_entities"] + row["new_entities"]
                      if entity.get("signal_type") == "CROSS_REF"]
        if any(entity.get("evidence_scope") == "UNRESOLVED" for entity in cross_refs):
            row["warnings"] = sorted(set(row["warnings"]) | {"UNRESOLVED_CROSS_REFERENCE"})
            row["review_reasons"] = sorted(set(row["review_reasons"]) | {"UNRESOLVED_CROSS_REFERENCE"})
            row["needs_review"] = True
            if row["review_priority"] == "LOW":
                row["review_priority"] = "HIGH"
        def target_article(entity):
            target = entity.get("cross_ref_target")
            if not target:
                return None
            match = re.search(r"\bĐIỀU\s+\d+(?:\.\d+)?", target.upper())
            return match.group(0) if match else None
        def target_was_renumbered(entity):
            target = entity.get("cross_ref_target")
            if not target:
                return False
            normalized = target.upper()
            if normalized in renumbered_targets:
                return True
            article = target_article(entity)
            return article in renumbered_targets
        if any(target_was_renumbered(entity) for entity in cross_refs):
            row["warnings"] = sorted(set(row["warnings"]) | {"INTERNAL_CROSS_REFERENCE_RISK"})
            row["review_reasons"] = sorted(set(row["review_reasons"]) | {"INTERNAL_CROSS_REFERENCE_RISK"})
            row["needs_review"] = True
            row["review_priority"] = "HIGH" if row["review_priority"] != "CRITICAL" else row["review_priority"]


def build_result(old, new, *, alignment_config=None, budget=None):
    cfg = {**ALIGNMENT_CONFIG, **(alignment_config or {})}
    budget = budget or AlignmentBudget()
    records = align_documents(old["nodes"], new["nodes"], cfg, budget)
    a, b = compact_document(old, "old"), compact_document(new, "new")
    old_nodes, new_nodes = {n["node_id"]: n for n in a["nodes"]}, {n["node_id"]: n for n in b["nodes"]}
    add_local_changes(records, old_nodes, new_nodes, budget)
    add_semantic_entities(records, old_nodes, new_nodes, budget)
    warnings = sorted({w for row in records for w in row["warnings"]} | set(a["warnings"]) | set(b["warnings"]))
    return {"old_document": a, "new_document": b, "alignments": records, "warnings": warnings,
            "needs_review": bool(warnings or a["needs_review"] or b["needs_review"]), "config": cfg,
            "b3_schema_version": "b3-v1", "entity_rules_version": "b3-rules-v1",
            "priority_rules_version": "b3-priority-v1"}
