"""Read-only family, split and annotation preflight. A lock digest is supplied by the study owner."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from experiments.evaluate_structure import ROOT


EXPECTED_SPLITS = {"dev_train": 8, "dev_val": 7, "test_holdout": 15}
ALLOWED_NODE_TYPES = {"PREAMBLE", "ARTICLE", "CLAUSE", "PARAGRAPH", "SIGNATURE", "TABLE"}
REQUIRED_MANIFEST_FIELDS = {
    "template_id", "root_family_id", "assigned_split", "sha256_text", "gold_review_status",
    "license_confirmed_by_author",
}


def _gold_schema_errors(gold, pages):
    errors = []
    nodes = gold.get("nodes")
    if not isinstance(nodes, list):
        return ["nodes must be a list"]
    ids = [node.get("gold_id") if isinstance(node, dict) else None for node in nodes]
    for node_id, count in Counter(ids).items():
        if count > 1:
            errors.append(f"duplicate gold_id: {node_id}")
    by_id = {node_id: node for node_id, node in zip(ids, nodes) if isinstance(node_id, str)}
    line_counts = {page_number: len(page.split("\n")) for page_number, page in enumerate(pages, 1)}
    owned = set()
    for node in nodes:
        if not isinstance(node, dict):
            errors.append("node must be an object")
            continue
        node_id = node.get("gold_id")
        node_type = node.get("node_type")
        if not isinstance(node_id, str) or not node_id:
            errors.append("gold_id must be a non-empty string")
        if node_type not in ALLOWED_NODE_TYPES:
            errors.append(f"{node_id}: invalid node_type")
        parent = node.get("parent")
        if parent is not None and parent not in by_id:
            errors.append(f"{node_id}: missing parent")
        if node_type == "CLAUSE" and (parent is None or by_id.get(parent, {}).get("node_type") != "ARTICLE"):
            errors.append(f"{node_id}: clause parent must be ARTICLE")
        if node_type != "CLAUSE" and parent is not None:
            errors.append(f"{node_id}: only CLAUSE may have a parent")
        if node_type in ("ARTICLE", "CLAUSE") and not node.get("number_label"):
            errors.append(f"{node_id}: missing number_label")
        spans = node.get("lines")
        if not isinstance(spans, list) or not spans:
            errors.append(f"{node_id}: missing lines")
            continue
        for span in spans:
            page, start, end = (span.get(key) for key in ("page", "start", "end"))
            if (not isinstance(page, int) or not isinstance(start, int) or not isinstance(end, int)
                    or page not in line_counts or start < 0 or end < start or end >= line_counts[page]):
                errors.append(f"{node_id}: invalid line span")
                continue
            for line_index in range(start, end + 1):
                key = (page, line_index)
                if key in owned:
                    errors.append(f"overlapping node line: {page}:{line_index}")
                owned.add(key)
    for span in gold.get("layout_lines", []):
        page, line_index = span.get("page"), span.get("line_index")
        if page not in line_counts or not isinstance(line_index, int) or line_index < 0 or line_index >= line_counts[page]:
            errors.append("invalid layout line")
    return sorted(set(errors))


def check_data(folder=ROOT / "data", locked_manifest_sha256=None):
    raw = (folder / "dataset_manifest.json").read_bytes()
    rows = json.loads(raw)
    splits = defaultdict(set)
    pending_gold, pending_license, mismatches = [], [], []
    duplicate_templates, duplicate_families = [], []
    duplicate_hashes, gold_schema_errors = [], {}
    gold_hash_mismatches, missing_gold_hashes = [], []
    metadata_errors, missing_fields = {}, {}
    source_inventory = []
    pending_scientific_evidence = []
    if not isinstance(rows, list):
        raise ValueError("dataset_manifest.json must contain a list")
    template_ids = [row.get("template_id") for row in rows if isinstance(row, dict)]
    family_ids = [row.get("root_family_id") for row in rows if isinstance(row, dict)]
    hashes = [row.get("sha256_text") for row in rows if isinstance(row, dict)]
    duplicate_templates = sorted(key for key, count in Counter(template_ids).items() if key and count > 1)
    duplicate_families = sorted(key for key, count in Counter(family_ids).items() if key and count > 1)
    duplicate_hashes = sorted(key for key, count in Counter(hashes).items() if key and count > 1)
    template_root = folder / "raw_templates"
    folder_ids = {path.name for path in template_root.iterdir() if path.is_dir()} if template_root.exists() else set()
    manifest_ids = {key for key in template_ids if key}
    unlisted_templates = sorted(folder_ids - manifest_ids)
    missing_template_folders = sorted(manifest_ids - folder_ids)
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = row.get("template_id")
        missing = sorted(REQUIRED_MANIFEST_FIELDS - set(row))
        if missing:
            missing_fields[str(key)] = missing
            continue
        splits[row["root_family_id"]].add(row["assigned_split"])
        source = folder / "raw_templates" / key
        try:
            gold = json.loads((source / "gold_tree.json").read_text(encoding="utf-8"))
            source_path = source / gold["transcript"]
            pages = source_path.read_text(encoding="utf-8").split("\f")
            digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        except (FileNotFoundError, KeyError, json.JSONDecodeError, UnicodeDecodeError) as error:
            metadata_errors[key] = [f"source read failed: {error.__class__.__name__}"]
            continue
        if digest != row["sha256_text"] or digest != gold.get("transcript_sha256"):
            mismatches.append(key)
        gold_digest = hashlib.sha256((source / "gold_tree.json").read_bytes()).hexdigest()
        if row.get("gold_tree_sha256") is None:
            missing_gold_hashes.append(key)
        elif row["gold_tree_sha256"] != gold_digest:
            gold_hash_mismatches.append(key)
        errors = _gold_schema_errors(gold, pages)
        if errors:
            gold_schema_errors[key] = errors
        if row["gold_review_status"] != "APPROVED" or gold.get("review_status") != "APPROVED":
            pending_gold.append(key)
        if row["license_confirmed_by_author"] is not True:
            pending_license.append(key)
        source_kind = "synthetic" if key.startswith(("SYN_", "FIX_")) else row.get("source_kind", "unclassified")
        evidence_fields = ("provenance_evidence", "license_evidence", "adjudication_evidence")
        if (source_kind != "sourced_contract" or row.get("independence_status") != "VERIFIED"
                or row.get("independent_annotation") is not True
                or any(not isinstance(row.get(field), str) or not row[field].strip()
                       for field in evidence_fields)):
            pending_scientific_evidence.append(key)
        source_inventory.append({
            "template_id": key,
            "root_family_id": row["root_family_id"],
            "assigned_split": row["assigned_split"],
            "source_kind": source_kind,
            "provenance": row.get("source_origin", "UNSPECIFIED"),
            "license_status": "AUTHOR_CONFIRMED" if row["license_confirmed_by_author"] else "LICENSE_UNVERIFIED",
            "gold_status": row["gold_review_status"],
            "independent_annotation": row.get("independent_annotation") is True,
        })
    overlap = sorted(family for family, values in splits.items() if len(values) != 1)
    counts = Counter(split for values in splits.values() for split in values)
    digest = hashlib.sha256(raw).hexdigest()
    locked = locked_manifest_sha256 == digest
    split_errors = {key: {"expected": expected, "actual": counts.get(key, 0)}
                    for key, expected in EXPECTED_SPLITS.items() if counts.get(key, 0) != expected}
    complete = counts == EXPECTED_SPLITS and len(rows) == sum(EXPECTED_SPLITS.values())
    invalid = (overlap or pending_gold or pending_license or mismatches or duplicate_templates or duplicate_families
               or duplicate_hashes or gold_schema_errors or gold_hash_mismatches or missing_gold_hashes
               or metadata_errors or missing_fields or split_errors or unlisted_templates or missing_template_folders
               or pending_scientific_evidence)
    return {"eligible": bool(complete and locked and not invalid),
            "families": len(splits), "missing_families": max(0, 30 - len(splits)), "split_counts": dict(counts),
            "pending_gold": pending_gold, "pending_license": pending_license, "unreviewed_labels": pending_gold,
            "license_unverified": pending_license, "hash_mismatches": mismatches,
            "gold_tree_hash_mismatches": gold_hash_mismatches, "missing_gold_tree_hashes": missing_gold_hashes,
            "duplicate_template_ids": duplicate_templates, "duplicate_family_ids": duplicate_families,
            "duplicate_content_hashes": duplicate_hashes, "gold_schema_errors": gold_schema_errors,
            "metadata_errors": metadata_errors, "missing_manifest_fields": missing_fields,
            "family_overlap": overlap, "split_errors": split_errors,
            "unlisted_templates": unlisted_templates, "missing_template_folders": missing_template_folders,
            "source_inventory": source_inventory,
            "pending_scientific_evidence": pending_scientific_evidence,
            "manifest_sha256": digest, "split_lock_verified": locked}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--locked-manifest-sha256")
    args = parser.parse_args()
    report = check_data(locked_manifest_sha256=args.locked_manifest_sha256)
    print(json.dumps(report, indent=2))
    integrity_keys = ("hash_mismatches", "gold_tree_hash_mismatches", "missing_gold_tree_hashes",
                      "duplicate_template_ids", "duplicate_family_ids", "duplicate_content_hashes",
                      "gold_schema_errors", "metadata_errors", "missing_manifest_fields", "family_overlap",
                      "unlisted_templates", "missing_template_folders")
    if any(report[key] for key in integrity_keys):
        raise SystemExit(1)
