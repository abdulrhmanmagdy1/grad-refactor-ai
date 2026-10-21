import pytest

from textstats.counts import count_ngrams, count_words, drop_rare, ngrams, top_n


def test_count_words():
    assert count_words(["a", "b", "a"]) == {"a": 2, "b": 1}


def test_count_words_of_nothing():
    assert count_words([]) == {}


def test_ngrams_of_a_short_text_are_empty():
    assert ngrams(["only"], 2) == []
    assert count_ngrams([], 3) == {}


def test_ngrams_need_a_positive_size():
    with pytest.raises(ValueError):
        ngrams(["a", "b"], 0)


def test_top_n_puts_the_highest_count_first():
    assert top_n({"a": 1, "b": 3, "c": 2}, 2) == [("b", 3), ("c", 2)]


def test_drop_rare():
    counts = {"x": 1, "y": 4}
    assert drop_rare(counts, 2) is counts
    assert counts == {"y": 4}
