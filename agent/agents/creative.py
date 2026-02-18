"""CreativeAgent - Bilder, kreative Texte (HYBRID: GPT-5.1 + Nemotron)."""

import os
import asyncio
import logging

from agent.base_agent import BaseAgent
from agent.providers import ModelProvider
from agent.prompts import CREATIVE_SYSTEM_PROMPT

log = logging.getLogger("TimusAgent-v4.4")


class CreativeAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(CREATIVE_SYSTEM_PROMPT, tools_description_string, 8, "creative")
        self.tools_description = tools_description_string
        self.nemotron_client = None
        openrouter_key = os.getenv("OPENROUTER_API_KEY")
        if openrouter_key:
            from openai import OpenAI as OpenRouterClient
            self.nemotron_client = OpenRouterClient(
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
            )

    async def _generate_image_prompt_with_gpt(self, user_request: str) -> str:
        log.info("Phase 1: GPT-5.1 generiert detaillierten Bildprompt")

        prompt = f"""Du bist ein Experte fuer DALL-E Bildprompts.
Erstelle einen DETAILLIERTEN, AUSFUEHRLICHEN englischen Bildprompt fuer folgende Anfrage:

"{user_request}"

ANFORDERUNGEN:
- Mindestens 20-30 Woerter
- Beschreibe: Hauptmotiv, Stil, Beleuchtung, Komposition, Details, Stimmung
- Sei spezifisch und inspirierend
- Nutze visuelle Adjektive (z.B. "soft golden lighting", "elegant composition")
- Auf ENGLISCH!

BEISPIEL:
Input: "male eine Katze"
Output: "elegant grey tabby cat sitting on a sunlit windowsill, soft natural lighting streaming through white curtains, detailed fur texture, peaceful expression, minimalist modern interior, shallow depth of field, professional photography style, warm and cozy atmosphere"

NUR DEN PROMPT AUSGEBEN, KEINE ERKLAERUNGEN!"""

        try:
            response = await asyncio.to_thread(
                self.provider_client.get_client(ModelProvider.OPENAI).chat.completions.create,
                model="gpt-5.1",
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,
                max_completion_tokens=200,
            )
            generated_prompt = response.choices[0].message.content.strip()
            log.info(f"GPT-5.1 Prompt: {generated_prompt[:80]}...")
            return generated_prompt
        except Exception as e:
            log.error(f"GPT-5.1 Prompt-Generierung fehlgeschlagen: {e}")
            return f"detailed image of {user_request}, high quality, professional"

    async def _execute_with_nemotron(self, image_prompt: str, size: str = "1024x1024", quality: str = "high") -> dict:
        log.info("Phase 2: Nemotron strukturiert Tool-Call")

        if not self.nemotron_client:
            log.warning("Nemotron nicht verfuegbar, Fallback auf direkte Tool-Ausfuehrung")
            return await self._call_tool("generate_image", {
                "prompt": image_prompt,
                "size": size,
                "quality": quality,
            })

        nemotron_system = f"""Du bist ein praeziser Tool-Executor.

DEINE AUFGABE:
Fuehre generate_image mit den gegebenen Parametern aus.

VERFUEGBARE TOOLS:
{self.tools_description}

FORMAT (EXAKT):
Thought: Ich fuehre generate_image aus.
Action: {{"method": "generate_image", "params": {{"prompt": "...", "size": "...", "quality": "..."}}}}

WICHTIG: NUR das Action-JSON ausgeben, KEINE zusaetzlichen Erklaerungen!"""

        user_message = f"""Fuehre generate_image aus mit:
- prompt: "{image_prompt}"
- size: "{size}"
- quality: "{quality}"

Gib NUR das Action-JSON zurueck!"""

        try:
            response = await asyncio.to_thread(
                self.nemotron_client.chat.completions.create,
                model="nvidia/nemotron-3-nano-30b-a3b",
                messages=[
                    {"role": "system", "content": nemotron_system},
                    {"role": "user", "content": user_message},
                ],
                temperature=0.0,
                max_tokens=1500,
            )

            nemotron_reply = response.choices[0].message.content.strip() if response.choices[0].message.content else ""

            if not nemotron_reply:
                log.warning("Nemotron gab leeren Response zurueck. Fallback zu direktem Call.")
                return await self._call_tool("generate_image", {
                    "prompt": image_prompt,
                    "size": size,
                    "quality": quality,
                })

            log.info(f"Nemotron Output ({len(nemotron_reply)} chars):\n{nemotron_reply[:500]}")

            action, err = self._parse_action(nemotron_reply)

            if not action:
                log.warning(f"Nemotron Action-Parse fehlgeschlagen: {err}")
                log.info("Fallback zu direktem Tool-Call")
                return await self._call_tool("generate_image", {
                    "prompt": image_prompt,
                    "size": size,
                    "quality": quality,
                })

            log.info(f"Tool-Call: {action.get('method')} mit params")
            obs = await self._call_tool(action.get("method", ""), action.get("params", {}))
            return obs

        except Exception as e:
            log.error(f"Nemotron-Ausfuehrung fehlgeschlagen: {e}")
            return await self._call_tool("generate_image", {
                "prompt": image_prompt,
                "size": size,
                "quality": quality,
            })

    @staticmethod
    def _extract_tool_error(observation: dict) -> tuple[bool, str, str]:
        """Normalisiert Fehlererkennung aus Tool-Responses."""
        if not isinstance(observation, dict):
            return True, "Unerwartetes Antwortformat vom Tool.", ""

        status = str(observation.get("status", "") or "").strip().lower()
        error_code = str(observation.get("error_code", "") or "").strip().lower()

        if "error" in observation:
            return True, str(observation.get("error") or "Unbekannter Fehler"), error_code
        if status in {"error", "failed", "failure"}:
            msg = str(
                observation.get("message")
                or observation.get("error")
                or "Unbekannter Fehler"
            )
            return True, msg, error_code
        return False, "", error_code

    @staticmethod
    def _build_safe_retry_prompt(detailed_prompt: str) -> str:
        """Erzeugt einen moderationsfreundlichen Retry-Prompt fuer Bildgenerierung."""
        base = str(detailed_prompt or "").strip()
        safety_clause = (
            "Original fictional character only, no copyrighted or trademarked characters, "
            "no logos, no real persons, no violence, no weapons, family-friendly."
        )
        if base:
            return f"{base}. {safety_clause}"
        return safety_clause

    async def run(self, task: str) -> str:
        log.info(f"{self.__class__.__name__} - HYBRID MODE (GPT-5.1 + Nemotron)")

        task_lower = task.lower()
        is_image_request = any(kw in task_lower for kw in [
            "mal", "bild", "generiere bild", "erstelle bild", "zeichne", "image",
        ])

        if not is_image_request:
            log.info("Keine Bild-Anfrage, nutze Standard-Logik")
            return await super().run(task)

        detailed_prompt = await self._generate_image_prompt_with_gpt(task)
        observation = await self._execute_with_nemotron(detailed_prompt, size="1024x1024", quality="high")
        self._handle_file_artifacts(observation)

        if isinstance(observation, dict):
            has_error, error_message, error_code = self._extract_tool_error(observation)
            if has_error and error_code == "moderation_blocked":
                safe_prompt = self._build_safe_retry_prompt(detailed_prompt)
                log.warning("Bildgenerierung moderiert geblockt. Versuche sicheren Retry.")
                observation_retry = await self._execute_with_nemotron(
                    safe_prompt, size="1024x1024", quality="high"
                )
                self._handle_file_artifacts(observation_retry)
                if isinstance(observation_retry, dict):
                    retry_error, retry_message, _ = self._extract_tool_error(observation_retry)
                    if retry_error:
                        return f"Fehler bei der Bildgenerierung: {retry_message}"
                    observation = observation_retry
                    detailed_prompt = safe_prompt
                else:
                    return "Fehler bei der Bildgenerierung: Unerwartetes Antwortformat beim Retry."

            elif has_error:
                return f"Fehler bei der Bildgenerierung: {error_message}"

            saved_path = observation.get("saved_as", "")
            image_url = observation.get("image_url", "")

            if not saved_path and not image_url:
                return (
                    "Bildgenerierung abgeschlossen, aber es wurde weder Datei noch URL "
                    "zurueckgegeben."
                )

            final_answer = "Ich habe das Bild erfolgreich generiert!"
            if saved_path:
                final_answer += f"\n\nGespeichert unter: {saved_path}"
            if image_url:
                final_answer += f"\nURL: {image_url}"
            final_answer += f"\n\nVerwendeter Prompt: {detailed_prompt[:100]}..."

            return final_answer

        return "Bildgenerierung abgeschlossen, aber unerwartetes Antwortformat."
