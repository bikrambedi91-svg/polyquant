"""Tests for FundingBasis model — Contrarian funding rate signal."""

import pytest
from tests.unit.test_models.conftest import make_default_params
from models.funding_basis import FundingBasisModel


@pytest.fixture
def model():
    return FundingBasisModel(make_default_params("FundBasis"))


@pytest.mark.asyncio
async def test_extreme_negative_funding_bullish(model):
    """Extreme negative funding → contrarian bullish, prob_up > 0.6."""
    out = await model.generate_signal(
        "BTC", "1h", funding_data={"rate": -0.0005, "timestamp": 0, "asset": "BTC"}
    )
    assert out.prob_up > 0.6
    assert out.confidence > 40
    assert any("contrarian_long" in d for d in out.key_drivers)


@pytest.mark.asyncio
async def test_extreme_positive_funding_bearish(model):
    """Extreme positive funding → contrarian bearish, prob_up < 0.4."""
    out = await model.generate_signal(
        "ETH", "1h", funding_data={"rate": 0.002, "timestamp": 0, "asset": "ETH"}
    )
    assert out.prob_up < 0.4
    assert any("contrarian_short" in d for d in out.key_drivers)


@pytest.mark.asyncio
async def test_neutral_funding(model):
    """Neutral funding → prob near 0.5, low confidence."""
    out = await model.generate_signal(
        "BTC", "1h", funding_data={"rate": 0.0001, "timestamp": 0, "asset": "BTC"}
    )
    assert 0.45 <= out.prob_up <= 0.55
    assert out.confidence <= 30


@pytest.mark.asyncio
async def test_no_funding_data(model):
    """Missing funding data → safe output."""
    out = await model.generate_signal("BTC", "1h")
    assert out.confidence == 0
    assert out.prob_up == 0.5


@pytest.mark.asyncio
async def test_prob_clamped(model):
    """Even with extreme data, prob must stay in [0, 1]."""
    out = await model.generate_signal(
        "BTC", "1h", funding_data={"rate": -0.01, "timestamp": 0, "asset": "BTC"}
    )
    assert 0.0 <= out.prob_up <= 1.0
