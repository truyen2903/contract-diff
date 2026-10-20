from app.engines.text_diff import diff_words
from app.services.document_service import extract_document

def compare_text(old_text: str, new_text: str):
    changes = diff_words(old_text, new_text)

    return {
        "is_identical": old_text == new_text,
        "old_length": len(old_text),
        "new_length": len(new_text),
        "changes": changes,
    }

def compare_document(old_filename, old_file_stream,new_filename, new_file_stream):
    old_document = extract_document(old_filename, old_file_stream)
    new_document = extract_document(new_filename, new_file_stream)
    
    old_text = "\n\n".join(page["text"] for page in old_document["pages"])
    new_text = "\n\n".join(page["text"] for page in new_document["pages"])
    
    needs_review = any(
    page["warnings"]
    for page in old_document["pages"] + new_document["pages"]
)
    
    changes = diff_words(old_text,new_text)
    
    return {
        "old_document":old_document,
        "new_document":new_document,
        "changes":changes,
        "needs_review": needs_review,
    }