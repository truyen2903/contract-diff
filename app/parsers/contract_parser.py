"""Phân đoạn hợp đồng tiếng Việt thành cây PREAMBLE / ARTICLE / CLAUSE / PARAGRAPH / SIGNATURE.

Máy trạng thái duyệt các dòng không trắng, không bị mask. Mỗi dòng thuộc đúng một node;
khi không chắc một dòng là đầu mục, giữ nó trong node đang mở và gắn cảnh báo.
Quy tắc: docs/implementation/reviews/phase-b1/round3-consensus.md.
"""

import re

from app.extractors.layout_cleaner import (EDGE_ZONE_RATIO, QUALITY_WARNINGS, REVIEW_PAGE_WARNINGS, clean_layout,
                                           recognition_text)


# Số hiệu dài hơn mức này không phải đầu mục (và không bao giờ được đổi sang int).
MAX_NUMBER_DIGITS = 6
INDENT_TOLERANCE = 4.0

ARTICLE = re.compile(r"^(?P<word>Điều|ĐIỀU)[ \t]+(?P<number>[0-9]+[a-zA-Z]?|[IVXLCDM]+)(?!\w|\.[0-9])(?P<rest>.*)$")
EXPLICIT_CLAUSE = re.compile(r"^(?P<word>Khoản|KHOẢN)[ \t]+(?P<number>[0-9]+)(?!\w|\.[0-9])(?P<rest>.*)$")
SECTION = re.compile(
    r"^(?P<word>PHẦN|Phần|CHƯƠNG|Chương|PHỤ LỤC|Phụ lục)[ \t]+(?P<number>[0-9]+|[IVXLCDM]+)(?!\w|\.[0-9])(?P<rest>.*)$"
)
SIMPLE_CLAUSE = re.compile(r"^(?P<number>[0-9]+)[.)][ \t]+(?P<body>\S.*)$")
DOTTED_CLAUSE = re.compile(r"^(?P<prefix>[0-9]+)\.(?P<number>[0-9]+)(?![0-9]|\.[0-9])\.?[ \t]+(?P<body>\S.*)$")
POINT = re.compile(r"^(?:[a-zđ][.)]|[0-9]+(?:\.[0-9]+){2,}\.?)[ \t]")
SIGNATURE = re.compile(r"^ĐẠI DIỆN\b")
ROMAN = re.compile(r"M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})")
DELIMITED_REST = re.compile(r"^[ \t]*[.:\-–—][ \t]*(?P<title>.*)$")
CURRENCY_START = re.compile(r"^(?:USD|VND|VNĐ|EUR)\b|^%")
DANGLING_WORD = re.compile(r"\b(?:khoản|điều|mục|phần|chương|điểm|tại|theo|của|và|hoặc)$", re.IGNORECASE)
ROMAN_VALUES = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
OPENING_MARKS = "([\"'“‘«"
CLOSING_MARKS = ")]\"'”’»"
TERMINAL_MARKS = (".", ";", ":", "!", "?", "…")


def is_all_caps(text):
    return any(char.isalpha() for char in text) and not any(char.islower() for char in text)


def roman_value(numeral):
    total = 0
    for char, following in zip(numeral, numeral[1:] + " "):
        value = ROMAN_VALUES[char]
        total += -value if following != " " and ROMAN_VALUES[following] > value else value
    return total


def number_value(number):
    digits = re.match(r"[0-9]+", number)
    return int(digits.group()) if digits else roman_value(number)


def read_heading(pattern, text):
    """None nếu không phải đầu mục; {"uncertain": True} nếu giống đầu mục nhưng phần đuôi không đủ chắc."""
    match = pattern.match(text)
    if not match:
        return None
    number = match["number"]
    if number.isalpha() and not ROMAN.fullmatch(number):
        return None
    digits = re.match(r"[0-9]+", number)
    if digits and len(digits.group()) > MAX_NUMBER_DIGITS:
        return None
    rest = match["rest"]
    heading = {"label": f"{match['word']} {number}", "number": number, "strict": True, "title": None}
    if not rest.strip():
        return heading
    delimited = DELIMITED_REST.match(rest)
    if delimited:
        heading["title"] = delimited["title"].strip() or None
        return heading
    tail = rest.strip()
    # Chỉ cách bằng khoảng trắng: nhận khi đuôi viết hoa toàn bộ (ĐIỀU 1 ĐỐI TƯỢNG HỢP ĐỒNG).
    if rest[0] in " \t" and is_all_caps(tail):
        heading["strict"] = False
        heading["title"] = tail
        return heading
    return {"uncertain": True}


def is_heading(heading):
    return heading is not None and not heading.get("uncertain")


def is_strict_heading(heading):
    return is_heading(heading) and heading["strict"]


def numbered_clause(text):
    match = DOTTED_CLAUSE.match(text) or SIMPLE_CLAUSE.match(text)
    if not match:
        return None
    prefix = match.groupdict().get("prefix")
    if len(match["number"]) > MAX_NUMBER_DIGITS or (prefix and len(prefix) > MAX_NUMBER_DIGITS):
        return None
    body = match["body"].lstrip(OPENING_MARKS)
    if not body or not body[0].isupper() or CURRENCY_START.match(body):
        return None
    return {
        "label": f"{prefix}.{match['number']}" if prefix else match["number"],
        "prefix": int(prefix) if prefix else None,
        "number": int(match["number"]),
    }


def has_boundary(previous):
    # Ranh giới trước một Khoản đánh số: sau đầu mục, sau câu đã kết thúc, hoặc trong danh sách ngắn.
    if previous["kind"] in ("ARTICLE", "TITLE", "SECTION"):
        return True
    text = previous["text"].rstrip().rstrip(CLOSING_MARKS)
    if text.endswith(TERMINAL_MARKS):
        return True
    return previous["kind"] == "CLAUSE" and not DANGLING_WORD.search(text)


def ends_article_scope(text):
    return is_heading(read_heading(ARTICLE, text)) or is_heading(read_heading(SECTION, text)) or SIGNATURE.match(text)


def count_prefixes(content, position, heading):
    # Đếm tiền tố d1 của các Khoản d1.d2 qua đủ cổng nhận Khoản, trong phạm vi Điều hiện tại.
    # Đi lại các dòng với cùng cách phân loại TITLE/CLAUSE như build_nodes để ranh giới khớp nhau.
    counts = {}
    previous = {"kind": "ARTICLE", "text": recognition_text(content[position]["text"]), "line": content[position]}
    expecting_title = heading["title"] is None
    for index in range(position + 1, len(content)):
        line = content[index]
        text = recognition_text(line["text"])
        if not text:
            # Dòng chỉ có ký tự vô hình: không cắt quan hệ liền kề giữa đầu mục và tiêu đề.
            previous["line"] = line
            continue
        if ends_article_scope(text):
            break
        if expecting_title:
            expecting_title = False
            if is_title_line(text, previous["line"], line):
                previous = {"kind": "TITLE", "text": text, "line": line}
                continue
        kind = "TEXT"
        if not POINT.match(text):
            candidate = numbered_clause(text)
            if is_heading(read_heading(EXPLICIT_CLAUSE, text)):
                kind = "CLAUSE"
            elif candidate and has_boundary(previous):
                kind = "CLAUSE"
                if candidate["prefix"] is not None:
                    counts[candidate["prefix"]] = counts.get(candidate["prefix"], 0) + 1
        previous = {"kind": kind, "text": text, "line": line}
    return counts


def numbering_warnings(previous_number, number):
    if previous_number is None:
        return [] if number == 1 else ["NON_CONSECUTIVE_CLAUSE_NUMBER"]
    if number == previous_number:
        return ["DUPLICATE_CLAUSE_NUMBER"]
    if number != previous_number + 1:
        return ["NON_CONSECUTIVE_CLAUSE_NUMBER"]
    return []


def is_title_line(text, previous_line, line):
    adjacent = previous_line["page_number"] == line["page_number"] and previous_line["line_index"] + 1 == line["line_index"]
    return (
        adjacent
        and is_all_caps(text)
        and len(text) <= 120
        and read_heading(ARTICLE, text) is None
        and read_heading(SECTION, text) is None
        and read_heading(EXPLICIT_CLAUSE, text) is None
        and numbered_clause(text) is None
        and not POINT.match(text)
        and not SIGNATURE.match(text)
    )


def match_clause(text, article, previous, owner):
    """Trả (nhãn, số, cảnh báo của Khoản mới) nếu dòng mở Khoản; nếu không, gắn cảnh báo cho owner và trả None."""
    if POINT.match(text):
        return None
    explicit = read_heading(EXPLICIT_CLAUSE, text)
    if is_heading(explicit):
        return explicit["label"], int(explicit["number"]), []
    candidate = numbered_clause(text)
    if candidate is None:
        return None
    stale_prefix = candidate["prefix"] is not None and candidate["prefix"] != article["_number"]
    if stale_prefix and article["_prefix_counts"].get(candidate["prefix"], 0) < 2:
        add_warning(owner, "NUMBERING_PARENT_MISMATCH")
        return None
    if not has_boundary(previous):
        add_warning(owner, "AMBIGUOUS_CLAUSE_CANDIDATE")
        return None
    return candidate["label"], candidate["number"], ["NUMBERING_PARENT_MISMATCH"] if stale_prefix else []


def new_node(nodes, node_type, parent=None, number_label=None, title=None, section_context=None):
    node = {
        "node_id": f"n{len(nodes) + 1:04d}",
        "node_type": node_type,
        "parent_id": parent["node_id"] if parent else None,
        "children": [],
        "section_context": section_context,
        "number_label": number_label,
        "title": title,
        "warnings": [],
        "_lines": [],
    }
    if parent:
        parent["children"].append(node["node_id"])
    nodes.append(node)
    return node


def add_warning(node, warning):
    if warning not in node["warnings"]:
        node["warnings"].append(warning)


def check_indent(article, clause, line):
    # Khoản lệch lề so với Khoản đầu tiên có tọa độ của cùng Điều trên cùng trang: chỉ cảnh báo.
    bbox = line["bbox"]
    if bbox is None:
        return
    anchors = article.setdefault("_indent", {})
    anchor = anchors.setdefault(line["page_number"], bbox["x0"])
    if abs(bbox["x0"] - anchor) > INDENT_TOLERANCE:
        add_warning(clause, "CLAUSE_INDENT_MISMATCH")


def build_nodes(content):
    nodes = []
    article = clause_number = owner = expecting_title = previous = None
    section_context = None
    in_signature = after_signature = seen_article = False

    for position, line in enumerate(content):
        text = recognition_text(line["text"])
        if not text:
            # Dòng chỉ có ký tự vô hình (BOM, khoảng trắng không ngắt): giữ trong node đang mở,
            # không đổi ranh giới, và không cắt quan hệ liền kề giữa đầu mục và tiêu đề.
            if owner is None:
                owner = new_node(nodes, "PREAMBLE")
            owner["_lines"].append(line)
            if previous:
                previous["line"] = line
            continue
        article_heading = read_heading(ARTICLE, text)
        section_heading = read_heading(SECTION, text)

        if expecting_title:
            expecting_title = False
            if is_title_line(text, previous["line"], line):
                article["title"] = text
                article["_lines"].append(line)
                previous = {"kind": "TITLE", "text": text, "line": line}
                continue
            add_warning(article, "ARTICLE_TITLE_UNRESOLVED")

        # Sau khối ký chỉ đầu mục dạng chặt mới mở lại cấu trúc.
        opens_article = is_strict_heading(article_heading) if after_signature else is_heading(article_heading)
        opens_section = is_strict_heading(section_heading) if after_signature else is_heading(section_heading)

        if opens_article:
            article = owner = new_node(
                nodes, "ARTICLE", number_label=article_heading["label"],
                title=article_heading["title"], section_context=section_context,
            )
            if after_signature:
                add_warning(article, "STRUCTURE_AFTER_SIGNATURE")
            article["_number"] = number_value(article_heading["number"])
            article["_prefix_counts"] = count_prefixes(content, position, article_heading)
            article["_lines"].append(line)
            clause_number = None
            in_signature = after_signature = False
            seen_article = True
            expecting_title = article_heading["title"] is None
            previous = {"kind": "ARTICLE", "text": text, "line": line}
            continue

        if opens_section:
            section_context = text
            owner = new_node(nodes, "PARAGRAPH", title=text, section_context=section_context)
            if after_signature:
                add_warning(owner, "STRUCTURE_AFTER_SIGNATURE")
            owner["_lines"].append(line)
            article = None
            in_signature = False
            previous = {"kind": "SECTION", "text": text, "line": line}
            continue

        if seen_article and not in_signature and SIGNATURE.match(text):
            owner = new_node(nodes, "SIGNATURE")
            owner["_lines"].append(line)
            article = None
            in_signature = after_signature = True
            previous = {"kind": "TEXT", "text": text, "line": line}
            continue

        kind = "TEXT"
        if article is not None:
            clause = match_clause(text, article, previous, owner)
            if clause:
                label, number, warnings = clause
                owner = new_node(nodes, "CLAUSE", parent=article, number_label=label, section_context=section_context)
                for warning in warnings + numbering_warnings(clause_number, number):
                    add_warning(owner, warning)
                check_indent(article, owner, line)
                clause_number = number
                kind = "CLAUSE"

        if owner is None:
            owner = new_node(nodes, "PREAMBLE")
        if kind == "TEXT" and (article_heading or section_heading or read_heading(EXPLICIT_CLAUSE, text)):
            add_warning(owner, "UNCERTAIN_HEADING")
        owner["_lines"].append(line)
        previous = {"kind": kind, "text": text, "line": line}

    if expecting_title:
        add_warning(article, "ARTICLE_TITLE_UNRESOLVED")
    return nodes


def line_runs(lines):
    # Các dải dòng liên tiếp trên cùng một trang.
    runs = []
    for line in lines:
        last = runs[-1][-1] if runs else None
        if last and last["page_number"] == line["page_number"] and last["line_index"] + 1 == line["line_index"]:
            runs[-1].append(line)
        else:
            runs.append([line])
    return runs


def union_box(lines):
    boxes = [line["bbox"] for line in lines]
    if any(box is None for box in boxes):
        return None
    return {
        "page": boxes[0]["page"],
        "x0": min(box["x0"] for box in boxes),
        "top": min(box["top"] for box in boxes),
        "x1": max(box["x1"] for box in boxes),
        "bottom": max(box["bottom"] for box in boxes),
    }


def finalize_node(node, nodes_by_id, source_type, page_warnings):
    spans = []
    for run in line_runs(node["_lines"]):
        spans.append({
            "page_number": run[0]["page_number"],
            "raw_char_start": run[0]["raw_start"],
            "raw_char_end": run[-1]["raw_end"],
            "clean_char_start": run[0]["clean_start"],
            "clean_char_end": run[-1]["clean_end"],
            "bbox": union_box(run),
            "source_type": source_type,
        })
    # Cây chỉ sâu hai cấp (ARTICLE > CLAUSE), nên cây con là node và các con trực tiếp.
    subtree = [node] + [nodes_by_id[child] for child in node["children"]]
    subtree_lines = [line for member in subtree for line in member["_lines"]]
    page_numbers = sorted({line["page_number"] for line in subtree_lines})
    bboxes = []
    for page_number in page_numbers:
        box = union_box([line for line in subtree_lines if line["page_number"] == page_number])
        if box:
            bboxes.append(box)
    warnings = list(node["warnings"])
    for page_number in page_numbers:
        for warning in page_warnings.get(page_number, []):
            if warning in QUALITY_WARNINGS and warning not in warnings:
                warnings.append(warning)
    return {
        "node_id": node["node_id"],
        "node_type": node["node_type"],
        "parent_id": node["parent_id"],
        "children": node["children"],
        "section_context": node["section_context"],
        "number_label": node["number_label"],
        "title": node["title"],
        "own_text": "\n".join(line["text"] for line in node["_lines"]),
        "subtree_text": "\n".join(line["text"] for line in subtree_lines),
        "page_numbers": page_numbers,
        "bboxes": bboxes,
        "source_spans": spans,
        "warnings": warnings,
    }


def parse_contract(layout) -> dict:
    content = [line for line in layout["lines"] if not line["masked"] and line["text"].strip()]
    warnings = []
    if any(is_heading(read_heading(ARTICLE, recognition_text(line["text"]))) for line in content):
        nodes = build_nodes(content)
    else:
        nodes = []
        if content:
            paragraph = new_node(nodes, "PARAGRAPH")
            paragraph["_lines"] = content
            warnings.append("NO_STRUCTURE_DETECTED")
        elif any(line["masked"] for line in layout["lines"]):
            warnings.append("ALL_CONTENT_MASKED")

    page_warnings = {page["page_number"]: page["warnings"] for page in layout["page_warnings"]}
    nodes_by_id = {node["node_id"]: node for node in nodes}
    result_nodes = [finalize_node(node, nodes_by_id, layout["source_type"], page_warnings) for node in nodes]
    needs_review = bool(warnings) or any(node["warnings"] for node in result_nodes) or any(
        warning in REVIEW_PAGE_WARNINGS for page in layout["page_warnings"] for warning in page["warnings"]
    )
    return {**layout, "nodes": result_nodes, "warnings": warnings, "needs_review": needs_review}


def parse_contract_pages(pages, source_type, enable_layout_cleaning=True, edge_zone_ratio=EDGE_ZONE_RATIO) -> dict:
    return parse_contract(clean_layout(pages, source_type, enable_layout_cleaning, edge_zone_ratio))


def parse_contract_text(text) -> dict:
    return parse_contract_pages([{"page_number": 1, "text": text}], "PLAIN_TEXT")
