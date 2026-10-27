"""Contacts and companies, deduplicated by email address."""

from __future__ import annotations

from crm.models import Company, Contact


def normalize_email(email: str) -> str:
    """Return the form of an address used to detect duplicates.

    Email addresses are compared without surrounding whitespace and without
    regard to letter case, so ``" Ann@Example.com"`` and ``"ann@example.com"``
    are the same contact.
    """
    return email.strip().lower()


def email_domain(email: str) -> str:
    """Return the lower-cased domain part of an address, or "" if it has none."""
    _, at, domain = email.strip().rpartition("@")
    return domain.lower() if at else ""


class ContactBook:
    """All contacts and companies, with one contact per email address."""

    def __init__(self) -> None:
        self.companies: dict[str, Company] = {}
        self.contacts: dict[str, Contact] = {}
        self._by_email: dict[str, str] = {}

    def add_company(self, name: str, domain: str = "") -> Company:
        """Create a company; its domain links new contacts to it."""
        company = Company(f"CO{len(self.companies) + 1}", name.strip(), domain.lower())
        self.companies[company.company_id] = company
        return company

    def company_named(self, name: str) -> Company | None:
        """Return the company with this name, ignoring case, if there is one."""
        wanted = name.strip().casefold()
        for company in self.companies.values():
            if company.name.casefold() == wanted:
                return company
        return None

    def company_for_email(self, email: str) -> Company | None:
        """Return the company whose domain matches the address, if any."""
        domain = email_domain(email)
        for company in self.companies.values():
            if domain and company.domain == domain:
                return company
        return None

    def find_by_email(self, email: str) -> Contact | None:
        """Return the contact with this address, if there is one."""
        contact_id = self._by_email.get(normalize_email(email))
        return None if contact_id is None else self.contacts[contact_id]

    def add_contact(
        self,
        name: str,
        email: str,
        company_id: str | None = None,
        tags: list[str] | None = None,
    ) -> Contact:
        """Add a contact, or return the existing one with the same email.

        When the address is already known the existing contact is returned
        and the new tags are added to it. Without a company the contact is
        linked to the company that owns the email domain, if any.
        """
        tags = list(tags) if tags else []
        existing = self.find_by_email(email)
        if existing is not None:
            for tag in tags:
                if tag not in existing.tags:
                    existing.tags.append(tag)
            return existing
        if company_id is None:
            company = self.company_for_email(email)
            company_id = company.company_id if company else None
        contact = Contact(f"C{len(self.contacts) + 1}", name.strip(), email.strip(), company_id, tags=tags)
        self.contacts[contact.contact_id] = contact
        self._by_email[normalize_email(email)] = contact.contact_id
        return contact

    def tag(self, contact_id: str, tag: str) -> None:
        """Add a tag to one contact."""
        tags = self.contacts[contact_id].tags
        if tag not in tags:
            tags.append(tag)

    def tagged(self, tag: str) -> list[Contact]:
        """Return the contacts carrying ``tag``, by id."""
        return [c for c in self.contacts.values() if tag in c.tags]
