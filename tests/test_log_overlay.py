from types import SimpleNamespace

import spectr.spectr as spectr
from spectr.spectr import SpectrApp
import asyncio


class _StubEvent(SimpleNamespace):
    stopped: bool = False

    def stop(self):
        self.stopped = True


class _StubScreen:
    def __init__(self, *, id=None):
        self.id = id


def _build_app(monkeypatch):
    app = SimpleNamespace(
        confirm_quit=False,
        overlay=None,
        log_screen=None,
        screen_stack=[],
    )

    def install_screen(screen, name):
        app.installed = (screen, name)

    def push_screen(screen):
        app.pushed = screen
        app.screen_stack.append(screen)

    def pop_screen():
        app.popped = True
        app.screen_stack.pop()

    app.install_screen = install_screen
    app.push_screen = push_screen
    app.pop_screen = pop_screen
    app.action_toggle_log_overlay = lambda: SpectrApp.action_toggle_log_overlay(app)
    monkeypatch.setattr(spectr, "ErrorLogScreen", _StubScreen)
    return app


def test_tilde_key_pushes_log_screen(monkeypatch):
    app = _build_app(monkeypatch)
    event = _StubEvent(key="`", character="`")

    asyncio.run(SpectrApp.on_key(app, event))

    assert isinstance(app.log_screen, _StubScreen)
    assert app.pushed is app.log_screen
    assert app.screen_stack[-1] is app.log_screen
    assert event.stopped is True


def test_shift_tilde_key_pops_when_open(monkeypatch):
    app = _build_app(monkeypatch)
    app.log_screen = _StubScreen()
    app.screen_stack.append(app.log_screen)
    event = _StubEvent(key="~", character="~")

    asyncio.run(SpectrApp.on_key(app, event))
    # App should leave the existing log screen alone so the screen can handle
    # the key itself.
    assert app.screen_stack[-1] is app.log_screen
    assert getattr(app, "popped", False) is False
    assert event.stopped is False


def test_character_key_variation(monkeypatch):
    app = _build_app(monkeypatch)
    event = _StubEvent(key="grave", character="`")

    asyncio.run(SpectrApp.on_key(app, event))

    assert app.pushed is app.log_screen
    assert event.stopped is True
