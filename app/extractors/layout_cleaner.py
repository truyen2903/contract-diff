"""Sổ dòng có ánh xạ nguồn, soft-mask header/footer/số trang và cảnh báo chất lượng trang.

Không xóa nội dung: dòng bị mask vẫn nằm trong sổ dòng. Không tự mask khi thiếu tọa độ thật.
"""

import math
import re
import unicodedata
from statistics import median


# Sai lệch có chủ đích so với §4.1 (8%/7%): header thực tế của fixture nằm tới 8,8% chiều cao trang.
EDGE_ZONE_RATIO = 0.10
TOP_STABILITY_RATIO = 0.02
PAGE_SEPARATOR = "\n\n"

QUALITY_WARNINGS = ("EMPTY_OR_SCANNED_PAGE", "GARBLED_TEXT_ENCODING")
REVIEW_PAGE_WARNINGS = QUALITY_WARNINGS + ("LINE_GEOMETRY_UNAVAILABLE", "LAYOUT_CANDIDATE")

LINE_BREAK = re.compile(r"\r\n|\r|\n")
PAGE_NUMBER = re.compile(r"(?:(?:trang|page)[ \t]+[0-9]+(?:[ \t]*(?:/|trên|of)[ \t]*[0-9]+)?|-[ \t]*[0-9]+[ \t]*-)", re.IGNORECASE)
PAGE_SUFFIX = re.compile(r"^(?P<prefix>.*?)[ \t]*(?:trang|page)[ \t]+(?P<page>[0-9]+)[ \t]*(?:/|trên|of)[ \t]*(?P<total>[0-9]+)$", re.IGNORECASE)
# Chỉ số trang tường minh ở cuối dòng; số trần ("đợt 3") không bị coi là số trang.
TRAILING_PAGE_NUMBER = re.compile(
    r"[ \t]*(?:(?:trang|page)[ \t]+[0-9]+(?:[ \t]*(?:/|trên|of)[ \t]*[0-9]+)?|(?<![0-9/])[0-9]+[ \t]*(?:/|trên|of)[ \t]*[0-9]+|-[ \t]*[0-9]+[ \t]*-)$",
    re.IGNORECASE,
)
STRUCTURE_START = re.compile(r"^(?:Điều|ĐIỀU|Khoản|KHOẢN|PHẦN|Phần|CHƯƠNG|Chương|PHỤ LỤC|Phụ lục|[0-9]+[.)]|[0-9]+\.[0-9]+|[a-zđ][.)])")
PROTECTED_CONTENT = re.compile(
    r"[0-9][0-9.,]*[ \t]*(?:đồng|tỷ|triệu|nghìn)\b|(?<![^\W\d_])(?:vnđ|vnd|usd|eur)(?![^\W\d_])|%"
    r"|[0-9]{1,2}[ \t]*[/.-][ \t]*[0-9]{1,2}[ \t]*[/.-][ \t]*[0-9]{2,4}"
    r"|\b(?:phải|không được|có nghĩa vụ|có quyền|cam kết|chịu trách nhiệm)\b",
    re.IGNORECASE,
)
# Dấu hiệu khối ký (M7: dòng mở khối ký bắt đầu bằng "ĐẠI DIỆN"): không mask, không coi là trang quét.
SIGNATURE_KEYWORDS = ("ĐẠI DIỆN", "KÝ TÊN", "GIÁM ĐỐC")
GARBLED = re.compile(r"\x00|\ufffd|[\ue000-\uf8ff]|\(cid:[0-9]+\)")
CID = re.compile(r"\(cid:[0-9]+\)")
LEGACY_ENCODING = re.compile(r"(?<=[A-Za-z])[\u00b5\u00b8\u00b9\u00ae\u00ac](?=[A-Za-z])")


def recognition_text(text):
    # Chỉ dùng để nhận diện, không sửa nội dung: khoảng trắng không ngắt và BOM coi như khoảng trắng.
    return text.replace("\u00a0", " ").replace("\ufeff", "").strip()


def page_quality_warnings(text, image_coverage, source_type) -> list[str]:
    text = unicodedata.normalize("NFC", text)
    warnings = []
    content = text.strip()
    if source_type == "PDF_DIGITAL":
        has_signature = any(keyword in content.upper() for keyword in SIGNATURE_KEYWORDS)
        if (len(content) < 20 and not has_signature) or (image_coverage >= 0.5 and len(content) < 50):
            warnings.append("EMPTY_OR_SCANNED_PAGE")
    bad = sum(len(match.group()) for match in GARBLED.finditer(text))
    visible = sum(1 for char in text if not char.isspace())
    if (visible and bad / visible > 0.01) or len(CID.findall(text)) >= 3 or len(LEGACY_ENCODING.findall(text)) >= 5:
        warnings.append("GARBLED_TEXT_ENCODING")
    return warnings


def build_lines(pages) -> tuple[list[dict], str, set]:
    lines = []
    page_texts = []
    geometry_mismatch = set()
    clean_offset = 0
    for page in pages:
        raw = page["text"]
        breaks = list(LINE_BREAK.finditer(raw)) + [None]
        boxes = page.get("line_boxes")
        if boxes is not None and len(boxes) != len(breaks):
            # Số dòng không khớp số tọa độ: không gắn tọa độ nào cho trang này.
            boxes = None
            geometry_mismatch.add(page["page_number"])
        page_lines = []
        start = 0
        for line_index, match in enumerate(breaks):
            end = match.start() if match else len(raw)
            text = unicodedata.normalize("NFC", raw[start:end])
            bbox = None
            if boxes is not None and boxes[line_index] is not None:
                bbox = {"page": page["page_number"], **boxes[line_index]}
            lines.append({
                "page_number": page["page_number"],
                "line_index": line_index,
                "text": text,
                "raw_start": start,
                "raw_end": end,
                "raw_offsets_exact": raw[start:end] == text,
                "clean_start": clean_offset,
                "clean_end": clean_offset + len(text),
                "bbox": bbox,
                "masked": False,
                "mask_reason": None,
            })
            page_lines.append(text)
            clean_offset += len(text) + 1
            start = match.end() if match else end
        page_texts.append("\n".join(page_lines))
        clean_offset += len(PAGE_SEPARATOR) - 1
    return lines, PAGE_SEPARATOR.join(page_texts), geometry_mismatch


def in_edge_zone(line, height, edge_zone_ratio):
    bbox = line["bbox"]
    if bbox is None or not height:
        return None
    if bbox["bottom"] <= edge_zone_ratio * height:
        return "TOP"
    if bbox["top"] >= (1 - edge_zone_ratio) * height:
        return "BOTTOM"
    return None


def looks_like_layout(text):
    # Bốn điều kiện bảo vệ nội dung của §4.1 Quy tắc B, thêm từ khóa khối ký.
    return (
        len(text) <= 100
        and not text.endswith((".", ";", ":"))
        and not STRUCTURE_START.match(text)
        and not PROTECTED_CONTENT.search(text)
        and not any(keyword in text.upper() for keyword in SIGNATURE_KEYWORDS)
    )


def same_number(digits, value):
    # So sánh dạng chuỗi: không đổi chuỗi chữ số dài tùy ý sang int.
    return digits.lstrip("0") == str(value)


def stable_members(members, heights):
    # Chỉ giữ các dòng có vị trí dọc ổn định giữa các trang.
    positions = [member["bbox"]["top"] / heights[member["page_number"]] for member in members]
    middle = median(positions)
    return [m for m, p in zip(members, positions) if abs(p - middle) <= TOP_STABILITY_RATIO]


def mask_lines(group, reason, min_pages, heights):
    stable = stable_members(group, heights)
    if len({line["page_number"] for line in stable}) >= min_pages:
        for line in stable:
            line["masked"] = True
            line["mask_reason"] = reason


def mask_layout_lines(lines, pages, edge_zone_ratio=EDGE_ZONE_RATIO):
    heights = {page["page_number"]: page.get("height") for page in pages}
    page_count = len(pages)

    # Quy tắc A: dòng chỉ chứa số trang, nằm ở mép trang.
    for line in lines:
        text = recognition_text(line["text"])
        if in_edge_zone(line, heights[line["page_number"]], edge_zone_ratio) and PAGE_NUMBER.fullmatch(text):
            line["masked"] = True
            line["mask_reason"] = "PAGE_NUMBER"

    candidates = {}
    for line in lines:
        text = recognition_text(line["text"])
        zone = in_edge_zone(line, heights[line["page_number"]], edge_zone_ratio)
        if line["masked"] or not zone or not text or not looks_like_layout(text):
            continue
        if page_count == 2:
            # Ngoại lệ P = 2: hậu tố "Trang k / 2" khớp đúng số trang, phần chữ trước giống hệt nhau.
            match = PAGE_SUFFIX.match(text)
            if (match and match["prefix"] and same_number(match["page"], line["page_number"])
                    and same_number(match["total"], page_count)):
                candidates.setdefault((zone, match["prefix"]), []).append(line)
        elif page_count >= 3:
            pattern = TRAILING_PAGE_NUMBER.sub("", text)
            if pattern:
                candidates.setdefault((zone, pattern), []).append(line)

    min_pages = 2 if page_count == 2 else max(3, math.ceil(0.65 * page_count))
    for (zone, _), group in candidates.items():
        mask_lines(group, "REPEATED_HEADER" if zone == "TOP" else "REPEATED_FOOTER", min_pages, heights)
    return lines


def clean_layout(pages, source_type, enable_layout_cleaning=True, edge_zone_ratio=EDGE_ZONE_RATIO) -> dict:
    lines, normalized_text, geometry_mismatch = build_lines(pages)
    if enable_layout_cleaning:
        mask_layout_lines(lines, pages, edge_zone_ratio)

    lines_by_page = {}
    for line in lines:
        lines_by_page.setdefault(line["page_number"], []).append(line)
    page_warnings = []
    for page in pages:
        warnings = list(page.get("warnings", []))
        if page["page_number"] in geometry_mismatch and "LINE_GEOMETRY_UNAVAILABLE" not in warnings:
            warnings.append("LINE_GEOMETRY_UNAVAILABLE")
        warnings += page_quality_warnings(page["text"], page.get("image_coverage", 0.0), source_type)
        page_lines = lines_by_page.get(page["page_number"], [])
        if any(line["bbox"] is None and PAGE_NUMBER.fullmatch(recognition_text(line["text"])) for line in page_lines):
            warnings.append("LAYOUT_CANDIDATE")
        page_warnings.append({"page_number": page["page_number"], "warnings": warnings})

    return {
        "source_type": source_type,
        "page_count": len(pages),
        "normalized_text": normalized_text,
        "lines": lines,
        "page_warnings": page_warnings,
    }
