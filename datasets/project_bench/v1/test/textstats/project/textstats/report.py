"""Per-document statistics and the CSV report."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from textstats import config
from textstats.corpus import Document, fingerprint, iter_documents
from textstats.counts import count_ngrams, count_words, drop_rare, top_n
from textstats.readability import (
    average_word_length,
    flesch_kincaid_grade,
    flesch_reading_ease,
    lexical_diversity,
)
from textstats.tokenizer import remove_stopwords, split_sentences, tokenize

REPORT_COLUMNS: tuple[str, ...] = (
    "document",
    "words",
    "unique_words",
    "sentences",
    "average_word_length",
    "lexical_diversity",
    "reading_ease",
    "grade_level",
    "top_words",
    "top_ngrams",
)


@dataclass(frozen=True)
class DocumentStats:
    """One row of the report; the fields match REPORT_COLUMNS."""

    document: str
    words: int
    unique_words: int
    sentences: int
    average_word_length: float
    lexical_diversity: float
    reading_ease: float
    grade_level: float
    top_words: str
    top_ngrams: str


def _format_top(pairs: Iterable[tuple[str, int]]) -> str:
    """Format (item, count) pairs as ``item:count`` joined by '; '."""
    return "; ".join(f"{item}:{count}" for item, count in pairs)


def analyze_document(
    document: Document, settings: config.Settings | None = None
) -> DocumentStats:
    """Compute the report row for ``document``.

    Word counts, word length and diversity use every word. The top words and
    n-grams leave out stopwords and anything seen fewer than ``min_count`` times.
    """
    settings = settings or config.Settings()
    tokens = tokenize(document.text, settings.lowercase, settings.min_word_length)
    content = remove_stopwords(tokens, settings.stopwords)
    word_counts = drop_rare(count_words(content), settings.min_count)
    ngram_counts = drop_rare(count_ngrams(content, settings.ngram_size), settings.min_count)
    return DocumentStats(
        document=document.name,
        words=len(tokens),
        unique_words=len(set(tokens)),
        sentences=len(split_sentences(document.text)),
        average_word_length=average_word_length(tokens),
        lexical_diversity=lexical_diversity(tokens),
        reading_ease=flesch_reading_ease(document.text),
        grade_level=flesch_kincaid_grade(document.text),
        top_words=_format_top(top_n(word_counts, settings.top_words)),
        top_ngrams=_format_top(top_n(ngram_counts, settings.top_words)),
    )


def analyze_corpus(
    documents: Iterable[Document], settings: config.Settings | None = None
) -> list[DocumentStats]:
    """Analyze the documents in order.

    A document whose text repeats an earlier one, ignoring case and spacing, is
    skipped so that copies do not weigh twice in the report.
    """
    seen: set[str] = set()
    rows: list[DocumentStats] = []
    for document in documents:
        key = fingerprint(document.text)
        if key in seen:
            continue
        seen.add(key)
        rows.append(analyze_document(document, settings))
    return rows


def write_report(
    rows: Sequence[DocumentStats], path: Path, columns: Sequence[str] = REPORT_COLUMNS
) -> None:
    """Write ``rows`` to ``path`` as UTF-8 CSV with a header, keeping ``columns`` only."""
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def build_report(corpus_root: Path, output: Path, settings_path: Path | None = None) -> int:
    """Analyze every document under ``corpus_root`` and write the CSV to ``output``.

    Settings come from ``settings_path`` when given, otherwise the defaults are used.
    Returns the number of rows written.
    """
    settings = config.load_settings(settings_path) if settings_path else config.Settings()
    rows = analyze_corpus(iter_documents(corpus_root, settings.suffixes), settings)
    write_report(rows, output, settings.columns)
    return len(rows)
