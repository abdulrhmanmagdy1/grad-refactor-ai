from datetime import date, datetime
from decimal import Decimal

import pytest

from crm.forecast import forecast, months_ahead, render
from crm.pipeline import Pipeline, PipelineError, weighted_amount

NOW = datetime(2026, 10, 27, 9, 0)


def make_pipeline() -> Pipeline:
    pipeline = Pipeline()
    pipeline.open_deal("Website", "CO1", Decimal("10000"), date(2026, 11, 15))
    pipeline.open_deal("Support plan", "CO2", Decimal("4000"), date(2026, 12, 1))
    pipeline.open_deal("Hardware", "CO1", Decimal("2500"), date(2027, 3, 1))
    return pipeline


def test_move_changes_stage_and_weight() -> None:
    pipeline = make_pipeline()
    deal = pipeline.move("D1", "proposal", NOW)
    assert deal.stage == "proposal"
    assert weighted_amount(deal) == Decimal("5000.00")
    assert len(pipeline.changes_for("D1")) == 1


def test_closed_deals_cannot_move() -> None:
    pipeline = make_pipeline()
    pipeline.move("D2", "won", NOW)
    with pytest.raises(PipelineError):
        pipeline.move("D2", "negotiation", NOW)
    with pytest.raises(PipelineError):
        pipeline.move("D1", "maybe", NOW)


def test_pipeline_value_counts_open_deals_only() -> None:
    pipeline = make_pipeline()
    pipeline.move("D2", "lost", NOW)
    assert pipeline.pipeline_value() == Decimal("1250.00")


def test_months_ahead_crosses_the_year() -> None:
    assert months_ahead(date(2026, 11, 3), 3) == ["2026-11", "2026-12", "2027-01"]


def test_forecast_by_month() -> None:
    pipeline = make_pipeline()
    pipeline.move("D1", "negotiation", NOW)
    rows = forecast(list(pipeline.deals.values()), date(2026, 10, 1), months=3)
    assert [r.month for r in rows] == ["2026-10", "2026-11", "2026-12"]
    assert rows[1].deals == 1 and rows[1].weighted == Decimal("7500.00")
    assert rows[2].weighted == Decimal("400.00")
    assert "total" in render(rows)
