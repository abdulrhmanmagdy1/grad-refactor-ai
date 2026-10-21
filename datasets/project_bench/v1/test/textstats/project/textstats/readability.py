"""Readability scores for English text."""

from __future__ import annotations

from collections.abc import Sequence

from textstats.tokenizer import count_syllables, split_sentences, tokenize


def flesch_reading_ease(text: str) -> float:
    """Flesch reading ease of ``text``, rounded to one decimal; higher is easier.

    206.835 - 1.015 * (words per sentence) - 84.6 * (syllables per word).
    Text without words scores 0.0.
    """
    sentences = split_sentences(text)
    words = tokenize(text)
    if not sentences or not words:
        return 0.0
    syllables = sum(count_syllables(word) for word in words)
    words_per_sentence = len(words) / len(sentences)
    syllables_per_word = syllables / len(words)
    score = 206.835 - 1.015 * words_per_sentence - 84.6 * syllables_per_word
    return round(score, 1)


def flesch_kincaid_grade(text: str) -> float:
    """Flesch-Kincaid grade level of ``text``, rounded to one decimal.

    0.39 * (words per sentence) + 11.8 * (syllables per word) - 15.59.
    Text without words scores 0.0.
    """
    sentences = split_sentences(text)
    words = tokenize(text)
    if not sentences or not words:
        return 0.0
    syllables = sum(count_syllables(word) for word in words)
    words_per_sentence = len(words) / len(sentences)
    syllables_per_word = syllables / len(words)
    grade = 0.39 * words_per_sentence + 11.8 * syllables_per_word - 15.59
    return round(grade, 1)


def lexical_diversity(tokens: Sequence[str]) -> float:
    """Distinct tokens divided by all tokens, rounded to three decimals; 0.0 if empty."""
    if not tokens:
        return 0.0
    return round(len(set(tokens)) / len(tokens), 3)


def average_word_length(tokens: Sequence[str]) -> float:
    """Mean number of characters per token, rounded to two decimals; 0.0 if empty."""
    if not tokens:
        return 0.0
    return round(sum(len(token) for token in tokens) / len(tokens), 2)
