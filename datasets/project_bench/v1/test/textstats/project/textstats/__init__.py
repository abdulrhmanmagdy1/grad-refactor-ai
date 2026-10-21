"""Word statistics and readability scores for a folder of text documents."""

from textstats.config import Settings, load_settings
from textstats.corpus import Document, iter_documents, load_document, load_index
from textstats.report import DocumentStats, analyze_corpus, build_report, write_report

__all__ = [
    "Document",
    "DocumentStats",
    "Settings",
    "analyze_corpus",
    "build_report",
    "iter_documents",
    "load_document",
    "load_index",
    "load_settings",
    "write_report",
]
