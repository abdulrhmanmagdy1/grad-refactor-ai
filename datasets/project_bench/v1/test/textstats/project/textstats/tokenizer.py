"""Splitting text into words and sentences."""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable

WORD_PATTERN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
SENTENCE_END = re.compile(r"[.!?]+")
VOWEL_RUN = re.compile(r"[aeiouy]+")


def tokenize(text: str, lowercase: bool = True, min_length: int = 1) -> list[str]:
    """Return the words of ``text`` in order.

    A word is a run of ASCII letters, optionally with one apostrophe inside
    ("don't"). Words shorter than ``min_length`` characters are left out.
    """
    words = WORD_PATTERN.findall(text)
    if lowercase:
        words = [word.lower() for word in words]
    return [word for word in words if len(word) >= min_length]


def split_sentences(text: str) -> list[str]:
    """Split ``text`` into sentences ending in '.', '!' or '?'.

    Text after the last end mark counts as a sentence too; empty pieces are dropped.
    """
    pieces = SENTENCE_END.split(text)
    return [piece.strip() for piece in pieces if piece.strip()]


def count_syllables(word: str) -> int:
    """Estimate the number of syllables in ``word``.

    Each run of vowels (a, e, i, o, u, y) is one syllable. A final 'e' is silent
    ("make") unless it follows an 'l' ("table"), and every word has at least one
    syllable.
    """
    word = word.lower()
    count = len(VOWEL_RUN.findall(word))
    if word.endswith("e") and not word.endswith("le") and count > 1:
        count -= 1
    return max(count, 1)


def remove_stopwords(tokens: Iterable[str], stopwords: Collection[str]) -> list[str]:
    """Return a new list of ``tokens`` without the stopwords, in the original order.

    ``stopwords`` holds lowercase words; tokens are compared ignoring case.
    """
    kept = list(tokens)
    for token in kept:
        if token.lower() in stopwords:
            kept.remove(token)
    return kept
