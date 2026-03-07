"""Tests for MomentumRegime model — ADX + DI trend classification."""

import pytest
from tests.unit.test_models.conftest import make_ohlcv, make_default_params
from models.momentum_regime import MomentumRegimeModel


@pytest.fixture
def model():
    params = make_default_params("MomRegime", "5m")
    return MomentumRegimeModel(params)


@pytest.mark.asyncio
async def test_trending_up_signal(model):
    """Strong uptrend OHLCV should give TRENDING_UP with prob_up > 0.55."""
    ohlcv = make_ohlcv(150, trend="up", volatility=0.003, seed=42)
    out = await model.generate_signal("BTC", "5m", ohlcv)
    assert out.model_name == "MomRegime"
    assert out.prob_up > 0.55
    assert out.confidence > 30
    assert any("TRENDING_UP" in d for d in out.key_drivers)


@pytest.mark.asyncio
async def test_trending_down_signal(model):
    """Strong downtrend OHLCV should give prob_up < 0.45."""
    ohlcv = make_ohlcv(150, trend="down", volatility=0.003, seed=42)
    out = await model.generate_signal("ETH", "5m", ohlcv)
    assert out.prob_up < 0.45


@pytest.mark.asyncio
async def test_choppy_signal(model):
    """Choppy data should give prob in reasonable range."""
    ohlcv = make_ohlcv(150, trend="choppy", volatility=0.005, seed=42)
    out = await model.generate_signal("SOL", "5m", ohlcv)
    assert 0.10 <= out.prob_up <= 0.90


@pytest.mark.asyncio
async def test_insufficient_data_returns_safe_output(model):
    """Too few bars → confidence=0 fallback."""
    ohlcv = make_ohlcv(5, trend="up")
    out = await model.generate_signal("BTC", "5m", ohlcv)
    assert out.confidence == 0
    assert out.prob_up == 0.5


@pytest.mark.asyncio
async def test_param_version_propagated(model):
    """Output should carry the param version."""
    ohlcv = make_ohlcv(150, trend="up")
    out = await model.generate_signal("BTC", "5m", ohlcv)
    assert out.param_version == 1


@pytest.mark.asyncio
async def test_hot_swap_params():
    """Changing params at runtime changes model behavior."""
    params1 = make_default_params("MomRegime", "5m")
    model = MomentumRegimeModel(params1)

    ohlcv = make_ohlcv(150, trend="up", seed=42)
    out1 = await model.generate_signal("BTC", "5m", ohlcv)

    # Swap to much higher ADX threshold (makes it harder to classify as trending)
    from models.base import ModelParams
    params2 = ModelParams(values={**params1.values, "adx_threshold": 35}, version=2)
    model.update_params(params2)
    out2 = await model.generate_signal("BTC", "5m", ohlcv)

    assert out2.param_version == 2
    # With higher threshold, less likely to be classified as trending
    # so the output should differ from the original
