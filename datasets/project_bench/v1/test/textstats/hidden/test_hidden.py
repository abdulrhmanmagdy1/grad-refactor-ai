"""Hidden tests for the textstats benchmark project."""

import pytest

from textstats.corpus import Document, fingerprint, load_document
from textstats.counts import drop_rare, ngrams, top_n
from textstats.readability import flesch_kincaid_grade, flesch_reading_ease
from textstats.report import analyze_corpus
from textstats.tokenizer import remove_stopwords


def test_B1_remove_stopwords_drops_adjacent_stopwords():
    tokens = ["It", "is", "a", "test", "of", "the", "system"]
    assert remove_stopwords(tokens, {"it", "is", "a", "of", "the"}) == ["test", "system"]


def test_B2_ngrams_include_the_last_window():
    assert ngrams(["to", "be", "or", "not"], 2) == [("to", "be"), ("be", "or"), ("or", "not")]
    assert ngrams(["just", "one"], 2) == [("just", "one")]
    assert ngrams(["a", "b", "c"], 1) == [("a",), ("b",), ("c",)]


def test_B3_top_n_lists_equal_counts_alphabetically():
    counts = {"pear": 2, "apple": 2, "fig": 5, "kiwi": 1, "banana": 2}
    assert top_n(counts, 4) == [("fig", 5), ("apple", 2), ("banana", 2), ("pear", 2)]


def test_S1_load_document_stays_inside_the_corpus(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.txt").write_text("public text", encoding="utf-8")
    (tmp_path / "private.txt").write_text("salary figures", encoding="utf-8")
    try:
        document = load_document(corpus, "../private.txt")
    except (ValueError, OSError):
        return
    assert "salary" not in document.text


def test_keep_load_document_reads_subfolders(tmp_path):
    (tmp_path / "letters").mkdir()
    (tmp_path / "letters" / "1854.txt").write_text("Dear Anna.", encoding="utf-8")
    document = load_document(tmp_path, "letters/1854.txt")
    assert document == Document(name="letters/1854.txt", text="Dear Anna.")


def test_keep_remove_stopwords_keeps_the_other_words_in_order():
    assert remove_stopwords(["Cats", "and", "dogs", "and", "birds"], {"and"}) == [
        "Cats",
        "dogs",
        "birds",
    ]
    assert remove_stopwords([], {"the"}) == []


def test_keep_ngrams_of_a_short_text_are_empty():
    assert ngrams(["alone"], 2) == []
    assert ngrams([], 1) == []


def test_keep_top_n_puts_the_highest_count_first():
    assert top_n({"a": 1, "b": 3, "c": 2}, 5) == [("b", 3), ("c", 2), ("a", 1)]
    assert top_n({"a": 1}, 0) == []


def test_keep_drop_rare_deletes_every_rare_entry():
    counts = {"a": 1, "b": 1, "c": 3, "d": 1, "e": 2}
    assert drop_rare(counts, 2) == {"c": 3, "e": 2}
    assert counts == {"c": 3, "e": 2}


def test_keep_fingerprint_ignores_case_and_spacing():
    assert fingerprint("Hello  there.\nBye.") == fingerprint("hello there. BYE.")
    assert fingerprint("Hello there.") != fingerprint("Hello where.")


def test_keep_analyze_corpus_skips_repeated_documents():
    documents = [
        Document("a.txt", "Hello there. Bye."),
        Document("b.txt", "hello   THERE.\nbye."),
        Document("c.txt", "Something else."),
    ]
    assert [row.document for row in analyze_corpus(documents)] == ["a.txt", "c.txt"]


def test_keep_readability_scores():
    text = "The cat sat. The dog ran."
    assert flesch_reading_ease(text) == pytest.approx(119.2)
    assert flesch_kincaid_grade(text) == pytest.approx(-2.6)
    assert flesch_kincaid_grade("") == 0.0
