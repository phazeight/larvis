# tests/test_indexer.py
from larvis import indexer
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


def test_clean_for_index_strips_code_blocks_and_comments():
    raw = (
        "## Daily Record\n"
        "%%Your Record%%\n"
        "- [ ] test larvis working well for $600 dollars alex!\n"
        "## Energy allocation\n"
        "```PeriodicPARA\nProjectListByTime\n```\n"
        "```dataview\nLIST FROM \"1. Projects\"\n```\n"
    )
    out = indexer._clean_for_index(raw)
    assert "$600 dollars alex" in out          # real content kept
    assert "PeriodicPARA" not in out           # query block dropped
    assert "ProjectListByTime" not in out
    assert "dataview" not in out
    assert "%%" not in out and "Your Record" not in out  # obsidian comment dropped


def test_clean_for_index_empty_when_only_boilerplate():
    raw = "%%note%%\n```PeriodicPARA\nTaskListByTag\n```\n"
    assert indexer._clean_for_index(raw).strip() == ""
