"""Comment attachments, stored on disk under the uploads folder."""

from __future__ import annotations

import shutil
from pathlib import Path

from helpdesk.models import Attachment

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024


class UploadStore:
    """Keeps every attachment at ``root/<ticket id>/<file name>``."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def ticket_folder(self, ticket_id: int) -> Path:
        """The folder holding the attachments of one ticket."""
        return self.root / str(ticket_id)

    def save(self, ticket_id: int, filename: str, data: bytes) -> Attachment:
        """Store an uploaded file for a ticket and return its record.

        Empty names and files over ``MAX_ATTACHMENT_BYTES`` are refused; a file
        with the same name on the same ticket is replaced.
        """
        if not filename or filename in {".", ".."} or Path(filename).name != filename:
            raise ValueError(f"invalid attachment name: {filename!r}")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise ValueError(f"{filename} is larger than {MAX_ATTACHMENT_BYTES} bytes")
        folder = self.ticket_folder(ticket_id)
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / filename
        target.write_bytes(data)
        return Attachment(filename=filename, path=str(target), size=len(data))

    def read(self, attachment: Attachment) -> bytes:
        """Return the stored content of an attachment."""
        return Path(attachment.path).read_bytes()

    def delete(self, attachment: Attachment) -> None:
        """Remove one stored attachment; a file that is already gone is ignored."""
        Path(attachment.path).unlink(missing_ok=True)

    def purge_ticket(self, ticket_id: int) -> int:
        """Delete every attachment of a ticket and return how many files were removed."""
        folder = self.ticket_folder(ticket_id)
        if not folder.is_dir():
            return 0
        count = sum(1 for path in folder.iterdir() if path.is_file())
        shutil.rmtree(folder)
        return count
