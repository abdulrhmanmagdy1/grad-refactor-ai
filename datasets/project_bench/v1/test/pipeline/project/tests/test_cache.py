from pipeline.cache import DiskCache, file_fingerprint, make_key


def test_round_trip(tmp_path):
    cache = DiskCache(tmp_path / "cache")
    assert cache.get("sales-1") is None
    cache.put("sales-1", {"total": 3.5, "groups": ["a", "b"]})
    assert cache.get("sales-1") == {"total": 3.5, "groups": ["a", "b"]}
    cache.put("sales-1", {"total": 4})
    assert cache.get("sales-1") == {"total": 4}


def test_unreadable_entry_is_a_miss(tmp_path):
    cache = DiskCache(tmp_path)
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    assert cache.get("broken") is None


def test_clear(tmp_path):
    cache = DiskCache(tmp_path / "cache")
    cache.put("a", 1)
    cache.put("b", 2)
    assert cache.clear() == 2
    assert cache.get("a") is None


def test_fingerprint(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("a,b\n1,2\n", encoding="utf-8")
    first = file_fingerprint(path)
    assert first == file_fingerprint(path)
    path.write_text("a,b\n1,3\n", encoding="utf-8")
    assert file_fingerprint(path) != first


def test_make_key_depends_on_settings():
    assert make_key("sales", "x", "y") == make_key("sales", "x", "y")
    assert make_key("sales", "x", "y") != make_key("sales", "x", "z")
    assert make_key("sales", "x", "y") != make_key("sales", "xy")
    assert make_key("sales", "x").startswith("sales-")
