import json

import pytest

from textstats.config import Settings, load_settings


def test_ini_settings(tmp_path):
    path = tmp_path / "settings.ini"
    path.write_text(
        "[textstats]\n"
        "lowercase = no\n"
        "ngram_size = 3\n"
        "stopwords = The, a\n"
        "columns = document, words\n",
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.lowercase is False
    assert settings.ngram_size == 3
    assert settings.stopwords == frozenset({"the", "a"})
    assert settings.columns == ("document", "words")
    assert settings.top_words == Settings().top_words


def test_json_settings(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"top_words": 3, "suffixes": [".TXT", ".md"]}), encoding="utf-8")
    settings = load_settings(path)
    assert settings.top_words == 3
    assert settings.suffixes == (".txt", ".md")


@pytest.mark.parametrize(
    "content",
    [
        {"columns": ["document", "colour"]},
        {"top_words": 0},
        {"lowercase": "maybe"},
        {"verbose": True},
    ],
)
def test_bad_json_settings_are_rejected(tmp_path, content):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(path)


def test_ini_without_the_section(tmp_path):
    path = tmp_path / "settings.ini"
    path.write_text("[other]\nlowercase = yes\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(path)


def test_unsupported_file_type(tmp_path):
    path = tmp_path / "settings.yaml"
    path.write_text("lowercase: true\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_settings(path)
