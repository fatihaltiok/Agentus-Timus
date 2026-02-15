# tools/engines/qwen_vl_engine.py (Qwen2.5-VL Vision Language Model Engine)
"""
Qwen2.5-VL Vision Language Model Engine für UI-Automation und Web-Navigation.

Features:
- RTX 3090 GPU Optimierung (CUDA, bfloat16)
- Strukturierte JSON-Aktionen für UI-Automation
- Screenshot-Analyse mit Koordinaten-Extraktion
- Singleton-Pattern für effizientes Model-Loading

Konfiguration per .env:
    QWEN_VL_MODEL=Qwen/Qwen2.5-VL-7B-Instruct  # oder 3B-Instruct
    QWEN_VL_DEVICE=cuda  # auto, cuda, cpu
    QWEN_VL_MAX_TOKENS=512
    QWEN_VL_SCREENSHOT_SIZE=1920,1080
"""

import logging
import os
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from PIL import Image
import torch

from tools.shared_context import log

# Transformers Import mit Fehlerbehandlung
try:
    from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False
    log.error("KRITISCH: 'transformers' nicht installiert. QwenVLEngine nicht verfügbar.")
    Qwen2VLForConditionalGeneration, AutoProcessor = None, None


@dataclass
class UIAction:
    """Strukturierte UI-Aktion vom VLM"""
    action: str  # click, type, press, scroll_up, scroll_down, wait, done
    x: Optional[int] = None
    y: Optional[int] = None
    text: Optional[str] = None
    key: Optional[str] = None
    seconds: Optional[float] = None
    confidence: float = 1.0


class QwenVLEngine:
    """
    Singleton-Klasse für Qwen2.5-VL Vision Language Model.
    Optimiert für RTX 3090 mit bfloat16 und CUDA.
    """
    _instance = None

    def __new__(cls):
        if not cls._instance:
            cls._instance = super(QwenVLEngine, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, 'initialized'):
            return

        # Konfiguration aus .env
        # Qwen2-VL Modelle (kompatibel mit transformers 4.45+):
        # - Qwen/Qwen2-VL-2B-Instruct (schnell, ~4GB VRAM geladen, ~8GB Inferenz)
        # - Qwen/Qwen2-VL-7B-Instruct (besser, ~14GB VRAM geladen, ~20GB Inferenz)
        self.model_name = os.getenv("QWEN_VL_MODEL", "Qwen/Qwen2-VL-2B-Instruct")
        self.device_setting = os.getenv("QWEN_VL_DEVICE", "auto")
        self.max_tokens = int(os.getenv("QWEN_VL_MAX_TOKENS", "512"))
        # 1536x864 = Kompromiss aus Präzision und VRAM (~6-7GB Inferenz)
        self.screenshot_size = self._parse_size(os.getenv("QWEN_VL_SCREENSHOT_SIZE", "1536,864"))
        
        # Modell-Instanzen
        self.model = None
        self.processor = None
        self.device = None
        
        # Status
        self.initialized = False
        self.model_loaded = False
        
        log.info(f"🔧 QwenVLEngine Konfiguration: model={self.model_name}, device={self.device_setting}")

    def _parse_size(self, size_str: str) -> Tuple[int, int]:
        """Parst Größen-String wie '1920,1080'"""
        try:
            width, height = map(int, size_str.split(','))
            return (width, height)
        except:
            return (1920, 1080)

    def initialize(self):
        """
        Lädt Qwen2.5-VL Modell in die GPU (RTX 3090).
        Wird vom mcp_server beim Start aufgerufen.
        """
        if self.initialized:
            log.info("QwenVLEngine ist bereits initialisiert.")
            return

        if not TRANSFORMERS_AVAILABLE:
            log.error("Transformers nicht verfügbar. QwenVLEngine kann nicht initialisieren.")
            return

        # Device bestimmen
        if self.device_setting == "auto":
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = self.device_setting

        log.info(f"🚀 Lade Qwen2.5-VL Modell: {self.model_name}")
        log.info(f"   Device: {self.device}")
        
        if self.device == "cuda":
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / 1e9
            log.info(f"   GPU: {gpu_name} ({gpu_memory:.1f} GB)")

        try:
            # Tokenizer/Processor laden
            log.info("📥 Lade Processor...")
            self.processor = AutoProcessor.from_pretrained(
                self.model_name,
                trust_remote_code=True
            )

            # Modell mit Optimierungen laden
            log.info("📥 Lade Modell (das kann einen Moment dauern)...")
            
            # 8-bit Quantization Check
            use_8bit = os.getenv("QWEN_VL_8BIT", "0") == "1"
            
            dtype = None  # Initialisiere dtype
            
            if use_8bit and self.device == "cuda":
                # 8-bit Quantization - spart 50% VRAM
                log.info("   Using 8-bit quantization (spart ~50% VRAM)")
                try:
                    self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                        self.model_name,
                        load_in_8bit=True,
                        device_map="auto",
                        trust_remote_code=True,
                        low_cpu_mem_usage=True
                    )
                    log.info("   ✅ 8-bit Modell geladen")
                except Exception as e:
                    log.warning(f"   ⚠️ 8-bit fehlgeschlagen: {e}")
                    log.warning("   Fallback zu Standard-16bit...")
                    use_8bit = False
            
            if not use_8bit:
                # Standard 16-bit Loading
                if self.device == "cuda" and torch.cuda.is_bf16_supported():
                    dtype = torch.bfloat16
                    log.info("   Using bfloat16 für optimale RTX 3090 Performance")
                elif self.device == "cuda":
                    dtype = torch.float16
                    log.info("   Using float16")
                else:
                    dtype = torch.float32
                    log.info("   Using float32 (CPU)")

                self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                    self.model_name,
                    torch_dtype=dtype,
                    trust_remote_code=True,
                    low_cpu_mem_usage=True
                )
                
                # Explizit auf GPU/CPU verschieben (vermeidet device_map Probleme)
                if self.device == "cuda":
                    self.model = self.model.to("cuda")
                else:
                    self.model = self.model.to("cpu")

            self.model.eval()  # Inference-Modus
            
            self.initialized = True
            self.model_loaded = True
            
            log.info(f"✅ QwenVLEngine erfolgreich initialisiert!")
            log.info(f"   Modell: {self.model_name}")
            log.info(f"   Device: {self.device}")
            log.info(f"   Dtype: {dtype}")
            
            # VRAM-Info
            if self.device == "cuda":
                vram_used = torch.cuda.memory_allocated() / 1e9
                vram_total = torch.cuda.get_device_properties(0).total_memory / 1e9
                log.info(f"   VRAM: {vram_used:.1f} GB / {vram_total:.1f} GB")

        except Exception as e:
            self.initialized = False
            log.error(f"❌ Fehler beim Laden des Qwen-VL Modells: {e}", exc_info=True)

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Bereitet Screenshot für das Modell vor.
        Konvertiert zu RGB und resize zur konsistenten Größe.
        """
        img = image.convert("RGB")
        if img.size != self.screenshot_size:
            img = img.resize(self.screenshot_size, Image.Resampling.LANCZOS)
        return img

    def _cleanup_memory(self):
        """Bereinigt GPU-Speicher vor Inferenz (verhindert OOM durch Fragmentierung)."""
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            # FFT-Cache auch leeren
            if hasattr(torch.backends.cuda, 'cufft_plan_cache'):
                torch.backends.cuda.cufft_plan_cache.clear()
    
    def analyze_screenshot(
        self,
        image: Image.Image,
        task: str,
        history: Optional[List[Dict]] = None,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Analysiert Screenshot und gibt strukturierte UI-Aktionen zurück.
        
        Args:
            image: PIL Image (Screenshot)
            task: Aktuelle Aufgabenbeschreibung
            history: Liste vorheriger Aktionen für Kontext
            system_prompt: Optionaler benutzerdefinierter System-Prompt
            
        Returns:
            {
                "success": bool,
                "actions": List[UIAction],
                "raw_response": str,
                "error": Optional[str]
            }
        """
        # Lazy Loading: Initialisiere bei erster Nutzung
        if not self.initialized or not self.model:
            log.info("🔄 Qwen-VL wird on-demand geladen (Lazy Loading)...")
            self.initialize()
            if not self.initialized:
                return {
                    "success": False,
                    "actions": [],
                    "raw_response": "",
                    "error": "QwenVLEngine Initialisierung fehlgeschlagen"
                }

        # WICHTIG: Speicher bereinigen vor Inferenz!
        self._cleanup_memory()
        
        try:
            # Bild vorverarbeiten
            processed_img = self.preprocess_image(image)
            
            # Standard System Prompt für UI-Automation
            if system_prompt is None:
                system_prompt = self._get_default_system_prompt(task, history)
            # Bei benutzerdefiniertem Prompt: Keine .format() da geschweifte Klammern im JSON sind

            # Nachrichten erstellen
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "image", "image": processed_img},
                    {"type": "text", "text": f"Analysiere den Screenshot für die Aufgabe: {task}\nGib die nächste Aktion(en) als JSON-Array zurück."}
                ]}
            ]

            # Inference
            effective_max_tokens = max_tokens if max_tokens is not None else self.max_tokens
            log.info(f"🧠 Qwen-VL Analyse läuft... (max_tokens={effective_max_tokens})")

            text = self.processor.apply_chat_template(messages, add_generation_prompt=True)
            inputs = self.processor(
                text=[text],
                images=[processed_img],
                return_tensors="pt",
                padding=True
            ).to(self.device)

            # Generate mit optimierten Parametern
            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=effective_max_tokens,
                    do_sample=False,  # Deterministisch für UI-Automation
                    temperature=None,
                    top_p=None,
                    pad_token_id=self.processor.tokenizer.pad_token_id
                )
            
            # Decode Output
            generated_ids = generated_ids[0][inputs.input_ids.shape[1]:]
            output = self.processor.decode(generated_ids, skip_special_tokens=True)
            
            # VRAM freigeben nach Inferenz
            if self.device == "cuda":
                del inputs, generated_ids
                torch.cuda.empty_cache()
            
            log.info(f"📝 Raw Output: {output[:200]}...")
            
            # Parse JSON Actions
            actions = self._parse_actions(output)
            
            return {
                "success": True,
                "actions": actions,
                "raw_response": output,
                "error": None
            }

        except Exception as e:
            log.error(f"❌ Fehler bei Qwen-VL Analyse: {e}", exc_info=True)
            return {
                "success": False,
                "actions": [],
                "raw_response": "",
                "error": str(e)
            }

    def _get_default_system_prompt(self, task: str, history: Optional[List[Dict]]) -> str:
        """Optimiertes System Prompt für UI-Automation mit präziser Done-Erkennung"""
        history_str = self._format_history(history)
        has_history = bool(history)

        history_warning = ""
        if has_history:
            history_warning = """
=== BEREITS AUSGEFUEHRTE AKTIONEN (NICHT WIEDERHOLEN!) ===
{history}
DIESE AKTIONEN WURDEN SCHON AUSGEFUEHRT! Wiederhole sie NICHT!
Schaue auf den Screenshot und entscheide was als NAECHSTES passieren muss.
Wenn die Aufgabe bereits erledigt aussieht, antworte mit [{{"action": "done"}}].
""".format(history=history_str)

        return f"""Du bist ein Browser-GUI-Agent. Analysiere den Screenshot und gib die NAECHSTE Aktion zurueck.

Aufgabe: {task}
{history_warning}
AUFLOESUNG: 1920x1080 Pixel. Koordinaten: (0,0) = oben links.

ANTWORT FORMAT - NUR JSON, KEINE Erklaerungen:
[{{"action": "click", "x": 500, "y": 300}}]

AKTIONEN: click(x,y), type(text), press(key), scroll_up, scroll_down, wait(seconds), done

REGELN:
1. Maximal 3 Aktionen pro Antwort
2. Wenn die Aufgabe ERLEDIGT aussieht: [{{"action": "done"}}]
3. NIEMALS vorherige Aktionen wiederholen
4. Schaue genau auf den Screenshot - was ist JETZT zu sehen?

NUR JSON!"""

    def _format_history(self, history: Optional[List[Dict]]) -> str:
        """Formatiert Aktions-History fuer Prompt - kompakt und klar"""
        if not history:
            return "Keine vorherigen Aktionen."

        lines = []
        for i, action in enumerate(history[-6:], 1):  # Letzte 6 Aktionen
            act = action.get("action", "?")
            parts = [act]
            if action.get("x") and action.get("y"):
                parts.append(f"({action['x']},{action['y']})")
            if action.get("text"):
                parts.append(f"'{action['text'][:30]}'")
            if action.get("key"):
                parts.append(action["key"])
            lines.append(f"  Schritt {i}: {' '.join(parts)}")
        return "\n".join(lines)

    def _parse_actions(self, output: str) -> List[UIAction]:
        """
        Parst JSON-Aktionen aus Modell-Output.
        Unterstützt verschiedene JSON-Formate, truncated JSON Repair und Fallback-Parsing.
        """
        actions = []

        # Versuche JSON zu finden (kann in ```json ... ``` oder direkt sein)
        json_match = re.search(r'```json\s*(\[.*?\])\s*```', output, re.DOTALL)
        if not json_match:
            json_match = re.search(r'(\[.*?\])', output, re.DOTALL)

        if json_match:
            try:
                data = json.loads(json_match.group(1))
                if not isinstance(data, list):
                    data = [data]

                for item in data:
                    if isinstance(item, dict):
                        actions.append(self._dict_to_action(item))

            except json.JSONDecodeError as e:
                log.warning(f"JSON Parse Error: {e}")

        # Truncated JSON Repair: wenn max_tokens die Antwort abschneidet
        if not actions:
            truncated = re.search(r'(\[.+)', output, re.DOTALL)
            if truncated:
                raw = truncated.group(1).strip()
                # Finde alle vollstaendigen {...} Objekte im abgeschnittenen Array
                obj_matches = re.finditer(r'\{[^{}]+\}', raw)
                for m in obj_matches:
                    try:
                        item = json.loads(m.group(0))
                        if isinstance(item, dict) and "action" in item:
                            actions.append(self._dict_to_action(item))
                    except json.JSONDecodeError:
                        continue
                if actions:
                    log.info(f"🔧 Truncated JSON repariert: {len(actions)} Aktionen extrahiert")

        if not actions:
            # Fallback: Versuche aus Text zu extrahieren
            log.warning("Keine JSON-Aktionen gefunden, verwende Fallback-Parsing")

            # Suche nach Koordinaten im Text
            coord_match = re.search(r'\(?\s*(\d{3,4})\s*[,\s]+\s*(\d{3,4})\s*\)?', output)
            if coord_match:
                x, y = int(coord_match.group(1)), int(coord_match.group(2))
                actions.append(UIAction(action="click", x=x, y=y))

        return actions

    def _dict_to_action(self, item: Dict) -> UIAction:
        """Konvertiert ein Dict zu einer UIAction."""
        return UIAction(
            action=item.get("action", "unknown"),
            x=item.get("x"),
            y=item.get("y"),
            text=item.get("text"),
            key=item.get("key"),
            seconds=item.get("seconds"),
            confidence=item.get("confidence", 1.0)
        )

    def is_initialized(self) -> bool:
        """Gibt zurück ob die Engine initialisiert ist."""
        return self.initialized

    def get_model_info(self) -> Dict[str, Any]:
        """Gibt Modell-Informationen zurück."""
        info = {
            "model_name": self.model_name,
            "initialized": self.initialized,
            "device": self.device,
            "max_tokens": self.max_tokens,
            "screenshot_size": self.screenshot_size
        }
        
        if self.device == "cuda" and torch.cuda.is_available():
            info["gpu_name"] = torch.cuda.get_device_name(0)
            info["vram_total_gb"] = torch.cuda.get_device_properties(0).total_memory / 1e9
            info["vram_used_gb"] = torch.cuda.memory_allocated() / 1e9
        
        return info


# ===== GLOBALE SINGLETON INSTANZ =====
qwen_vl_engine_instance = QwenVLEngine()
log.info(f"✅ QwenVLEngine Singleton erstellt (Modell: {qwen_vl_engine_instance.model_name})")
