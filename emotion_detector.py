"""
Emotion Detector für Timus
Erkennt Emotionen aus Sprache mittels SpeechBrain
"""
import numpy as np
import torch
import soundfile as sf
import tempfile
import os

class EmotionDetector:
    def __init__(self):
        self.classifier = None
        self.emotion_map = {
            "NEU": "neutral",
            "HAP": "happy", 
            "SAD": "sad",
            "ANG": "angry"
        }
        self._load_model()
    
    def _load_model(self):
        try:
            from speechbrain.inference.interfaces import foreign_class
            
            # CPU nutzen weil GPU voll mit Moondream
            run_opts = {"device": "cpu"}
            
            self.classifier = foreign_class(
                source="speechbrain/emotion-recognition-wav2vec2-IEMOCAP",
                pymodule_file="custom_interface.py",
                classname="CustomEncoderWav2vec2Classifier",
                run_opts=run_opts
            )
            print(f"✅ Emotion Detector geladen (auf CPU)")
        except Exception as e:
            print(f"⚠️ Emotion Detector nicht verfügbar: {e}")
    
    def detect_from_file(self, audio_path: str) -> dict:
        """Erkennt Emotion aus Audio-Datei."""
        if not self.classifier:
            return {"emotion": "unknown", "confidence": 0.0}
        
        try:
            # SpeechBrain Analyse
            out_prob, score, index, text_lab = self.classifier.classify_file(audio_path)
            
            # Bugfix: text_lab ist eine Liste ['NEU'], wir brauchen das erste Element
            label_key = text_lab[0] if isinstance(text_lab, list) else text_lab
            
            # Confidence berechnen (Tensor zu Float wandeln)
            if hasattr(score, "__iter__"):
                confidence = score[0].item() if hasattr(score[0], "item") else float(score[0])
            else:
                confidence = score.item() if hasattr(score, "item") else float(score)
            
            emotion = self.emotion_map.get(label_key, "neutral")
            
            return {
                "emotion": emotion,
                "confidence": confidence,
                "raw_label": label_key
            }
        except Exception as e:
            print(f"Fehler bei Emotion Detection: {e}")
            return {"emotion": "error", "confidence": 0.0, "error": str(e)}
    
    def detect_from_array(self, audio_array: np.ndarray, sample_rate: int = 16000) -> dict:
        """Erkennt Emotion aus Audio-Array (z.B. direkt vom Mikrofon)."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            temp_name = f.name
            
        try:
            if len(audio_array.shape) > 1:
                audio_array = audio_array.flatten()
            
            sf.write(temp_name, audio_array, sample_rate)
            result = self.detect_from_file(temp_name)
        finally:
            if os.path.exists(temp_name):
                os.remove(temp_name)
                
        return result
    
    def get_response_style(self, emotion: str) -> dict:
        """Gibt Antwort-Stil basierend auf Emotion zurück."""
        styles = {
            "happy": {"tone": "enthusiastic", "prefix": "Das freut mich! 😊 ", "emoji": "😊"},
            "sad": {"tone": "empathetic", "prefix": "Oje, das klingt nicht gut. ", "emoji": "😔"},
            "angry": {"tone": "calm", "prefix": "Ganz ruhig, ich bin ja da. ", "emoji": "😤"},
            "neutral": {"tone": "professional", "prefix": "", "emoji": "🙂"}
        }
        return styles.get(emotion, styles["neutral"])

_detector = None

def get_emotion_detector() -> EmotionDetector:
    global _detector
    if _detector is None:
        _detector = EmotionDetector()
    return _detector