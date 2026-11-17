"""OpenAI for the voice tests: it hears `heard`, answers `answer`, and keeps
what it was asked."""
import json

import pytest

import app.services.voice_bill as voice_bill


@pytest.fixture
def model(monkeypatch):
    asked = {"answer": {"items": [], "assign": []}, "heard": "", "chat": None, "transcription": None, "options": []}

    class _Transcriptions:
        def create(self, **kwargs):
            asked["transcription"] = kwargs

            class _Text:
                text = asked["heard"]

            return _Text()

    class _Fake:
        def __init__(self):
            self.chat = self
            self.completions = self
            self.audio = self
            self.transcriptions = _Transcriptions()

        def with_options(self, **options):
            asked["options"].append(options)
            return self

        def create(self, **kwargs):
            asked["chat"] = kwargs

            class _Msg:
                content = json.dumps(asked["answer"])

            class _Choice:
                message = _Msg()

            class _Resp:
                choices = [_Choice()]

            return _Resp()

    monkeypatch.setattr(voice_bill, "get_openai_client", lambda: _Fake())
    return asked
