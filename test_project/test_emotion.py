import os
import pytest


if os.getenv("RUN_EMOTION_TEST") != "1":
    pytest.skip("Emotionstest ist manuell (Audio/Model-Download).", allow_module_level=True)


def test_emotion_detection():
    from speechbrain.inference.interfaces import foreign_class
    import sounddevice as sd
    import soundfile as sf
    import torch

    if tuple(int(v) for v in torch.__version__.split(".")[:2]) < (2, 6):
        pytest.skip("Torch >= 2.6 erforderlich wegen Sicherheitsfix.")

    run_opts = {"device": "cuda" if torch.cuda.is_available() else "cpu"}

    fs = 16000
    audio = sd.rec(int(1 * fs), samplerate=fs, channels=1)
    sd.wait()
    sf.write("/tmp/test_emotion.wav", audio, fs)

    classifier = foreign_class(
        source="speechbrain/emotion-recognition-wav2vec2-IEMOCAP",
        pymodule_file="custom_interface.py",
        classname="CustomEncoderWav2vec2Classifier",
        run_opts=run_opts,
    )

    _out_prob, score, _index, text_lab = classifier.classify_file("/tmp/test_emotion.wav")
    assert text_lab
    assert score is not None