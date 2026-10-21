from textstats.corpus import Document, iter_documents, load_index, read_text


def test_iter_documents_walks_subfolders_in_order(tmp_path):
    (tmp_path / "b.txt").write_text("Second.", encoding="utf-8")
    (tmp_path / "a.txt").write_text("First.", encoding="utf-8")
    (tmp_path / "notes.md").write_text("Not a text file.", encoding="utf-8")
    (tmp_path / ".draft.txt").write_text("Hidden.", encoding="utf-8")
    (tmp_path / "empty.txt").write_text("   \n", encoding="utf-8")
    (tmp_path / "letters").mkdir()
    (tmp_path / "letters" / "c.txt").write_text("Third.", encoding="utf-8")
    names = [document.name for document in iter_documents(tmp_path)]
    assert names == ["a.txt", "b.txt", "letters/c.txt"]


def test_read_text_falls_back_to_windows_1252(tmp_path):
    path = tmp_path / "old.txt"
    path.write_bytes("caf\N{LATIN SMALL LETTER E WITH ACUTE}".encode("cp1252"))
    assert read_text(path) == "caf\N{LATIN SMALL LETTER E WITH ACUTE}"


def test_load_index(tmp_path):
    (tmp_path / "letters").mkdir()
    (tmp_path / "letters" / "one.txt").write_text("Dear Anna.", encoding="utf-8")
    (tmp_path / "two.txt").write_text("Dear Ben.", encoding="utf-8")
    (tmp_path / "index.txt").write_text("# letters\nletters/one.txt\n\ntwo.txt\n", encoding="utf-8")
    assert load_index(tmp_path) == [
        Document(name="letters/one.txt", text="Dear Anna."),
        Document(name="two.txt", text="Dear Ben."),
    ]
