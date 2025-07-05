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
