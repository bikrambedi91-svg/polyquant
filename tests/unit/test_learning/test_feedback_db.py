"""Tests for learning/feedback_db.py — FeedbackRecord, store, query, Brier."""

import pytest
from learning.feedback_db import FeedbackRecord, FeedbackStore


def _record(
    trade_id="T-001", asset="BTC", timeframe="1h", action="BUY_YES",
    regime="RISK_ON", entry_price=0.55, exit_price=0.70, size_usd=100,
    ensemble_prob=0.65, result="WON", pnl_usd=15.0,
    model_probs=None, **kwargs,
) -> FeedbackRecord:
    return FeedbackRecord(
        trade_id=trade_id,
        asset=asset,
        timeframe=timeframe,
        action=action,
        regime=regime,
        entry_price=entry_price,
        exit_price=exit_price,
        size_usd=size_usd,
        ensemble_prob=ensemble_prob,
        result=result,
        pnl_usd=pnl_usd,
        model_probs=model_probs or {"MomRegime": 0.65, "TechConf": 0.60},
        **kwargs,
    )


class TestFeedbackRecord:
    def test_actual_outcome_buy_yes_won(self):
        r = _record(action="BUY_YES", result="WON")
        assert r.actual_outcome == 1.0

    def test_actual_outcome_buy_yes_lost(self):
        r = _record(action="BUY_YES", result="LOST")
        assert r.actual_outcome == 0.0

    def test_actual_outcome_buy_no_won(self):
        """BUY_NO WON means the event resolved DOWN → outcome=0.0."""
        r = _record(action="BUY_NO", result="WON")
        assert r.actual_outcome == 0.0

    def test_actual_outcome_buy_no_lost(self):
        """BUY_NO LOST means the event resolved UP → outcome=1.0."""
        r = _record(action="BUY_NO", result="LOST")
        assert r.actual_outcome == 1.0

    def test_brier_contribution(self):
        """ensemble_prob=0.65, actual=1.0 → (0.65-1.0)^2 = 0.1225."""
        r = _record(ensemble_prob=0.65, action="BUY_YES", result="WON")
        assert r.brier_contribution == pytest.approx(0.1225)

    def test_oracle_fields(self):
        r = _record(oracle_start_price=95000.0, oracle_end_price=96000.0)
        assert r.oracle_start_price == 95000.0
        assert r.oracle_end_price == 96000.0

    def test_taker_fee_stored(self):
        r = _record(taker_fee_paid=1.50)
        assert r.taker_fee_paid == 1.50


class TestFeedbackStore:
    def test_store_and_get_all(self):
        store = FeedbackStore()
        store.store(_record(trade_id="T-001"))
        store.store(_record(trade_id="T-002"))
        assert store.total_trades == 2
        assert len(store.get_all()) == 2

    def test_get_by_bucket_asset(self):
        store = FeedbackStore()
        store.store(_record(trade_id="T-001", asset="BTC"))
        store.store(_record(trade_id="T-002", asset="ETH"))
        store.store(_record(trade_id="T-003", asset="BTC"))
        assert len(store.get_by_bucket(asset="BTC")) == 2
        assert len(store.get_by_bucket(asset="ETH")) == 1

    def test_get_by_bucket_timeframe(self):
        store = FeedbackStore()
        store.store(_record(trade_id="T-001", timeframe="1h"))
        store.store(_record(trade_id="T-002", timeframe="5m"))
        assert len(store.get_by_bucket(timeframe="5m")) == 1

    def test_get_by_bucket_regime(self):
        store = FeedbackStore()
        store.store(_record(trade_id="T-001", regime="RISK_ON"))
        store.store(_record(trade_id="T-002", regime="RISK_OFF"))
        assert len(store.get_by_bucket(regime="RISK_OFF")) == 1

    def test_get_by_bucket_combined(self):
        store = FeedbackStore()
        store.store(_record(trade_id="T-001", asset="BTC", timeframe="1h", regime="RISK_ON"))
        store.store(_record(trade_id="T-002", asset="BTC", timeframe="1h", regime="RISK_OFF"))
        store.store(_record(trade_id="T-003", asset="ETH", timeframe="1h", regime="RISK_ON"))
        result = store.get_by_bucket(asset="BTC", timeframe="1h", regime="RISK_ON")
        assert len(result) == 1
        assert result[0].trade_id == "T-001"

    def test_get_by_model(self):
        store = FeedbackStore()
        store.store(_record(trade_id="T-001", model_probs={"MomRegime": 0.60}))
        store.store(_record(trade_id="T-002", model_probs={"TechConf": 0.55}))
        assert len(store.get_by_model("MomRegime")) == 1
        assert len(store.get_by_model("TechConf")) == 1

    def test_get_recent(self):
        store = FeedbackStore()
        for i in range(10):
            store.store(_record(trade_id=f"T-{i:03d}"))
        recent = store.get_recent(3)
        assert len(recent) == 3
        assert recent[0].trade_id == "T-007"

    def test_compute_brier_ensemble(self):
        store = FeedbackStore()
        # prob=0.8, outcome=1.0 → (0.8-1)^2 = 0.04
        store.store(_record(ensemble_prob=0.8, action="BUY_YES", result="WON"))
        # prob=0.6, outcome=0.0 → (0.6-0)^2 = 0.36
        store.store(_record(trade_id="T-002", ensemble_prob=0.6, action="BUY_YES", result="LOST"))
        brier = store.compute_brier_score()
        assert brier == pytest.approx(0.20)  # (0.04 + 0.36) / 2

    def test_compute_brier_per_model(self):
        store = FeedbackStore()
        store.store(_record(model_probs={"MomRegime": 0.80}, action="BUY_YES", result="WON"))
        store.store(_record(trade_id="T-002", model_probs={"MomRegime": 0.60}, action="BUY_YES", result="LOST"))
        brier = store.compute_brier_score(model_name="MomRegime")
        # (0.80-1)^2 = 0.04, (0.60-0)^2 = 0.36 → avg = 0.20
        assert brier == pytest.approx(0.20)

    def test_compute_brier_no_records(self):
        store = FeedbackStore()
        assert store.compute_brier_score() is None

    def test_win_rate(self):
        store = FeedbackStore()
        store.store(_record(trade_id="T-001", result="WON"))
        store.store(_record(trade_id="T-002", result="WON"))
        store.store(_record(trade_id="T-003", result="LOST"))
        assert store.compute_win_rate() == pytest.approx(2 / 3)

    def test_total_pnl(self):
        store = FeedbackStore()
        store.store(_record(trade_id="T-001", pnl_usd=10.0))
        store.store(_record(trade_id="T-002", pnl_usd=-5.0))
        assert store.compute_total_pnl() == pytest.approx(5.0)

    def test_cold_start(self):
        store = FeedbackStore()
        assert store.is_cold_start() is True
        for i in range(50):
            store.store(_record(trade_id=f"T-{i:03d}"))
        assert store.is_cold_start() is False

    def test_optuna_ready(self):
        store = FeedbackStore()
        assert store.is_optuna_ready() is False
        for i in range(80):
            store.store(_record(trade_id=f"T-{i:03d}"))
        assert store.is_optuna_ready() is True
