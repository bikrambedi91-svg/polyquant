"""Main loop — APScheduler orchestration with graceful shutdown.

Runs a 30-second cycle for full pipeline + 2-second fast monitor for 5m/15m positions.
Per-timeframe cooldowns prevent over-trading.
Graceful shutdown on SIGINT/SIGTERM.
Error handling: cycle failure → log, continue. FeedHealthError → halt immediately.
"""

import asyncio
import signal
import sys
from datetime import datetime, timezone

import structlog

from config.constants import MARKET_TIMEFRAMES
from data.price_feed import FeedHealthError
from orchestrator.pipeline import TradingPipeline

logger = structlog.get_logger(__name__)

# Cooldowns per timeframe (seconds) — don't re-check a timeframe too often
# 1h cooldown reduced from 120s to 30s to catch re-entry opportunities
# after TP exits. Binary TP often hits in <10s, price bounces, creating
# multiple entry points within a single 1h market window.
TIMEFRAME_COOLDOWNS: dict[str, int] = {
    "5m": 30,
    "15m": 60,
    "1h": 30,    # Fast re-evaluation for 1h re-entries after TP
    "4h": 600,
    "daily": 1800,  # 30 min — daily markets move slow
}

# Fast monitor interval for 5m/15m positions (seconds)
FAST_MONITOR_INTERVAL = 2


class MainLoop:
    """Runs the trading pipeline on a schedule with graceful shutdown."""

    def __init__(
        self,
        pipeline: TradingPipeline,
        cycle_interval: int = 30,
        timeframes: list[str] | None = None,
        ws_manager=None,
    ):
        self._pipeline = pipeline
        self._interval = cycle_interval
        self._timeframes = timeframes or MARKET_TIMEFRAMES
        self._ws_manager = ws_manager
        self._running = False
        self._shutdown_event = asyncio.Event()
        self._last_run: dict[str, datetime] = {}
        self._cycle_count = 0
        self._total_trades = 0
        self._total_exits = 0
        self._fast_exits = 0
        self._errors = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def cycle_count(self) -> int:
        return self._cycle_count

    def _should_run_timeframe(self, tf: str) -> bool:
        """Check cooldown for a timeframe."""
        last = self._last_run.get(tf)
        if last is None:
            return True
        cooldown = TIMEFRAME_COOLDOWNS.get(tf, 60)
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
        return elapsed >= cooldown

    async def start(self) -> None:
        """Start the main trading loop. Blocks until shutdown."""
        self._running = True
        self._setup_signal_handlers()

        # Start WebSocket manager if provided
        if self._ws_manager:
            await self._ws_manager.start()
            logger.info("ws_manager_launched")

        logger.info(
            "main_loop_started",
            interval=self._interval,
            fast_monitor_interval=FAST_MONITOR_INTERVAL,
            timeframes=self._timeframes,
            ws_enabled=self._ws_manager is not None,
        )

        # Start fast monitor as a concurrent background task
        fast_task = asyncio.create_task(self._fast_monitor_loop())

        try:
            while self._running:
                await self._run_one_iteration()

                # Wait for next cycle or shutdown
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=self._interval,
                    )
                    # If we get here, shutdown was requested
                    break
                except asyncio.TimeoutError:
                    # Normal timeout — continue loop
                    pass

        except asyncio.CancelledError:
            logger.info("main_loop_cancelled")
        finally:
            fast_task.cancel()
            try:
                await fast_task
            except asyncio.CancelledError:
                pass
            # Stop WebSocket manager
            if self._ws_manager:
                await self._ws_manager.stop()
            self._running = False
            logger.info(
                "main_loop_stopped",
                cycles=self._cycle_count,
                trades=self._total_trades,
                exits=self._total_exits,
                fast_exits=self._fast_exits,
                errors=self._errors,
            )

    async def _fast_monitor_loop(self) -> None:
        """2-second fast monitoring loop for 5m/15m positions.

        Fetches fresh CLOB prices and checks TP/SL independently
        from the main 30-second trading cycle.
        """
        logger.info("fast_monitor_started", interval=FAST_MONITOR_INTERVAL)
        while self._running:
            try:
                exits = await self._pipeline.fast_monitor()
                if exits > 0:
                    self._fast_exits += exits
                    self._total_exits += exits
                    logger.info("fast_monitor_exits", count=exits, total_fast=self._fast_exits)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("fast_monitor_error", error=str(exc))

            try:
                await asyncio.sleep(FAST_MONITOR_INTERVAL)
            except asyncio.CancelledError:
                raise

    async def _run_one_iteration(self) -> None:
        """Run one iteration: check each timeframe and run pipeline."""
        self._cycle_count += 1

        for tf in self._timeframes:
            if not self._running:
                break

            if not self._should_run_timeframe(tf):
                continue

            try:
                result = await self._pipeline.run_cycle(timeframe=tf)
                self._last_run[tf] = datetime.now(timezone.utc)
                self._total_trades += result.trades_opened
                self._total_exits += result.exits_executed

                if result.errors:
                    self._errors += len(result.errors)

            except FeedHealthError as exc:
                # Price feeds critically broken — halt bot immediately
                logger.critical(
                    "feed_health_halt",
                    timeframe=tf,
                    cycle=self._cycle_count,
                    error=str(exc),
                )
                print(f"\n  HALTING BOT: {exc}")
                self.stop()
                return  # Don't process more timeframes

            except Exception as exc:
                self._errors += 1
                logger.error(
                    "cycle_error",
                    timeframe=tf,
                    cycle=self._cycle_count,
                    error=str(exc),
                )
                # Don't crash — continue to next timeframe

    def stop(self) -> None:
        """Request graceful shutdown."""
        logger.info("shutdown_requested")
        self._running = False
        self._shutdown_event.set()

    def _setup_signal_handlers(self) -> None:
        """Register signal handlers for graceful shutdown."""
        loop = asyncio.get_event_loop()

        def _handle_signal(sig):
            logger.info("signal_received", signal=sig.name)
            self.stop()

        # Only set signal handlers on Unix-like systems or if supported
        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, _handle_signal, sig)
        except (NotImplementedError, AttributeError):
            # Windows doesn't support add_signal_handler
            pass

    def get_status(self) -> dict:
        """Get current loop status for dashboard."""
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "total_trades": self._total_trades,
            "total_exits": self._total_exits,
            "fast_exits": self._fast_exits,
            "errors": self._errors,
            "last_run": {
                tf: dt.isoformat() for tf, dt in self._last_run.items()
            },
        }
