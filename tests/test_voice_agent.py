import json

import spectr.agent as agent


class DummyOpenAI:
    def __init__(self, api_key=None):
        pass


def test_stop_clears_event(monkeypatch):
    monkeypatch.setattr(agent, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(agent.pygame.mixer, "init", lambda: None)
    va = agent.VoiceAgent()
    va._stop_event.set()
    va.stop()
    assert not va._stop_event.is_set()


def test_strategy_code_tool_wiring(monkeypatch):
    monkeypatch.setattr(agent, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(agent.pygame.mixer, "init", lambda: None)

    calls = {"count": 0}

    def _get_strategy_code():
        calls["count"] += 1
        return "class Foo: pass"

    va = agent.VoiceAgent(get_strategy_code=_get_strategy_code)
    tool_names = [tool["function"]["name"] for tool in va.tools]
    assert "get_strategy_code" in tool_names
    assert json.loads(va.tool_funcs["get_strategy_code"]()) == "class Foo: pass"
    assert calls["count"] == 1
