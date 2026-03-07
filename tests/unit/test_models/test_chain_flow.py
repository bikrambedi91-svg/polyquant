"""Tests for ChainFlow model — Exchange net flow signal."""

import pytest
from tests.unit.test_models.conftest import make_default_params
from models.chain_flow import ChainFlowModel


@pytest.fixture
def model():
    return ChainFlowModel(make_default_params("ChainFlow"))


@pytest.mark.asyncio
async def test_large_outflow_bullish(model):
    """Large outflow (negative net_flow) → bullish signal."""
    out = await model.generate_signal(
        "BTC", "1h", flow_data={"net_flow": -5.0, "confidence": 60, "asset": "BTC"}
    )
    assert out.prob_up > 0.55
    assert out.confidence > 30
    assert any("outflow_bullish" in d for d in out.key_drivers)


@pytest.mark.asyncio
async def test_large_inflow_bearish(model):
    """Large inflow (positive net_flow) → bearish signal."""
    out = await model.generate_signal(
        "ETH", "1h", flow_data={"net_flow": 5.0, "confidence": 60, "asset": "ETH"}
    )
    assert out.prob_up < 0.45


@pytest.mark.asyncio
async def test_zero_confidence_returns_neutral(model):
    """Feed confidence=0 (no API key) → prob=0.5, confidence=0."""
    out = await model.generate_signal(
        "BTC", "1h", flow_data={"net_flow": 0.0, "confidence": 0, "asset": "BTC"}
    )
    assert out.prob_up == 0.5
    assert out.confidence == 0
    assert any("no_onchain_data" in d for d in out.key_drivers)


@pytest.mark.asyncio
async def test_no_flow_data(model):
    """Missing flow data → safe output."""
    out = await model.generate_signal("BTC", "1h")
    assert out.confidence == 0


@pytest.mark.asyncio
async def test_neutral_flow(model):
    """Small net_flow → neutral output."""
    out = await model.generate_signal(
        "BTC", "1h", flow_data={"net_flow": 0.3, "confidence": 60, "asset": "BTC"}
    )
    assert 0.45 <= out.prob_up <= 0.55
