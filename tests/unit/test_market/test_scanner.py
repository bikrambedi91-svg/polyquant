"""Tests for market/scanner.py — deterministic slug-based market discovery."""

import json
import time
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import httpx

from market.scanner import PolymarketScanner, CryptoMarket


def _make_event_response(
    question="Bitcoin Up or Down - March 5, 1:00PM-1:15PM ET",
    volume=10000,
    clob_token_ids=None,
    outcome_prices=None,
    end_date=None,
    condition_id="cond_123",
):
    """Build a mock Gamma API event response (as returned by /events/slug/{slug})."""
    if clob_token_ids is None:
        clob_token_ids = '["YES_TOKEN_ABC","NO_TOKEN_DEF"]'
    if outcome_prices is None:
        outcome_prices = '["0.55","0.45"]'
    if end_date is None:
        end_date = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()

    return {
        "id": "event_1",
        "title": question,
        "markets": [
            {
                "question": question,
                "clobTokenIds": clob_token_ids,
                "outcomePrices": outcome_prices,
                "volume": volume,
                "endDate": end_date,
                "conditionId": condition_id,
                "acceptingOrders": True,
            }
        ],
    }


def _mock_http_client(slug_responses: dict[str, dict | None]):
    """Create mock client that returns specific responses per slug.

    slug_responses maps slug substring → event dict (or None for 404).
    """
    async def mock_get(url, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.raise_for_status = MagicMock()

        for slug_part, event_data in slug_responses.items():
            if slug_part in url:
                if event_data is None:
                    resp.status_code = 404
                else:
                    resp.status_code = 200
                    resp.json.return_value = event_data
                return resp

        # Default: 404
        resp.status_code = 404
        return resp

    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = mock_get
    client.aclose = AsyncMock()
    return client


# ── Slug Generation Tests ──


def test_generates_12_slugs():
    """Should generate exactly 12 slugs (4 assets × 3 timeframes)."""
    scanner = PolymarketScanner()
    slugs = scanner._generate_all_slugs()

    assert len(slugs) == 12
    assets = {s[0] for s in slugs}
    timeframes = {s[1] for s in slugs}
    assert assets == {"BTC", "ETH", "SOL", "XRP"}
    assert timeframes == {"15m", "1h", "4h"}


def test_15m_slug_format():
    """15m slugs should be {asset}-updown-15m-{ts} aligned to 900s."""
    scanner = PolymarketScanner()
    slugs = scanner._generate_all_slugs()

    for asset, tf, slug in slugs:
        if tf == "15m":
            parts = slug.split("-")
            assert parts[1] == "updown"
            assert parts[2] == "15m"
            ts = int(parts[3])
            assert ts % 900 == 0  # aligned to 900s


def test_1h_slug_format():
    """1h slugs should be {asset_full}-up-or-down-{month}-{day}-{hour}{ampm}-et."""
    scanner = PolymarketScanner()
    slugs = scanner._generate_all_slugs()

    for asset, tf, slug in slugs:
        if tf == "1h":
            assert "up-or-down" in slug
            assert slug.endswith("-et")
            # Asset name should be full form
            if asset == "BTC":
                assert slug.startswith("bitcoin-")
            elif asset == "ETH":
                assert slug.startswith("ethereum-")
            elif asset == "SOL":
                assert slug.startswith("solana-")
            elif asset == "XRP":
                assert slug.startswith("xrp-")


def test_4h_slug_format():
    """4h slugs should be {asset}-updown-4h-{ts} aligned to 4h ET blocks."""
    scanner = PolymarketScanner()
    slugs = scanner._generate_all_slugs()

    for asset, tf, slug in slugs:
        if tf == "4h":
            parts = slug.split("-")
            assert parts[1] == "updown"
            assert parts[2] == "4h"
            # Timestamp exists and is a valid integer
            ts = int(parts[3])
            assert ts > 0


# ── Market Parsing Tests ──


def test_parses_market_correctly():
    """Should parse token IDs, prices, and metadata from event response."""
    scanner = PolymarketScanner()
    end_time = (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat()
    mkt = {
        "question": "Bitcoin Up or Down - March 6, 12:45PM-1:00PM ET",
        "clobTokenIds": '["YES_ABC","NO_DEF"]',
        "outcomePrices": '["0.72","0.28"]',
        "volume": 5000,
        "endDate": end_time,
        "conditionId": "cond_1",
        "acceptingOrders": True,
    }
    result = scanner._parse_market(mkt, "BTC", "15m", "btc-updown-15m-123")

    assert result is not None
    assert result.asset == "BTC"
    assert result.timeframe == "15m"
    assert result.market_type == "up_down"
    assert result.token_id_yes == "YES_ABC"
    assert result.token_id_no == "NO_DEF"
    assert result.current_yes_price == 0.72
    assert result.start_datetime is not None


def test_skips_closed_market():
    """Closed markets should be skipped."""
    scanner = PolymarketScanner()
    mkt = {
        "question": "Bitcoin Up or Down",
        "clobTokenIds": '["Y","N"]',
        "outcomePrices": '["0.5","0.5"]',
        "volume": 1000,
        "endDate": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "closed": True,
        "acceptingOrders": False,
    }
    assert scanner._parse_market(mkt, "BTC", "1h", "test") is None


def test_handles_list_clob_token_ids():
    """clobTokenIds can be a list (in tests) or stringified JSON (from API)."""
    scanner = PolymarketScanner()
    mkt = {
        "question": "Bitcoin Up or Down",
        "clobTokenIds": ["YES_1", "NO_1"],
        "outcomePrices": '["0.60","0.40"]',
        "volume": 1000,
        "endDate": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        "acceptingOrders": True,
    }
    result = scanner._parse_market(mkt, "BTC", "1h", "test")
    assert result is not None
    assert result.token_id_yes == "YES_1"


# ── Discovery Integration Tests ──


@pytest.mark.asyncio
async def test_discovers_market_by_slug():
    """Should fetch and parse a market by its generated slug."""
    # Use different end_dates per timeframe so TTR/age filters pass
    end_15m = (datetime.now(timezone.utc) + timedelta(minutes=12)).isoformat()
    end_1h = (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat()
    end_4h = (datetime.now(timezone.utc) + timedelta(hours=3, minutes=50)).isoformat()

    ev_15m = _make_event_response(question="BTC Up or Down 15m", end_date=end_15m)
    ev_1h = _make_event_response(question="Bitcoin Up or Down 1h", end_date=end_1h)
    ev_4h = _make_event_response(question="BTC Up or Down 4h", end_date=end_4h)

    # Map slug substrings → responses (15m slugs contain "updown-15m", etc.)
    client = _mock_http_client({
        "updown-15m": ev_15m,
        "up-or-down": ev_1h,
        "updown-4h": ev_4h,
    })
    scanner = PolymarketScanner(http_client=client)
    markets = await scanner.discover_markets()

    assert len(markets) > 0


@pytest.mark.asyncio
async def test_handles_404_gracefully():
    """If a slug returns 404, that market is skipped without error."""
    client = _mock_http_client({})  # All slugs will 404
    scanner = PolymarketScanner(http_client=client)
    markets = await scanner.discover_markets()

    assert markets == []


@pytest.mark.asyncio
async def test_handles_api_error_gracefully():
    """API failure → empty list, no crash."""
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(side_effect=httpx.HTTPError("connection failed"))
    client.aclose = AsyncMock()

    scanner = PolymarketScanner(http_client=client)
    markets = await scanner.discover_markets()

    assert markets == []


@pytest.mark.asyncio
async def test_filters_expired_markets():
    """Markets past their end time should be filtered out."""
    expired = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    event = _make_event_response(end_date=expired)
    client = _mock_http_client({"btc": event, "bitcoin": event})
    scanner = PolymarketScanner(http_client=client)
    markets = await scanner.discover_markets()

    btc_markets = [m for m in markets if m.asset == "BTC"]
    assert len(btc_markets) == 0


def test_start_datetime_computed():
    """start_datetime should be end_datetime - duration for each timeframe."""
    scanner = PolymarketScanner()
    end_time = datetime.now(timezone.utc) + timedelta(minutes=10)
    mkt = {
        "question": "BTC Up or Down",
        "clobTokenIds": '["Y","N"]',
        "outcomePrices": '["0.5","0.5"]',
        "volume": 1000,
        "endDate": end_time.isoformat(),
        "acceptingOrders": True,
    }
    # 15m → start = end - 900s
    result = scanner._parse_market(mkt, "BTC", "15m", "test")
    assert result is not None
    expected_start = result.end_datetime - timedelta(seconds=900)
    assert abs((result.start_datetime - expected_start).total_seconds()) < 2

    # 1h → start = end - 3600s
    result_1h = scanner._parse_market(mkt, "BTC", "1h", "test")
    expected_start_1h = result_1h.end_datetime - timedelta(seconds=3600)
    assert abs((result_1h.start_datetime - expected_start_1h).total_seconds()) < 2
