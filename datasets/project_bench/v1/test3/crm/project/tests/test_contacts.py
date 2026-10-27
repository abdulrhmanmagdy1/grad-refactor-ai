from crm.contacts import ContactBook, email_domain, normalize_email


def test_normalize_strips_whitespace() -> None:
    assert normalize_email("  bob@shop.io \n") == "bob@shop.io"


def test_email_domain() -> None:
    assert email_domain("ann@Example.COM") == "example.com"
    assert email_domain("no-at-sign") == ""


def test_same_email_returns_existing_contact_and_merges_tags() -> None:
    book = ContactBook()
    first = book.add_contact("Bob Stone", "bob@shop.io", tags=["vip"])
    again = book.add_contact("Robert Stone", " bob@shop.io ", tags=["vip", "trade-fair"])
    assert again is first
    assert first.tags == ["vip", "trade-fair"]
    assert len(book.contacts) == 1


def test_contact_linked_to_company_by_domain() -> None:
    book = ContactBook()
    acme = book.add_company("Acme", "acme.com")
    contact = book.add_contact("Dana Fox", "dana@acme.com", tags=["lead"])
    assert contact.company_id == acme.company_id
    assert book.company_named(" ACME ") is acme


def test_explicit_tags_and_tagged() -> None:
    book = ContactBook()
    ann = book.add_contact("Ann Lee", "ann@lee.dev", tags=["newsletter"])
    book.add_contact("Cy Moss", "cy@moss.dev", tags=["partner"])
    book.tag(ann.contact_id, "partner")
    assert [c.name for c in book.tagged("partner")] == ["Ann Lee", "Cy Moss"]
