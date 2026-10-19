"""Shared input limit for text sent to the embedding model."""

# The configured nomic model accepts 2048 tokens. This conservative UTF-8
# byte limit leaves room for tokenizers that split words into several tokens.
MAX_EMBEDDING_INPUT_BYTES = 1500


def split_text_by_bytes(text: str, max_bytes: int = MAX_EMBEDDING_INPUT_BYTES) -> list[str]:
    """Split text without discarding characters or splitting UTF-8 code points."""
    if max_bytes < 4:
        raise ValueError("max_bytes deve ser maior ou igual a 4.")
    if len(text.encode("utf-8")) <= max_bytes:
        return [text]

    parts: list[str] = []
    current: list[str] = []
    size = 0
    for character in text:
        character_size = len(character.encode("utf-8"))
        if size + character_size > max_bytes:
            parts.append("".join(current))
            current = []
            size = 0
        current.append(character)
        size += character_size
    if current:
        parts.append("".join(current))
    return parts
