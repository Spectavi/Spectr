import asyncio
import logging

import cache


log = logging.getLogger(__name__)


class CustomScanner:
    """Background scanner for filtering top gainers."""

    def __init__(self, data_api, exit_event) -> None:
        self.data_api = data_api
        self.exit_event = exit_event
        self.scanner_results: list[dict] = cache.load_scanner_cache()
        self.top_gainers: list[dict] = cache.load_gainers_cache()

    def _check_scan_symbol(self, row: dict) -> dict | None:
        """Fetch extra metrics for ``row`` and flag if it passes the filter."""
        sym = row["symbol"]
        quote = self.data_api.fetch_quote(sym)
        if not quote:
            return None

        profile = {}
        if hasattr(self.data_api, "fetch_company_profile"):
            try:
                profile = self.data_api.fetch_company_profile(sym) or {}
            except Exception:
                profile = {}

        prev = quote.get("previousClose") or 0

        avg_vol = quote.get("avgVolume") or profile.get("volAvg") or 0
        volume = quote.get("volume") or 0
        float_shares = (
            profile.get("float")
            or profile.get("floatShares")
            or quote.get("sharesOutstanding")
            or 0
        )

        rel_vol_pct = 100 * volume / avg_vol if avg_vol else 0

        passed = True
        if prev == 0 or (quote["price"] - prev) / prev < 0.05:
            passed = False
        if avg_vol == 0 or volume < 3 * avg_vol:
            passed = False
        if not self.data_api.has_recent_positive_news(sym, hours=48):
            passed = False

        return {
            **row,
            "open_price": quote["price"] - quote["change"],
            "avg_volume": avg_vol,
            "volume_pct": rel_vol_pct,
            "float": float_shares,
            "passed": passed,
        }

    async def _run_scanner(self) -> list[dict]:
        if self.exit_event.is_set():
            return []

        gainers = self.data_api.fetch_top_movers(limit=50)
        if self.exit_event.is_set():
            return []

        tasks = [asyncio.to_thread(self._check_scan_symbol, row) for row in gainers]
        results = []
        for coro in asyncio.as_completed(tasks):
            if self.exit_event.is_set():
                break
            data = await coro
            if data is not None:
                results.append(data)

        self.top_gainers = results
        cache.save_gainers_cache(results)
        return [r for r in results if r.get("passed")]

    async def scanner_loop(self, interval: float = 60.0) -> None:
        log.debug("scanner_loop start")
        self.scanner_results = cache.load_scanner_cache()
        self.top_gainers = cache.load_gainers_cache()
        while not self.exit_event.is_set():
            try:
                results = await self._run_scanner()
                self.scanner_results = results
                cache.save_scanner_cache(results)
            except Exception as exc:
                log.error(f"[scanner] {exc}")

            try:
                await asyncio.wait_for(self.exit_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

        log.debug("scanner_loop exit")
