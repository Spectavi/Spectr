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


def test_system_prompt_mentions_show_markdown_for_visual_requests(monkeypatch):
    monkeypatch.setattr(agent, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(agent.pygame.mixer, "init", lambda: None)

    va = agent.VoiceAgent()
    prompt = va.system_prompt
    assert "display_markdown" in prompt
    assert "asks to \"see\" or be \"shown\"" in prompt


def test_wants_markdown_for_show_or_see(monkeypatch):
    monkeypatch.setattr(agent, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(agent.pygame.mixer, "init", lambda: None)

    va = agent.VoiceAgent()
    assert va._wants_markdown("Show me the latest news") is True
    assert va._wants_markdown("Can I see the summary?") is True
    assert va._wants_markdown("Summarize the latest news") is False


def test_build_news_markdown(monkeypatch):
    monkeypatch.setattr(agent, "OpenAI", DummyOpenAI)
    monkeypatch.setattr(agent.pygame.mixer, "init", lambda: None)

    va = agent.VoiceAgent()
    latest = "Nvidia headlines (2024-01-01) https://example.com"
    recent = [
        {"title": "Story A", "date": "2024-01-02", "link": "https://a.example.com"}
    ]
    markdown, title = va._build_news_markdown(latest, recent, "NVDA")
    assert title == "NVDA News"
    assert "Latest headline" in markdown
    assert "- Nvidia headlines" in markdown
    assert "[Story A](https://a.example.com) (2024-01-02)" in markdown
