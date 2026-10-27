"""Deals and the sales pipeline stages they move through."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from crm.models import Deal, StageChange

# Chance of winning a deal in each stage, in pipeline order.
STAGE_PROBABILITY: dict[str, Decimal] = {
    "lead": Decimal("0.10"),
    "qualified": Decimal("0.25"),
    "proposal": Decimal("0.50"),
    "negotiation": Decimal("0.75"),
    "won": Decimal("1.00"),
    "lost": Decimal("0.00"),
}
CLOSED_STAGES = frozenset({"won", "lost"})


class PipelineError(ValueError):
    """Raised for an unknown deal or stage, or a move of a closed deal."""


def weighted_amount(deal: Deal) -> Decimal:
    """Return the deal amount multiplied by its stage's win probability."""
    return (deal.amount * STAGE_PROBABILITY[deal.stage]).quantize(Decimal("0.01"))


class Pipeline:
    """The deals being worked on and the history of their stage moves."""

    def __init__(self) -> None:
        self.deals: dict[str, Deal] = {}
        self.history: list[StageChange] = []

    def open_deal(self, title: str, company_id: str, amount: Decimal, expected_close: date) -> Deal:
        """Create a deal in the first stage."""
        if amount <= 0:
            raise PipelineError("a deal needs a positive amount")
        deal = Deal(f"D{len(self.deals) + 1}", title, company_id, amount, expected_close)
        self.deals[deal.deal_id] = deal
        return deal

    def get(self, deal_id: str) -> Deal:
        """Return a deal by id."""
        try:
            return self.deals[deal_id]
        except KeyError:
            raise PipelineError(f"unknown deal {deal_id!r}") from None

    def move(self, deal_id: str, stage: str, at: datetime) -> Deal:
        """Move a deal to ``stage`` and record the change in the history.

        Won and lost deals are closed and cannot be moved again.
        """
        deal = self.get(deal_id)
        if stage not in STAGE_PROBABILITY:
            raise PipelineError(f"unknown stage {stage!r}")
        if deal.stage in CLOSED_STAGES:
            raise PipelineError(f"{deal.deal_id} is already {deal.stage}")
        previous = deal.stage
        deal.stage = stage
        self.history.append(StageChange(deal.deal_id, stage, previous, at))
        return deal

    def changes_for(self, deal_id: str) -> list[StageChange]:
        """Return the stage moves of one deal, oldest first."""
        return [change for change in self.history if change.deal_id == deal_id]

    def entered_stage_at(self, deal_id: str, stage: str) -> datetime | None:
        """Return when the deal last moved into ``stage``, or None."""
        moves = [c.at for c in self.changes_for(deal_id) if c.to_stage == stage]
        return moves[-1] if moves else None

    def open_deals(self) -> list[Deal]:
        """Return the deals that are neither won nor lost."""
        return [d for d in self.deals.values() if d.stage not in CLOSED_STAGES]

    def pipeline_value(self) -> Decimal:
        """Return the sum of the weighted amounts of all open deals."""
        return sum((weighted_amount(d) for d in self.open_deals()), Decimal("0.00"))


def _stage_rank(stage: str) -> int:
    """Return the position of a stage in the pipeline, 0 for the first."""
    return list(STAGE_PROBABILITY).index(stage)
