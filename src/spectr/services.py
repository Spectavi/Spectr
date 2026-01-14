from __future__ import annotations

import asyncio
import logging
from enum import Enum
from typing import Callable, Iterable


class ServiceState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class PausableService:
    """Async service with cooperative pause/resume support."""

    def __init__(
        self,
        name: str,
        exit_event: asyncio.Event,
        logger: logging.Logger | None = None,
    ) -> None:
        self.name = name
        self._exit_event = exit_event
        self._pause_event = asyncio.Event()
        self._pause_event.set()
        self._task: asyncio.Task | None = None
        self._log = logger or logging.getLogger(__name__)
        self.state = ServiceState.STOPPED

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run_wrapper())
        self.state = ServiceState.RUNNING

    def pause(self) -> None:
        if self._task and not self._task.done():
            self._pause_event.clear()
            self.state = ServiceState.PAUSED

    def resume(self) -> None:
        if self._task and not self._task.done():
            self._pause_event.set()
            self.state = ServiceState.RUNNING

    def stop(self) -> None:
        if self._task:
            self._task.cancel()
        self._task = None
        self._pause_event.set()
        self.state = ServiceState.STOPPED

    async def _run_wrapper(self) -> None:
        self._log.info("%s service start", self.name)
        try:
            await self._run()
        except asyncio.CancelledError:
            pass
        except Exception:
            self._log.exception("%s service error", self.name)
        finally:
            self.state = ServiceState.STOPPED
            self._log.info("%s service exit", self.name)

    async def _wait_until_resumed(self) -> bool:
        while not self._pause_event.is_set():
            if self._exit_event.is_set():
                return False
            done, pending = await asyncio.wait(
                [self._pause_event.wait(), self._exit_event.wait()],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if self._exit_event.is_set():
                return False
        return True

    async def _sleep_or_exit(self, timeout: float) -> bool:
        try:
            await asyncio.wait_for(self._exit_event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        return True

    async def _run(self) -> None:
        raise NotImplementedError


class LivePollingService(PausableService):
    def __init__(
        self,
        *,
        exit_event: asyncio.Event,
        get_symbols: Callable[[], Iterable[str]],
        poll_symbol_cb: Callable[[str, dict | None, object | None], None],
        data_api,
        broker_api,
        interval: float,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__("polling", exit_event, logger=logger)
        self._get_symbols = get_symbols
        self._poll_symbol_cb = poll_symbol_cb
        self._data_api = data_api
        self._broker_api = broker_api
        self._interval = interval

    async def _run(self) -> None:
        while not self._exit_event.is_set():
            if not await self._wait_until_resumed():
                break

            symbols = list(self._get_symbols())
            if not symbols:
                if await self._sleep_or_exit(self._interval):
                    break
                continue

            try:
                quotes = self._data_api.fetch_quotes(list(symbols))
            except Exception as exc:
                self._log.error("[poll] batch quote error: %s", exc)
                quotes = {sym: None for sym in symbols}

            try:
                positions = self._broker_api.get_positions() or []
            except Exception as exc:
                self._log.warning("Failed to fetch positions: %s", exc)
                positions = []

            pos_map = {
                getattr(pos, "symbol", "").upper(): pos for pos in positions or []
            }

            tasks = [
                asyncio.to_thread(
                    self._poll_symbol_cb,
                    sym,
                    quotes.get(sym.upper()),
                    pos_map.get(sym.upper()),
                )
                for sym in symbols
            ]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            if await self._sleep_or_exit(self._interval):
                break


class EquityService(PausableService):
    def __init__(
        self,
        *,
        exit_event: asyncio.Event,
        update_cb: Callable[[], None],
        interval: float,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__("equity", exit_event, logger=logger)
        self._update_cb = update_cb
        self._interval = interval

    async def _run(self) -> None:
        while not self._exit_event.is_set():
            if not await self._wait_until_resumed():
                break
            try:
                await asyncio.to_thread(self._update_cb)
            except Exception as exc:
                self._log.error("[equity] %s", exc)

            if await self._sleep_or_exit(self._interval):
                break


class ScannerService:
    def __init__(
        self,
        *,
        exit_event: asyncio.Event,
        scanner,
        interval: float,
        logger: logging.Logger | None = None,
    ) -> None:
        self.name = "scanner"
        self._exit_event = exit_event
        self._scanner = scanner
        self._interval = interval
        self._log = logger or logging.getLogger(__name__)
        self._task: asyncio.Task | None = None
        self.state = ServiceState.STOPPED

    def update_scanner(self, scanner) -> None:
        self._scanner = scanner

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._run())
        self.state = ServiceState.RUNNING

    def pause(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        self._task = None
        self.state = ServiceState.PAUSED

    def resume(self) -> None:
        self.start()

    def stop(self) -> None:
        self.pause()
        self.state = ServiceState.STOPPED

    async def _run(self) -> None:
        self._log.info("%s service start", self.name)
        try:
            await self._scanner.scanner_loop(interval=self._interval)
        except asyncio.CancelledError:
            pass
        except Exception:
            self._log.exception("%s service error", self.name)
        finally:
            if self.state != ServiceState.PAUSED:
                self.state = ServiceState.STOPPED
            self._log.info("%s service exit", self.name)
