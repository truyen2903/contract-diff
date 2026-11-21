"""Prespecified flat baselines. Block IDs refer to their segmentation, not parser IDs."""

from app.engines.clause_aligner import align_documents
from app.engines.assignment import solve_assignment
from app.engines.similarity import fit_lexical, lexical_similarity
from app.engines.text_diff import diff_words


def whole_text(old, new):
    return diff_words(old, new)


def flat_alignment(old, new, segmentation, config=None):
    if segmentation not in ("paragraph", "line"):
        raise ValueError("unknown flat segmentation")

    def blocks(text):
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        parts = normalized.split("\n\n") if segmentation == "paragraph" else normalized.splitlines()
        return [{"node_id": f"block{i}", "node_type": "PARAGRAPH", "own_text": part,
                 "number_label": None, "section_context": None, "parent_id": None, "title": None, "children": []}
                for i, part in enumerate(parts) if part.strip()]
    return align_documents(blocks(old), blocks(new), config)


def _node_text(node):
    return node.get("own_text", "") if isinstance(node, dict) else str(node)


def similarity_matrix(old, new):
    vectors = fit_lexical([*(_node_text(node) for node in old), *(_node_text(node) for node in new)])
    old_vectors, new_vectors = vectors[:len(old)], vectors[len(old):]
    return [[lexical_similarity(left, right) for right in new_vectors] for left in old_vectors]


def greedy_alignment(old, new, threshold=.4):
    matrix = similarity_matrix(old, new)
    candidates = sorted((score, i, j) for i, row in enumerate(matrix)
                        for j, score in enumerate(row) if score >= threshold)
    used_old, used_new, result = set(), set(), []
    for score, i, j in sorted(candidates, key=lambda item: (-item[0], item[1], item[2])):
        if i not in used_old and j not in used_new:
            used_old.add(i)
            used_new.add(j)
            result.append((i, j, score))
    return sorted(result)


def flat_hungarian_alignment(old, new, threshold=.4):
    matrix = similarity_matrix(old, new)
    pairs = solve_assignment(matrix, threshold=threshold)
    return [(i, j, matrix[i][j]) for i, j in pairs]


def monotonic_alignment(old, new, threshold=.4):
    matrix = similarity_matrix(old, new)
    columns = len(new)
    empty = (0., 0, ())
    table = [[empty for _ in range(columns + 1)] for _ in range(len(old) + 1)]
    for i in range(1, len(old) + 1):
        for j in range(1, columns + 1):
            choices = [table[i - 1][j], table[i][j - 1]]
            score = matrix[i - 1][j - 1]
            if score >= threshold:
                previous = table[i - 1][j - 1]
                choices.append((previous[0] + score, previous[1] + 1,
                                previous[2] + ((-(i - 1), -(j - 1)),)))
            table[i][j] = max(choices)
    pairs = table[-1][-1][2]
    return [(-i, -j, matrix[-i][-j]) for i, j in pairs]
