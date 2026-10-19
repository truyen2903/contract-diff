from app.engines.text_diff import diff_words

def compare_text(old_text: str, new_text: str):
    changes = diff_words(old_text, new_text)

    return {
        "is_identical": old_text == new_text,
        "old_length": len(old_text),
        "new_length": len(new_text),
        "changes": changes,
    }