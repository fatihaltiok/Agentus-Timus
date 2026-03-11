from types import SimpleNamespace

from server import mcp_server


class _FakeVoiceEngine:
    def __init__(self):
        self._initialized = True
        self.is_listening = False
        self.is_speaking = False
        self.config = SimpleNamespace(inworld_voice="Lennart")

    def get_available_voices(self):
        return {"de": ["Lennart", "Ashley"]}

    def synthesize_mp3(self, text, voice=None):
        if not text:
            return None
        return b"ID3fake-mp3"

    async def transcribe_audio_bytes_async(self, audio_bytes, audio_format=None):
        if not audio_bytes:
            return ""
        return f"transcribed:{audio_format or 'unknown'}"


async def test_voice_status_endpoint_includes_current_voice(monkeypatch):
    fake_engine = _FakeVoiceEngine()
    monkeypatch.setattr("tools.voice_tool.tool.voice_engine", fake_engine)

    data = await mcp_server.voice_status_endpoint()

    assert data["status"] == "success"
    assert data["voice"]["current_voice"] == "Lennart"
    assert "de" in data["voice"]["available_voices"]


async def test_voice_synthesize_endpoint_returns_audio(monkeypatch):
    fake_engine = _FakeVoiceEngine()
    monkeypatch.setattr("tools.voice_tool.tool.voice_engine", fake_engine)

    response = await mcp_server.voice_synthesize_endpoint({"text": "Hallo Timus"})

    assert response.media_type == "audio/mpeg"
    assert response.body == b"ID3fake-mp3"


async def test_voice_transcribe_endpoint_returns_text(monkeypatch):
    fake_engine = _FakeVoiceEngine()
    monkeypatch.setattr("tools.voice_tool.tool.voice_engine", fake_engine)

    class _FakeUpload:
        filename = "voice-input.webm"

        async def read(self):
            return b"webm-audio"

    class _FakeRequest:
        headers = {"content-type": "multipart/form-data; boundary=test"}

        async def form(self):
            return {"file": _FakeUpload()}

    response = await mcp_server.voice_transcribe_endpoint(_FakeRequest())

    assert response["status"] == "success"
    assert response["text"] == "transcribed:webm"
