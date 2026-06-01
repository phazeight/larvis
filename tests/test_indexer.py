# tests/test_indexer.py
from larvis.indexer import chunk_text


def test_chunk_text_returns_single_chunk_for_short_text():
    chunks = chunk_text("hello world this is a short note", size=500, overlap=50)
    assert len(chunks) == 1
    assert "hello world" in chunks[0]


def test_chunk_text_splits_text_larger_than_chunk_size():
    # In cl100k_base "word" and " word" are each 1 token, so 600 words → 600 tokens
    text = " ".join(["word"] * 600)
    chunks = chunk_text(text, size=500, overlap=50)
    assert len(chunks) == 2


def test_chunk_text_overlap_produces_shorter_second_chunk():
    text = " ".join(["word"] * 600)
    chunks = chunk_text(text, size=500, overlap=50)
    # First chunk is full (500 tokens); second chunk is the remainder
    assert len(chunks[0]) > len(chunks[1])
