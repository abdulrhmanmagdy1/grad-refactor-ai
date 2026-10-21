"""The catalog of books and how many copies are on the shelf."""

from __future__ import annotations

from library.models import Book


class Catalog:
    """Books by ISBN, with the number of copies available to lend."""

    def __init__(self) -> None:
        self.books: dict[str, Book] = {}
        self.available: dict[str, int] = {}

    def add(self, book: Book) -> None:
        """Add a book, or more copies of a book already in the catalog."""
        if book.isbn in self.books:
            self.books[book.isbn].copies += book.copies
        else:
            self.books[book.isbn] = book
        self.available[book.isbn] = self.available.get(book.isbn, 0) + book.copies

    def search(self, words: str, found: list[Book] | None = None) -> list[Book]:
        """Books whose title or author contains every word (case-insensitive)."""
        found = [] if found is None else found
        terms = words.lower().split()
        for book in self.books.values():
            text = f"{book.title} {book.author}".lower()
            if all(term in text for term in terms):
                found.append(book)
        return found

    def remove_author(self, author: str) -> int:
        """Remove every book by an author; returns how many titles were removed."""
        removed = 0
        for isbn in list(self.books):
            if self.books[isbn].author == author:
                del self.books[isbn]
                self.available.pop(isbn, None)
                removed += 1
        return removed

    def take(self, isbn: str) -> None:
        """Take one copy off the shelf."""
        if self.available.get(isbn, 0) <= 0:
            raise LookupError(f"no copy of {isbn} is available")
        self.available[isbn] -= 1

    def put_back(self, isbn: str) -> None:
        """Return one copy to the shelf."""
        self.available[isbn] = self.available.get(isbn, 0) + 1
