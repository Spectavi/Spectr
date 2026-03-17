import json

import spectr.agent as agent


class DummyOpenAI:
    def __init__(self, api_key=None):
        pass


class FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.function = FakeFunction(name, arguments)


class FakeMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    def model_dump(self):
        payload = {"role": "assistant", "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in self.tool_calls
            ]
        return payload


class FakeCompletion:
    def __init__(self, message):
        self.choices = [type("Choice", (), {"message": message})()]


class FakeChatCompletions:
    def __init__(self, messages):
        self._messages = list(messages)

    def create(self, **kwargs):
        message = self._messages.pop(0)
        return FakeCompletion(message)


class FakeClient:
    def __init__(self, messages):
        self.chat = type(
            "Chat",
            (),
            {"completions": FakeChatCompletions(messages)},
        )()


def _patch_audio_init(monkeypatch):
    if agent.pygame is None:
        fake_mixer = type("FakeMixer", (), {"init": staticmethod(lambda: None)})()
        monkeypatch.setattr(agent, "pygame", type("FakePygame", (), {"mixer": fake_mixer})())
    else:
        monkeypatch.setattr(agent.pygame.mixer, "init", lambda: None)


def test_stop_clears_event(monkeypatch):
    monkeypatch.setattr(agent, "OpenAI", DummyOpenAI)
    _patch_audio_init(monkeypatch)
    va = agent.VoiceAgent()
    va._stop_event.set()
    va.stop()
    assert not va._stop_event.is_set()


def test_strategy_code_tool_wiring(monkeypatch):
    monkeypatch.setattr(agent, "OpenAI", DummyOpenAI)
    _patch_audio_init(monkeypatch)

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
    _patch_audio_init(monkeypatch)

    va = agent.VoiceAgent()
    prompt = va.system_prompt
    assert "display_markdown" in prompt
    assert "asks to \"see\" or be \"shown\"" in prompt


def test_wants_markdown_for_show_or_see(monkeypatch):
    monkeypatch.setattr(agent, "OpenAI", DummyOpenAI)
    _patch_audio_init(monkeypatch)

    va = agent.VoiceAgent()
    assert va._wants_markdown("Show me the latest news") is True
    assert va._wants_markdown("Can I see the summary?") is True
    assert va._wants_markdown("Summarize the latest news") is False


def test_build_news_markdown(monkeypatch):
    monkeypatch.setattr(agent, "OpenAI", DummyOpenAI)
    _patch_audio_init(monkeypatch)

    va = agent.VoiceAgent()
    latest = "Nvidia headlines (2024-01-01) https://example.com"
    recent = [
        {"title": "Story A", "date": "2024-01-02", "link": "https://a.example.com"}
    ]
    markdown, title = va._build_news_markdown(latest, recent, "NVDA")
    assert title == "NVDA News Summary"
    assert "Summary" in markdown
    assert "Sources" in markdown
    assert "[Story A](https://a.example.com) (2024-01-02)" in markdown


def test_ask_with_text_show_request_forces_markdown(monkeypatch):
    monkeypatch.setattr(agent, "OpenAI", DummyOpenAI)
    _patch_audio_init(monkeypatch)

    markdown_calls = []

    def _show_markdown(markdown, title=None):
        markdown_calls.append((markdown, title))
        return {"status": "shown"}

    va = agent.VoiceAgent(show_markdown=_show_markdown)
    va.client = FakeClient([FakeMessage(content="Here are the links you asked for.")])

    reply = va.ask_with_text("show me the 5 most recent links to news stories about NVDA", speak=False)

    assert reply == "Here are the links you asked for."
    assert len(markdown_calls) == 1
    assert markdown_calls[0][0] == "Here are the links you asked for."
    assert markdown_calls[0][1] is None


def test_ask_with_text_show_request_builds_news_markdown(monkeypatch):
    monkeypatch.setattr(agent, "OpenAI", DummyOpenAI)
    _patch_audio_init(monkeypatch)

    markdown_calls = []

    def _show_markdown(markdown, title=None):
        markdown_calls.append((markdown, title))
        return {"status": "shown"}

    va = agent.VoiceAgent(show_markdown=_show_markdown)
    va._summarize_recent_news = lambda sources, symbol: "Recent NVDA coverage is mixed. [1]"
    va.tool_funcs["get_recent_news"] = lambda symbol, days=30: json.dumps(
        [{"title": "Story A", "date": "2026-03-17", "link": "https://a.example.com"}]
    )
    va.client = FakeClient(
        [
            FakeMessage(
                tool_calls=[
                    FakeToolCall(
                        "call_1",
                        "get_recent_news",
                        json.dumps({"symbol": "NVDA", "days": 7}),
                    )
                ]
            ),
            FakeMessage(content="Here is the latest NVDA summary."),
        ]
    )

    reply = va.ask_with_text("show me a summarization of the latest news about NVDA", speak=False)

    assert reply == "Here is the latest NVDA summary."
    assert len(markdown_calls) == 1
    markdown, title = markdown_calls[0]
    assert title == "NVDA News Summary"
    assert "Summary" in markdown
    assert "Sources" in markdown
    assert "[Story A](https://a.example.com) (2026-03-17)" in markdown
