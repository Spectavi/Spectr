Spectr Architecture Refactor Plan

Goals
- Clear separation between Live and Backtest modes (no cross‑talk).
- Decouple business logic from UI (rendering becomes a thin layer).
- Improve testability, reliability, and maintainability.

Key Changes (Overview)
- Mode management: Centralize enter/exit logic; pause/resume services atomically.
- Services: Extract polling, scanner, and equity updaters from the App class.
- Store: Unidirectional data flow with a typed state store and events.
- Rendering: Introduce view models and a dedicated renderer around plotext.
- Backtest pipeline: Dedicated service returning immutable reports/models.

Details

1) Mode Separation
- Replace `is_backtest: bool` with `Mode` enum (LIVE, BACKTEST, …).
- Add `ModeManager` that:
  - Starts/stops services (polling/scanner/equity) on mode change.
  - Suspends UI update streams for live views during backtest.
  - Emits structured events for transitions (entered/exited). 
- Isolate backtest into a `BacktestSession` (input + immutable outputs) so UI never touches live caches during results.

2) Services and Lifecycles
- `LivePollingService`: Periodically fetch quotes + historical deltas; detect signals; publish updates per symbol.
- `ScannerService`: Background symbol discovery; publishes changes to the store.
- `EquityService`: Computes/evolves equity curve with cadence; publishes to store.
- Services expose `start()`, `pause()`, `resume()`, `stop()` and are supervised by `ModeManager`.

3) State and Data Flow
- Introduce an `AppStore` typed with dataclasses:
  - `AppState` (mode, active symbol, config, strategy, etc.)
  - `SymbolState` (df, indicators, last quote, signals)
  - `PortfolioState` (cash, positions, orders, equity)
- UI subscribes to store selectors; UI never mutates the store directly.
- Intents/commands (e.g., “set strategy”, “add symbol”) go through a controller that updates the store/services.

4) Rendering and View Models
- `ChartViewModel`: normalized input for charts (x labels, series, overlays, markers, y-range, titles).
- `ChartTransformer`: pure functions from DataFrame(+indicators) → `ChartViewModel`.
- `PlotRenderer`: `render_price(model) -> str`, `render_macd(model) -> str`, etc.; encapsulates plotext usage + global lock.
- Views (Graph/MACD/Volume/Equity) depend only on view models or a renderer call, not raw DataFrames.

5) Backtest Pipeline
- `BacktestService.run(input) -> BacktestReport` where `input` includes symbol, date range, starting cash, strategy + params.
- `BacktestReport`: immutable dataclass with `final_value`, `equity_curve`, `trades`, and `price_slice`.
- Add `BacktestTransformer` to produce `ChartViewModel` for the results screen. UI consumes only report + model.
- Keep indicator analysis (`metrics.analyze_indicators`) centralized so live/backtest stay consistent.

6) Concurrency and Scheduling
- Replace per-widget `set_interval` where possible with a central scheduler or store-driven updates.
- Use `asyncio.TaskGroup`/managed tasks for services; ensure clean cancellation on mode change and shutdown.
- Use an async channel/event bus with coalescing per symbol to avoid unbounded queues.

7) Error Handling and Logging
- Replace blanket `except Exception` with specific exceptions; propagate failures to a central UI/error service.
- Add structured logs on service start/stop and mode transitions.
- Ensure user-facing errors are rendered by a dedicated overlay service (UI stays passive).

8) Types and Config
- Migrate to dataclasses (or Pydantic) for `AppConfig`, strategy params, args snapshot, backtest inputs/outputs.
- Replace `SimpleNamespace` with typed models.
- Use enums/constants for strategy names, intervals, and style tokens.

9) Testing Strategy
- Unit-test services in isolation: polling, repositories, backtest service, renderer.
- Mode transition tests: entering/exiting backtest pauses/resumes services, UI ignores live updates in backtest.
- Snapshot tests for renderer output given deterministic models.
- Contract tests for strategy parameter mapping to guard refactors.

Incremental Migration Steps
1. Introduce `PlotRenderer` + `ChartViewModel`; refactor `GraphView` to use them behind current API.
2. Add `ModeManager`; route all mode transitions through it; remove scattered `is_backtest` branches.
3. Extract `LivePollingService`, `EquityService`, `ScannerService`; wire to `ModeManager`.
4. Introduce `AppStore`/controllers; migrate key flows (symbol changes, set strategy, add/remove symbol).
5. Build `BacktestService` returning `BacktestReport`; adapt results screen to consume report + chart model.
6. Backfill tests for services, mode transitions, and renderer snapshots.

Notes
- The existing global plot lock remains as a safety harness even after introducing the renderer; the renderer should own the lock.
- Keep compatibility shims in `SpectrApp` until migration completes; aim for smaller PRs to keep tests green.

