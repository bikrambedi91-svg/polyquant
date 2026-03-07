"""Tests for SentimentComposite model — Fear & Greed Index."""

import pytest
from tests.unit.test_models.conftest import make_default_params
from models.sentiment import SentimentModel


@pytest.fixture
def model():
    return SentimentModel(make_default_params("SentComp"))


@pytest.mark.asyncio
async def test_extreme_fear_bullish(model):
    """F&G=15 → extreme fear → contrarian bullish, prob_up > 0.55."""
    out = await model.generate_signal(
        "BTC", "1h", sentiment_data={"value": 15, "classification": "Extreme Fear"}
    )
    assert out.prob_up > 0.55
    assert out.confidence > 40
    assert any("contrarian_bullish" in d for d in out.key_drivers)


@pytest.mark.asyncio
async def test_extreme_greed_bearish(model):
    """F&G=90 → extreme greed → contrarian bearish, prob_up < 0.4."""
    out = await model.generate_signal(
        "ETH", "1h", sentiment_data={"value": 90, "classification": "Extreme Greed"}
    )
    assert out.prob_up < 0.4


@pytest.mark.asyncio
async def test_neutral_range(model):
    """F&G=50 → neutral range, prob near 0.5."""
    out = await model.generate_signal(
        "BTC", "1h", sentiment_data={"value": 50, "classification": "Neutral"}
    )
    assert 0.45 <= out.prob_up <= 0.55
    assert out.confidence <= 30


@pytest.mark.asyncio
async def test_5m_timeframe_returns_zero_confidence(model):
    """5m timeframe → confidence=0 (sentiment is stale on short TFs)."""
    out = await model.generate_signal(
        "BTC", "5m", sentiment_data={"value": 15, "classification": "Extreme Fear"}
    )
    assert out.confidence == 0
    assert out.prob_up == 0.5


@pytest.mark.asyncio
async def test_15m_timeframe_returns_zero_confidence(model):
    """15m timeframe → confidence=0."""
    out = await model.generate_signal(
        "BTC", "15m", sentiment_data={"value": 90, "classification": "Extreme Greed"}
    )
    assert out.confidence == 0


@pytest.mark.asyncio
async def test_no_sentiment_data(model):
    """Missing sentiment data → safe output."""
    out = await model.generate_signal("BTC", "1h")
    assert out.confidence == 0
