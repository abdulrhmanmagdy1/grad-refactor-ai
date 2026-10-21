import csv

from textstats.corpus import Document
from textstats.readability import average_word_length, flesch_reading_ease, lexical_diversity
from textstats.report import analyze_document, build_report


def test_analyze_document_counts():
    row = analyze_document(Document("a.txt", "The cat sat. The dog ran!"))
    assert row.document == "a.txt"
    assert row.words == 6
    assert row.unique_words == 5
    assert row.sentences == 2


def test_readability_of_empty_text():
    assert flesch_reading_ease("") == 0.0
    assert average_word_length([]) == 0.0
    assert lexical_diversity([]) == 0.0


def test_build_report_writes_the_chosen_columns(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "a.txt").write_text("The cat sat. The dog ran!", encoding="utf-8")
    settings = tmp_path / "settings.ini"
    settings.write_text("[textstats]\ncolumns = document, words, sentences\n", encoding="utf-8")
    output = tmp_path / "report.csv"
    assert build_report(corpus, output, settings) == 1
    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows == [{"document": "a.txt", "words": "6", "sentences": "2"}]
