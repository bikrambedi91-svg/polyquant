"""Tests for VolSurface model — IV skew / ATR percentile fallback."""

import pytest
from tests.unit.test_models.conftest import make_ohlcv, make_default_params
from models.vol_surface import VolSurfaceModel


@pytest.fixture
def model():
    return VolSurfaceModel(make_default_params("VolSurf"))


@pytest.mark.asyncio
async def test_atr_fallback_no_deribit(model):
    """No Deribit key → uses ATR percentile fallback without error."""
    ohlcv = make_ohlcv(150, trend="up")
    out = await model.generate_signal("BTC", "1h", ohlcv)
    assert out.model_name == "VolSurf"
    assert 0.0 <= out.prob_up <= 1.0
    assert out.raw_indicators.get("source") == "atr_fallback"


@pytest.mark.asyncio
async def test_deribit_data_steep_put_skew(model):
    """Steep put skew from Deribit → contrarian bullish."""
    ohlcv = make_ohlcv(150)
    out = await model.generate_signal(
        "BTC", "1h", ohlcv, deribit_data={"skew_25d": -10.0}
    )
    assert out.prob_up > 0.55
    assert out.raw_indicators.get("source") == "deribit"
    assert any("put_skew_steep" in d for d in out.key_drivers)


@pytest.mark.asyncio
async def test_deribit_data_steep_call_skew(model):
    """Steep call skew → contrarian bearish."""
    ohlcv = make_ohlcv(150)
    out = await model.generate_signal(
        "ETH", "1h", ohlcv, deribit_data={"skew_25d": 10.0}
    )
    assert out.prob_up < 0.45


@pytest.mark.asyncio
async def test_sol_uses_atr_even_with_deribit(model):
    """SOL/XRP should use ATR fallback even if Deribit data provided."""
    ohlcv = make_ohlcv(150)
    out = await model.generate_signal(
        "SOL", "1h", ohlcv, deribit_data={"skew_25d": -10.0}
    )
    assert out.raw_indicators.get("source") == "atr_fallback"


@pytest.mark.asyncio
async def test_insufficient_data(model):
    """Too few bars → safe output."""
    ohlcv = make_ohlcv(5)
    out = await model.generate_signal("BTC", "1h", ohlcv)
    assert out.confidence == 0
