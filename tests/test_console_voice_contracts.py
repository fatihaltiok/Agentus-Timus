import deal

from utils.voice_text import normalize_tts_text


@deal.post(lambda result: isinstance(result, str))
@deal.post(lambda result: len(result) <= 503)
def _normalized(text: str) -> str:
    return normalize_tts_text(text)


def test_normalize_tts_text_strips_and_caps_length():
    assert _normalized("  hallo  ") == "hallo"
    assert _normalized("") == ""
    assert len(_normalized("x" * 700)) == 503
