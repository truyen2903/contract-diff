"""Đặc trưng thuần Python, fit chung hai phía của cùng tầng đối sánh."""

import math
import re
import unicodedata
from collections import Counter


def content_key(text):
    return " ".join(unicodedata.normalize("NFC", text).split())


def body_start(text, label):
    if not label:
        return 0, None
    line = text.partition("\n")[0]
    # B1 ignores BOM for recognition. Retain its original index in own_text.
    indices = [i for i, char in enumerate(line) if char != "\ufeff"]
    visible = "".join(line[i] for i in indices)
    pattern = r"^\s*" + r"\s+".join(re.escape(word) for word in label.split())
    match = re.match(pattern + r"(?![\w]|\.\d)\s*(?:[.):–—-]\s*)?", visible)
    if not match or not match.end():
        return 0, "LABEL_NOT_AT_START"
    end = match.end()
    return (indices[end] if end < len(indices) else len(line)), None


def unique_anchors(old_keys, new_keys):
    counts = Counter(old_keys)
    other = Counter(new_keys)
    positions = {key: j for j, key in enumerate(new_keys)}
    def key_length(key):
        return len(" ".join(key).strip()) if isinstance(key, tuple) else len(key)
    return [(i, positions[key]) for i, key in enumerate(old_keys)
            if key_length(key) >= 20 and counts[key] == other[key] == 1]


def word_features(text):
    words = re.findall(r"\w+", text)
    counts = Counter(words)
    counts.update(zip(words, words[1:]))
    return counts


def char_features(text):
    counts = Counter()
    for word in text.split():
        padded = " " + word + " "
        for size in (3, 4):
            for start in range(max(1, len(padded) - size + 1)):
                counts[padded[start:start + size]] += 1
            if len(padded) <= size:
                break
    return counts


def tfidf(texts, features):
    counts = [features(text) for text in texts]
    frequencies = Counter()
    for row in counts:
        frequencies.update(row.keys())
    idf = {term: 1 + math.log((1 + len(texts)) / (1 + count))
           for term, count in frequencies.items()}
    vectors = []
    for row in counts:
        weights = {term: count * idf[term] for term, count in row.items()}
        norm = math.sqrt(math.fsum(value * value for value in weights.values()))
        vectors.append({term: value / norm for term, value in weights.items()})
    return vectors


def fit_lexical(texts):
    keys = [content_key(text).lower() for text in texts]
    return list(zip(keys, tfidf(keys, word_features), tfidf(keys, char_features)))


def cosine(left, right):
    if len(left) > len(right):
        left, right = right, left
    return min(1.0, math.fsum(value * right.get(term, 0) for term, value in left.items()))


def lexical_similarity(left, right):
    if left[0] == right[0]:
        return 1.0
    return .60 * cosine(left[1], right[1]) + .40 * cosine(left[2], right[2])


def title_similarity(left, right, one_sided="omit"):
    left, right = (content_key(value or "").lower() for value in (left, right))
    if not left or not right:
        return {"omit": None, "half": .5, "zero": 0.0}[one_sided] if left or right else None
    if left == right:
        return 1.0
    words, others = set(left.split()), set(right.split())
    jaccard = len(words & others) / len(words | others)
    if len(left) > len(right):
        left, right = right, left
    previous = list(range(len(left) + 1))
    for i, char in enumerate(right, 1):
        row = [i]
        for j, other in enumerate(left, 1):
            row.append(min(previous[j] + 1, row[-1] + 1, previous[j - 1] + (char != other)))
        previous = row
    return .5 * jaccard + .5 * (1 - previous[-1] / len(right))


def position_similarity(i, m, j, n):
    return 1 - abs(i / max(m - 1, 1) - j / max(n - 1, 1))


def combine_scores(lexical, title, position):
    if title is None and position is None:
        return lexical
    terms = [(.65, lexical)]
    if title is not None:
        terms.append((.25, title))
    if position is not None:
        terms.append((.10, position))
    return math.fsum(w * score for w, score in terms) / math.fsum(w for w, _ in terms)
