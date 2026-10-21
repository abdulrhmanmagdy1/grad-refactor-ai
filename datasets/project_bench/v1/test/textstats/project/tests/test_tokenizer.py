from textstats.tokenizer import count_syllables, remove_stopwords, split_sentences, tokenize


def test_tokenize_lowercases_and_keeps_inner_apostrophes():
    assert tokenize("Don't PANIC, it's fine.") == ["don't", "panic", "it's", "fine"]


def test_tokenize_can_keep_case_and_drop_short_words():
    assert tokenize("A cat sat on It", lowercase=False, min_length=3) == ["cat", "sat"]


def test_split_sentences_keeps_text_after_the_last_mark():
    assert split_sentences("One. Two!! Three? Four") == ["One", "Two", "Three", "Four"]


def test_split_sentences_of_blank_text():
    assert split_sentences("   ") == []


def test_count_syllables():
    assert count_syllables("make") == 1
    assert count_syllables("table") == 2
    assert count_syllables("banana") == 3
    assert count_syllables("rhythm") == 1
    assert count_syllables("the") == 1


def test_remove_stopwords_ignores_case():
    tokens = ["The", "cat", "sat", "on", "mat"]
    assert remove_stopwords(tokens, {"the", "on"}) == ["cat", "sat", "mat"]
    assert tokens == ["The", "cat", "sat", "on", "mat"]
