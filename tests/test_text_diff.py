import re
from app.engines.text_diff import diff_words

def tokenize_with_spans(text):
    result =[]
    for match in re.finditer(r"\S+", text):
        result.append({
            "text":match.group(),
            "start": match.start(),
            "end":match.end()
        })
    return result
