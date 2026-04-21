"""DocumentAgent — Dokumenten-Spezialist für PDF, DOCX, XLSX, TXT."""

from __future__ import annotations

import json
import re
import logging
from typing import Any, Optional

from agent.base_agent import BaseAgent
from agent.prompts import DOCUMENT_PROMPT_TEMPLATE
from agent.shared.delegation_handoff import DelegationHandoff, parse_delegation_handoff
from orchestration.specialist_step_package import (
    extract_specialist_step_package_from_handoff_data,
    render_specialist_step_package_block,
)

log = logging.getLogger("TimusAgent-v4.4")

# Reihenfolge: spezifischste Begriffe zuerst (DOCX vor PDF wegen "Angebot")
_FORMAT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("XLSX", re.compile(r"\b(excel|xlsx|tabelle|spreadsheet|kalkulat)\b", re.I)),
    ("DOCX", re.compile(r"\b(word|docx|angebot|brief|letter|anschreiben|editierbar|lebenslauf)\b", re.I)),
    ("TXT",  re.compile(r"\b(txt|plaintext|notiz|entwurf|rohtext)\b", re.I)),
    ("PDF",  re.compile(r"\b(pdf|bericht|report|zusammenfassung|summary|protokoll|projektdoku)\b", re.I)),
]
_DEFAULT_FORMAT = "PDF"
_EXPLICIT_TEXT_REF_PATTERN = re.compile(
    r"(?:^|[\s`'\"(])((?:[\w.-]+/)*[\w.-]+\.(?:md|txt|log|json|yaml|yml|toml|ini|cfg|py))(?:$|[\s`'\"),.;:])",
    re.IGNORECASE,
)
_EVIDENCE_READ_MARKERS = (
    "lies ",
    "lese ",
    "schau nach",
    "pruef",
    "prüf",
    "status",
    "naechstes",
    "nächstes",
    "was steht",
    "welche vorbereitungen",
    "welche vorbereitungen gibt es",
)


def _detect_format(task: str) -> str:
    for fmt, pattern in _FORMAT_PATTERNS:
        if pattern.search(task):
            return fmt
    return _DEFAULT_FORMAT


def _decode_handoff_value(value: Any) -> str:
    return str(value or "").replace("\\n", "\n").replace("\\t", "\t").replace("\\\\", "\\")


def _shorten_text(value: Any, *, limit: int = 1800) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    clipped = text[:limit].rsplit(" ", 1)[0].strip()
    return f"{clipped or text[:limit]}..."


def _parse_string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple)):
        return [str(item or "").strip() for item in value if str(item or "").strip()]
    raw = str(value or "").strip()
    if not raw:
        return []
    try:
        loaded = json.loads(raw)
    except Exception:
        loaded = None
    if isinstance(loaded, list):
        return [str(item or "").strip() for item in loaded if str(item or "").strip()]
    return [item.strip() for item in raw.split(",") if item.strip()]


def _extract_explicit_text_refs(task: str, handoff: Optional[DelegationHandoff]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    if handoff:
        for key in (
            "document_refs_json",
            "document_refs",
            "explicit_document_refs_json",
            "explicit_document_refs",
        ):
            for ref in _parse_string_list(handoff.handoff_data.get(key)):
                lowered = ref.lower()
                if lowered in seen:
                    continue
                seen.add(lowered)
                refs.append(ref)
    for match in _EXPLICIT_TEXT_REF_PATTERN.findall(str(task or "")):
        cleaned = str(match or "").strip().strip("`")
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        refs.append(cleaned)
    return refs


def _extract_table_from_source_material(source_material: str) -> tuple[list[str], list[list[str]]]:
    lines = [line.strip() for line in str(source_material or "").splitlines()]
    table_lines = [line for line in lines if "|" in line and line.count("|") >= 2]
    if len(table_lines) < 2:
        return [], []

    rows: list[list[str]] = []
    for raw_line in table_lines:
        stripped = raw_line.strip().strip("|")
        if not stripped:
            continue
        cells = [cell.strip() for cell in stripped.split("|")]
        if not any(cell for cell in cells):
            continue
        if all(re.fullmatch(r"[:\- ]+", cell or "") for cell in cells):
            continue
        rows.append(cells)
    if len(rows) < 2:
        return [], []

    headers = rows[0]
    width = len(headers)
    normalized_rows: list[list[str]] = []
    for row in rows[1:]:
        padded = row[:width] + [""] * max(0, width - len(row))
        normalized_rows.append(padded[:width])
    return headers, normalized_rows


class DocumentAgent(BaseAgent):
    def __init__(self, tools_description_string: str):
        super().__init__(
            DOCUMENT_PROMPT_TEMPLATE,
            tools_description_string,
            max_iterations=15,
            agent_type="document",
        )

    async def run(self, task: str) -> str:
        handoff = parse_delegation_handoff(task)
        effective_task = handoff.goal if handoff and handoff.goal else str(task or "").strip()
        handoff_context = self._build_delegation_document_context(handoff)
        file_evidence = await self._maybe_read_explicit_file_evidence(handoff, effective_task)
        if file_evidence:
            return file_evidence
        fmt = _detect_format(effective_task)
        log.info(f"DocumentAgent | Format erkannt: {fmt}")
        direct_export = await self._maybe_run_structured_lookup_export(handoff, fmt)
        if direct_export:
            return direct_export
        parts = [effective_task, f"ERKANNTES_FORMAT: {fmt}"]
        if handoff_context:
            parts.append(handoff_context)
        return await super().run("\n\n".join(part for part in parts if part))

    def _build_delegation_document_context(self, handoff: Optional[DelegationHandoff]) -> str:
        if not handoff:
            return ""

        lines: list[str] = ["# STRUKTURIERTER DOCUMENT-HANDOFF"]
        if handoff.expected_output:
            lines.append(f"Erwarteter Output: {handoff.expected_output}")
        if handoff.success_signal:
            lines.append(f"Erfolgssignal: {handoff.success_signal}")
        if handoff.constraints:
            lines.append("Constraints: " + " | ".join(handoff.constraints))
        specialist_step_package = render_specialist_step_package_block(
            extract_specialist_step_package_from_handoff_data(handoff.handoff_data)
        )
        if specialist_step_package:
            lines.append(specialist_step_package)

        for key, label in (
            ("recipe_id", "Rezept"),
            ("stage_id", "Stage"),
            ("artifact_name", "Artefaktname"),
            ("output_format", "Zielformat"),
            ("source_urls", "Quell-URLs"),
            ("captured_context", "Bereits erfasster Kontext"),
            ("previous_stage_result", "Vorheriges Stage-Ergebnis"),
            ("previous_blackboard_key", "Blackboard-Key"),
            ("document_refs_json", "Dokument-Referenzen"),
            ("evidence_mode", "Evidenzmodus"),
        ):
            value = handoff.handoff_data.get(key)
            if value:
                lines.append(f"{label}: {_decode_handoff_value(value)}")
        return "\n".join(lines)

    async def _maybe_read_explicit_file_evidence(
        self,
        handoff: Optional[DelegationHandoff],
        effective_task: str,
    ) -> str:
        normalized = str(effective_task or "").strip().lower()
        evidence_mode = (
            str((handoff.handoff_data or {}).get("evidence_mode") or "").strip().lower()
            if handoff
            else ""
        )
        should_read = evidence_mode == "read_and_summarize" or any(
            marker in normalized for marker in _EVIDENCE_READ_MARKERS
        )
        refs = _extract_explicit_text_refs(effective_task, handoff)
        if not should_read or not refs:
            return ""

        sections: list[str] = ["# DOKUMENT-EVIDENZ", "Explizit gelesene Dateien:"]
        success_count = 0
        for ref in refs[:4]:
            result = await self._call_tool("read_file", {"path": ref})
            payload = result if isinstance(result, dict) else {}
            if str(payload.get("status") or "").strip().lower() != "success":
                message = str(payload.get("message") or payload.get("error") or "").strip()
                sections.append(f"- {ref}: LESEN_FEHLGESCHLAGEN{': ' + message if message else ''}")
                continue
            success_count += 1
            content = _shorten_text(payload.get("content") or "", limit=2500)
            path = str(payload.get("path") or ref).strip()
            sections.extend(
                [
                    f"- {ref}: gelesen",
                    "",
                    f"## DATEI: {path}",
                    content or "(leer)",
                    "",
                ]
            )

        if success_count == 0:
            return ""
        sections.append(
            "Nutze nur diese gelesene Evidenz. Erfinde keine weiteren Dateien oder Projektkontexte."
        )
        return "\n".join(part for part in sections if part is not None).strip()

    async def _maybe_run_structured_lookup_export(
        self,
        handoff: Optional[DelegationHandoff],
        detected_format: str,
    ) -> str:
        if not handoff:
            return ""
        source_material = _decode_handoff_value(
            handoff.handoff_data.get("source_material") or handoff.handoff_data.get("captured_context") or ""
        )
        if "|" not in source_material:
            return ""
        output_format = (
            str(handoff.handoff_data.get("output_format") or "").strip().upper()
            or detected_format
        )
        if output_format not in {"XLSX", "TXT", "CSV"}:
            return ""
        headers, rows = _extract_table_from_source_material(source_material)
        if not headers or not rows:
            return ""
        title = str(handoff.handoff_data.get("artifact_name") or "Timus_Tabelle").strip() or "Timus_Tabelle"
        preview_lines = source_material.splitlines()
        preview = "\n".join(preview_lines[: min(6, len(preview_lines))]).strip()
        if output_format == "XLSX":
            result = await self._call_tool(
                "create_xlsx",
                {"title": title, "headers": headers, "rows": rows},
            )
        elif output_format == "CSV":
            result = await self._call_tool(
                "create_csv",
                {"title": title, "headers": headers, "rows": rows},
            )
        else:
            result = await self._call_tool(
                "create_txt",
                {"title": title, "content": source_material},
            )

        payload = result if isinstance(result, dict) else {}
        if payload.get("error") or str(payload.get("status") or "").strip().lower() == "error":
            return ""

        artifact_path = str(payload.get("path") or payload.get("filepath") or payload.get("filename") or "").strip()
        lines = [
            f"**Dokument erstellt:** `{artifact_path}`",
            f"**Format:** {output_format}",
            f"**Inhalt:** Tabelle mit {len(rows)} Zeilen aus dem Lookup-Ergebnis.",
        ]
        if preview:
            lines.extend(["", "**Vorschau:**", preview])
        return "\n".join(lines)
