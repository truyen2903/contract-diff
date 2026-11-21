import hashlib
import json

from experiments.check_alignment_data import check_data


def make_manifest(root, rows):
    (root / "dataset_manifest.json").write_text(json.dumps(rows), encoding="utf-8")


def make_family(root, template_id, text="Điều 1\nNội dung"):
    folder = root / "raw_templates" / template_id
    folder.mkdir(parents=True)
    digest = hashlib.sha256(text.encode()).hexdigest()
    (folder / "source.txt").write_bytes(text.encode("utf-8"))
    (folder / "gold_tree.json").write_text(json.dumps({
        "review_status": "PENDING_AUTHOR_REVIEW",
        "transcript": "source.txt",
        "transcript_sha256": digest,
        "nodes": [{"gold_id": "g1", "node_type": "ARTICLE", "parent": None,
                   "number_label": "Điều 1", "title": None,
                   "lines": [{"page": 1, "start": 0, "end": 1}]}],
        "layout_lines": [],
    }), encoding="utf-8")
    return digest


def row(template_id, family, digest, split="dev_train"):
    return {"template_id": template_id, "root_family_id": family, "assigned_split": split,
            "sha256_text": digest, "gold_review_status": "PENDING_AUTHOR_REVIEW",
            "license_confirmed_by_author": False}


def test_governance_reports_duplicates_and_missing_metadata(tmp_path):
    digest = make_family(tmp_path, "A")
    make_manifest(tmp_path, [row("A", "F", digest), row("A", "F", digest)])
    report = check_data(tmp_path)
    assert report["eligible"] is False
    assert report["duplicate_template_ids"] == ["A"]
    assert report["duplicate_family_ids"] == ["F"]
    assert "A" in report["unreviewed_labels"]
    assert "A" in report["license_unverified"]


def test_governance_detects_gold_schema_and_content_hash_errors(tmp_path):
    digest = make_family(tmp_path, "A", "Điều 1\nNội dung")
    (tmp_path / "raw_templates" / "A" / "gold_tree.json").write_text(json.dumps({
        "review_status": "PENDING_AUTHOR_REVIEW", "transcript": "source.txt",
        "transcript_sha256": "0" * 64, "nodes": [
            {"gold_id": "g1", "node_type": "UNKNOWN", "parent": "missing",
             "lines": [{"page": 4, "start": 3, "end": 1}]},
            {"gold_id": "g1", "node_type": "ARTICLE", "parent": None,
             "lines": []}], "layout_lines": []}), encoding="utf-8")
    make_manifest(tmp_path, [row("A", "F", digest)])
    report = check_data(tmp_path)
    assert report["hash_mismatches"] == ["A"]
    assert report["gold_schema_errors"]["A"]
    assert any("duplicate gold_id" in error for error in report["gold_schema_errors"]["A"])


def test_governance_validates_split_counts_and_hash_duplicates(tmp_path):
    d1 = make_family(tmp_path, "A", "A")
    d2 = make_family(tmp_path, "B", "B")
    make_manifest(tmp_path, [row("A", "F1", d1), row("B", "F2", d1, "dev_val")])
    report = check_data(tmp_path)
    assert report["duplicate_content_hashes"] == [d1]
    assert report["split_counts"] == {"dev_train": 1, "dev_val": 1}
    assert report["split_errors"]


def test_governance_detects_gold_tree_modification(tmp_path):
    digest = make_family(tmp_path, "A")
    gold_path = tmp_path / "raw_templates" / "A" / "gold_tree.json"
    gold_hash = hashlib.sha256(gold_path.read_bytes()).hexdigest()
    manifest_row = row("A", "F", digest)
    manifest_row["gold_tree_sha256"] = gold_hash
    make_manifest(tmp_path, [manifest_row])
    gold_path.write_text(gold_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    report = check_data(tmp_path)
    assert report["gold_tree_hash_mismatches"] == ["A"]


def test_governance_detects_unlisted_template_folder(tmp_path):
    make_family(tmp_path, "A")
    make_manifest(tmp_path, [])
    report = check_data(tmp_path)
    assert report["unlisted_templates"] == ["A"]


def test_scientific_gate_requires_source_and_review_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr("experiments.check_alignment_data.EXPECTED_SPLITS", {"dev_train": 1})
    digest = make_family(tmp_path, "A")
    gold_path = tmp_path / "raw_templates" / "A" / "gold_tree.json"
    gold = json.loads(gold_path.read_bytes())
    gold["review_status"] = "APPROVED"
    gold_path.write_text(json.dumps(gold), encoding="utf-8")
    entry = row("A", "F", digest)
    entry.update(gold_review_status="APPROVED", license_confirmed_by_author=True,
                 gold_tree_sha256=hashlib.sha256(gold_path.read_bytes()).hexdigest())

    def eligible():
        make_manifest(tmp_path, [entry])
        lock = hashlib.sha256((tmp_path / "dataset_manifest.json").read_bytes()).hexdigest()
        return check_data(tmp_path, locked_manifest_sha256=lock)["eligible"]

    assert not eligible()
    entry.update(source_kind="sourced_contract", provenance_evidence="intake/1",
                 license_evidence="permissions/1", independence_status="VERIFIED",
                 independent_annotation=True, adjudication_evidence="reviews/1")
    assert eligible()
    entry["source_kind"] = "synthetic"
    assert not eligible()
