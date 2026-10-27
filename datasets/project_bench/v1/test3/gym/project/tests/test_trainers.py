from datetime import datetime
from decimal import Decimal

import pytest

from gym.billing import Ledger
from gym.trainers import Trainer, TrainerDiary, TrainerError

START = datetime(2026, 3, 10, 9, 0)


@pytest.fixture
def diary() -> TrainerDiary:
    diary = TrainerDiary(Ledger())
    diary.add_trainer(Trainer("t1", "Karim", Decimal("40.00")))
    return diary


def test_overlapping_sessions_are_refused(diary: TrainerDiary) -> None:
    diary.book("t1", "m1", START, 60)
    with pytest.raises(TrainerError):
        diary.book("t1", "m2", datetime(2026, 3, 10, 9, 30), 60)


def test_back_to_back_sessions_are_fine(diary: TrainerDiary) -> None:
    diary.book("t1", "m1", START, 60)
    session = diary.book("t1", "m2", datetime(2026, 3, 10, 10, 0), 60)
    assert session.session_id == "PT0002"


def test_completed_session_is_charged(diary: TrainerDiary) -> None:
    session = diary.book("t1", "m1", START, 60)
    diary.complete(session.session_id)
    assert [c.amount for c in diary.ledger.pending["m1"]] == [Decimal("40.00")]


def test_late_cancellation_is_charged(diary: TrainerDiary) -> None:
    session = diary.book("t1", "m1", START, 60)
    assert diary.cancel(session.session_id, datetime(2026, 3, 9, 20, 0)) is True
    assert "m1" in diary.ledger.pending


def test_early_cancellation_is_free_and_frees_the_slot(diary: TrainerDiary) -> None:
    session = diary.book("t1", "m1", START, 60)
    assert diary.cancel(session.session_id, datetime(2026, 3, 8, 9, 0)) is False
    assert diary.ledger.pending == {}
    diary.book("t1", "m2", START, 60)
