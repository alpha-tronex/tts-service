"""Text preparation for speech. Pure functions, no model imports."""
import re
import unicodedata

MAX_TEXT_CHARS = 1000
# Both models read short inputs best, and SpeechT5 has a hard input limit, so
# long text is spoken one chunk at a time and the audio is joined afterwards.
MAX_CHUNK_CHARS = 180

_SENTENCE_END = re.compile(r"(?<=[.!?…;:])\s+")
_SPACE = re.compile(r"\s+")


def clean(text: str) -> str:
    """Normalises Unicode and whitespace; never changes the words."""
    return _SPACE.sub(" ", unicodedata.normalize("NFC", text)).strip()


def _split_long(sentence: str, limit: int) -> list[str]:
    """Breaks an over-long sentence at commas, then at spaces."""
    if len(sentence) <= limit:
        return [sentence]
    parts: list[str] = []
    current = ""
    for word in sentence.split(" "):
        candidate = f"{current} {word}".strip()
        if len(candidate) > limit and current:
            parts.append(current)
            current = word
        else:
            current = candidate
        # Prefer to break after a comma once the chunk is reasonably full.
        if current.endswith(",") and len(current) >= limit * 0.6:
            parts.append(current)
            current = ""
    if current:
        parts.append(current)
    # A single "word" longer than the limit (no spaces) is cut hard.
    return [p[i : i + limit] for p in parts for i in range(0, len(p), limit)]


def split_for_speech(text: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Sentences, each at most `limit` characters, in order."""
    cleaned = clean(text)
    if not cleaned:
        return []
    chunks: list[str] = []
    for sentence in _SENTENCE_END.split(cleaned):
        if sentence:
            chunks.extend(_split_long(sentence, limit))
    return chunks
