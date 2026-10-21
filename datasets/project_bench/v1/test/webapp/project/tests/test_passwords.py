from webapp.passwords import hash_password, needs_rehash, verify_password


def test_round_trip():
    encoded = hash_password("correct horse battery", iterations=1_000)
    assert verify_password("correct horse battery", encoded)
    assert not verify_password("correct horse batterY", encoded)


def test_same_password_gets_different_salts():
    first = hash_password("same password", iterations=1_000)
    second = hash_password("same password", iterations=1_000)
    assert first != second


def test_malformed_hashes_never_verify():
    assert not verify_password("anything", "")
    assert not verify_password("anything", "md5$1$00$00")
    assert not verify_password("anything", "pbkdf2_sha256$x$zz$zz")


def test_needs_rehash_when_iterations_grow():
    encoded = hash_password("some password", iterations=1_000)
    assert not needs_rehash(encoded, iterations=1_000)
    assert needs_rehash(encoded, iterations=2_000)
    assert needs_rehash("garbage", iterations=1_000)
