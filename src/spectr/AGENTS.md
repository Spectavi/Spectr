# AGENTS Guide for Spectr

This repository hosts **Spectr**, a terminal-based algorithmic trading tool built with Python 3.10+.
The project is packaged via `pyproject.toml` and source code lives inside the `src/` directory.

## Directory overview

- `src/spectr/` – main package
  - `cli.py` – command line entry point (`spectr` command)
  - `spectr.py` – core Textual app
  - `agent.py` – optional voice agent features
  - `fetch/` – broker and data API interfaces
  - `strategies/` – trading strategies
  - `scanners/` – stock scanners
  - `views/` – Textual UI components
  - `res/` – images, audio, and other static assets
- `tests/` – pytest unit tests validating broker tools, interfaces, and strategies
- `pyproject.toml` – packaging configuration

## Contribution notes

- Follow PEP8 conventions; run `black` on modified files before committing.
- Add any new dependencies to both `pyproject.toml` and `requirements.txt`.
- Place additional tests under `tests/` and run `pytest` before committing.
- UI additions belong in `src/spectr/views`; new strategies go in `src/spectr/strategies`.

## Running tests

Use `pytest` from the repository root:

```bash
pytest
```

All tests should succeed before submitting changes.