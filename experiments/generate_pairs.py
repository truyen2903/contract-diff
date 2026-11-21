"""Controlled edit operation with independent, stable IDs for engineering verification."""


def engineering_example():
    bodies = {"long": "Quy định giao nhận hàng hóa tại địa điểm do hai bên thống nhất.",
              "a": "Phí dịch vụ.", "b": "Bảo hành."}

    def render(order):
        nodes, lines = [], []
        offset = 0
        for i, key in enumerate(order, 1):
            label, body = f"Điều {i}", bodies[key]
            text = f"{label}: {body}"
            nodes.append({"node_id": key, "node_type": "ARTICLE", "parent_id": None, "children": [],
                          "section_context": None, "number_label": label, "title": body, "own_text": text,
                          "body": body, "clean_ranges": [[offset, offset + len(text)]]})
            lines.append(text)
            offset += len(text) + 1
        return nodes, "\n".join(lines)

    old_nodes, old_text = render(["long", "a", "b"])
    new_nodes, new_text = render(["a", "b", "long"])
    return {"usage": "ENGINEERING_ONLY", "old_nodes": old_nodes, "old_text": old_text,
            "new_nodes": new_nodes, "new_text": new_text, "edges": [(k, k) for k in bodies],
            "edit_moves": [("long", "long")]}
