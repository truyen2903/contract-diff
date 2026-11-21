"""Đánh giá ban đầu (dev pilot) của layout cleaner + contract parser trên gold trong data/raw_templates.

Chạy: .venv/Scripts/python -m experiments.evaluate_structure [--json đường_dẫn]
Chỉ là kiểm tra trên tập phát triển (dev_train, gold chưa được tác giả duyệt), không phải kết quả RQ1.
Đơn vị đánh giá (kế hoạch v2 §5.4): tập dòng content của node; ARTICLE tính trên cả cây con.
"""

import argparse
import hashlib
import json
from io import BytesIO
from pathlib import Path

from app.extractors.layout_cleaner import LINE_BREAK
from app.extractors.pdf_extractor import extract_pdf_lines
from app.parsers.contract_parser import parse_contract_pages


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "raw_templates"
SCORED_TYPES = ("ARTICLE", "CLAUSE")


def split_allowed(split, include_holdout=False):
    return split in ("dev_train", "dev_val") or (include_holdout and split == "test_holdout")


def char_iou(predicted, gold, weights):
    union = predicted | gold
    if not union:
        return 1.0
    return sum(weights[line] for line in predicted & gold) / sum(weights[line] for line in union)


def match_units(predicted, gold, weights, threshold):
    # Ghép một–một: xét các cặp theo IoU giảm dần, tie-break theo chỉ số để tất định.
    pairs = []
    for i, unit in enumerate(predicted):
        for j, target in enumerate(gold):
            iou = char_iou(unit, target, weights)
            if iou >= threshold and iou > 0:
                pairs.append((-iou, i, j))
    used_predicted, used_gold, matches = set(), set(), []
    for _, i, j in sorted(pairs):
        if i not in used_predicted and j not in used_gold:
            used_predicted.add(i)
            used_gold.add(j)
            matches.append((i, j))
    return sorted(matches)


def precision_recall_f1(true_positive, predicted_count, gold_count):
    precision = true_positive / predicted_count if predicted_count else 1.0
    recall = true_positive / gold_count if gold_count else 1.0
    if predicted_count == 0 and gold_count == 0:
        return 1.0, 1.0, 1.0
    if predicted_count == 0 or gold_count == 0:
        return precision, recall, 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def load_template(folder):
    gold = json.loads((folder / "gold_tree.json").read_text(encoding="utf-8"))
    raw = (folder / gold["transcript"]).read_bytes()
    if hashlib.sha256(raw).hexdigest() != gold["transcript_sha256"]:
        raise ValueError(f"{folder.name}: văn bản nguồn khác hash trong gold")
    pages = raw.decode("utf-8").split("\f")
    return gold, [{"page_number": n, "text": text} for n, text in enumerate(pages, start=1)]


def gold_lines(gold, pages):
    layout = {(item["page"], item["line_index"]) for item in gold["layout_lines"]}
    weights, content = {}, set()
    for page in pages:
        for index, text in enumerate(LINE_BREAK.split(page["text"])):
            key = (page["page_number"], index)
            weights[key] = max(len(text.strip()), 1)
            if text.strip() and key not in layout:
                content.add(key)
    return content, layout, weights


def gold_units(gold, content):
    owned = {}
    for node in gold["nodes"]:
        lines = set()
        for span in node["lines"]:
            lines |= {(span["page"], index) for index in range(span["start"], span["end"] + 1)}
        owned[node["gold_id"]] = lines & content
    units = {node_type: [] for node_type in SCORED_TYPES}
    for node in gold["nodes"]:
        if node["node_type"] in SCORED_TYPES:
            lines = set(owned[node["gold_id"]])
            for child in gold["nodes"]:
                if child["parent"] == node["gold_id"]:
                    lines |= owned[child["gold_id"]]
            units[node["node_type"]].append(frozenset(lines))
    return units


def predicted_units(result):
    # Tính trên mọi dòng node sở hữu (kể cả dòng layout không bị mask) để lỗi lọt layout bị phạt.
    owned = {}
    for node in result["nodes"]:
        lines = set()
        for span in node["source_spans"]:
            for line in result["lines"]:
                if (line["page_number"] == span["page_number"]
                        and span["clean_char_start"] <= line["clean_start"] < span["clean_char_end"]):
                    lines.add((line["page_number"], line["line_index"]))
        owned[node["node_id"]] = lines
    units = {node_type: [] for node_type in SCORED_TYPES}
    for node in result["nodes"]:
        if node["node_type"] in SCORED_TYPES:
            lines = set(owned[node["node_id"]])
            for child in node["children"]:
                lines |= owned[child]
            units[node["node_type"]].append(frozenset(lines))
    return units


def evaluate(result, gold, pages):
    content, layout, weights = gold_lines(gold, pages)
    expected = gold_units(gold, content)
    actual = predicted_units(result)
    scores = {}
    for node_type in SCORED_TYPES:
        for name, threshold in (("exact", 1.0), ("relaxed", 0.9)):
            matches = match_units(actual[node_type], expected[node_type], weights, threshold)
            scores[f"{node_type}_{name}"] = {
                "tp": len(matches), "predicted": len(actual[node_type]), "gold": len(expected[node_type]),
            }
    masked = {(line["page_number"], line["line_index"]) for line in result["lines"] if line["masked"]}
    scores["masked_content_lines"] = len(masked & content)
    scores["content_lines"] = len(content)
    scores["masked_layout_lines"] = len(masked & layout)
    scores["layout_lines"] = len(layout)
    scores["warnings"] = sorted({warning for node in result["nodes"] for warning in node["warnings"]} | set(result["warnings"]))
    return scores


def pdf_pages(gold):
    pdf = (ROOT / gold["source_pdf"]).read_bytes()
    if hashlib.sha256(pdf).hexdigest() != gold["source_pdf_sha256"]:
        raise ValueError("PDF khác hash trong gold")
    return extract_pdf_lines(BytesIO(pdf), 100)


def run_all(include_holdout=False):
    manifest_path = ROOT / "data" / "dataset_manifest.json"
    manifest_rows = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    splits = {row["template_id"]: row.get("assigned_split", "dev_train") for row in manifest_rows}
    runs = []
    for folder in sorted(DATA.iterdir()):
        split = splits.get(folder.name, "dev_train")
        if not split_allowed(split, include_holdout):
            continue
        gold, pages = load_template(folder)
        result = parse_contract_pages(pages, "PLAIN_TEXT")
        runs.append({"template_id": folder.name, "split": split, "input": "PLAIN_TEXT",
                     **evaluate(result, gold, pages)})
        if "source_pdf" in gold:
            extracted = pdf_pages(gold)
            if [page["text"] for page in extracted] != [page["text"] for page in pages]:
                raise ValueError(f"{folder.name}: transcript PDF bị trôi")
            for ratio in (0.07, 0.08, 0.10):
                result = parse_contract_pages(extracted, "PDF_DIGITAL", edge_zone_ratio=ratio)
                runs.append({"template_id": folder.name, "split": split,
                             "input": f"PDF_DIGITAL edge={ratio:.2f}",
                             **evaluate(result, gold, pages)})
    return runs


def total(runs, key):
    return {field: sum(run[key][field] for run in runs) for field in ("tp", "predicted", "gold")}


def report(runs):
    rows = ["| Mẫu | Đầu vào | ARTICLE exact TP/pred/gold | CLAUSE exact TP/pred/gold | CLAUSE IoU≥0,9 | Content bị mask | Layout bị mask | Cảnh báo |",
            "|---|---|---|---|---|---|---|---|"]
    for run in runs:
        def cell(key):
            return "{tp}/{predicted}/{gold}".format(**run[key])
        rows.append(f"| {run['template_id']} | {run['input']} | {cell('ARTICLE_exact')} | {cell('CLAUSE_exact')} | "
                    f"{cell('CLAUSE_relaxed')} | {run['masked_content_lines']}/{run['content_lines']} | "
                    f"{run['masked_layout_lines']}/{run['layout_lines']} | {', '.join(run['warnings'])} |")
    plain = [run for run in runs if run["input"] == "PLAIN_TEXT"]
    rows.append("")
    rows.append(f"Tổng micro trên đầu vào văn bản ({len(plain)} mẫu):")
    for key in ("ARTICLE_exact", "ARTICLE_relaxed", "CLAUSE_exact", "CLAUSE_relaxed"):
        counts = total(plain, key)
        precision, recall, f1 = precision_recall_f1(counts["tp"], counts["predicted"], counts["gold"])
        rows.append(f"- {key}: TP={counts['tp']} pred={counts['predicted']} gold={counts['gold']} "
                    f"P={precision:.3f} R={recall:.3f} F1={f1:.3f}")
    return "\n".join(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--json")
    parser.add_argument("--include-test-holdout", action="store_true")
    args = parser.parse_args()
    runs = run_all(include_holdout=args.include_test_holdout)
    print(report(runs))
    if args.json:
        Path(args.json).write_text(json.dumps(runs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
