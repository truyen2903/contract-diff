from difflib import SequenceMatcher
import re

def tokenize_with_spans(text):
    result =[]
    for match in re.finditer(r"\S+", text):
        result.append({
            "text":match.group(),
            "start": match.start(),
            "end":match.end()
        })
    return result

def diff_words(old_text: str, new_text: str) -> list[dict]: 
    old_tokens = tokenize_with_spans(old_text)
    new_tokens = tokenize_with_spans(new_text)
    old = [token["text"] for token in old_tokens]
    new = [token["text"] for token in new_tokens]
    changes = []
    matcher  = SequenceMatcher(
        a= old,
        b= new,
        autojunk=False
    )

    for tag,i1,i2,j1,j2 in matcher.get_opcodes():
        if tag == "equal":
            continue    
        old_span = None
        new_span = None
        if i1 < i2:
            old_span = {
                "start": old_tokens[i1]["start"],
                "end": old_tokens[i2 - 1]["end"],
            }
        if j1 < j2:
            new_span = {
                "start": new_tokens[j1]["start"],
                "end": new_tokens[j2 - 1]["end"],
            }
        old_fragment = ""
        new_fragment = ""
        if old_span is not None:
            old_fragment = old_text[old_span["start"]:old_span["end"]]
        if new_span is not None:
            new_fragment = new_text[new_span["start"]:new_span["end"]]
    changes.append({
        "type": tag,
        "old_text": old_fragment,
        "new_text": new_fragment,
        "old_span": old_span,
        "new_span": new_span,
    })
    return changes