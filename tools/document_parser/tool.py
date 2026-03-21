# tools/document_parser/tool.py

# Standard-Bibliotheken
import base64
import json
import logging
import io
import asyncio
import sys
from urllib.parse import urlparse

# Drittanbieter-Bibliotheken
import requests
import pypdfium2 as pdfium

# V2 Tool Registry
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# Holt den zentral konfigurierten Logger. Kein `log`-Import aus `shared_context`
# notwendig, da `getLogger` auf die globale Konfiguration zugreift.
logger_doc = logging.getLogger(__name__)

# Subprocess-Script für isolierte PDF-Extraktion (SEGV-safe).
# pypdfium2 (C-Extension) kann bei bestimmten PDFs SIGSEGV werfen und damit
# den gesamten Server-Prozess beenden. Indem wir die Extraktion in einem
# eigenen Subprocess ausführen, isolieren wir den Absturz vollständig.
_PDF_EXTRACT_SCRIPT = """
import sys, io, json, base64
import pypdfium2 as pdfium

pdf_b64 = sys.stdin.buffer.read()
pdf_bytes = base64.b64decode(pdf_b64)
pdf_file = io.BytesIO(pdf_bytes)
pdf_doc = pdfium.PdfDocument(pdf_file)
text_parts = []
for i in range(len(pdf_doc)):
    try:
        page = pdf_doc.get_page(i)
        text_parts.append(page.get_textpage().get_text_range())
        page.close()
    except Exception:
        continue
pdf_doc.close()
sys.stdout.write(json.dumps({"text": "\\n".join(text_parts)}))
"""


def _download_headers(pdf_url: str) -> dict:
    parsed = urlparse(pdf_url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    return {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "application/pdf,application/octet-stream,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": origin or pdf_url,
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
    }


async def _extract_text_with_pdfium_safe(pdf_bytes: bytes) -> str:
    """
    Extracts text from PDF in an isolated subprocess.
    pypdfium2 (C-Extension) can SIGSEGV on malformed PDFs, which would kill
    the entire server process. Running it in a subprocess isolates the crash.
    """
    pdf_b64 = base64.b64encode(pdf_bytes)
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-c", _PDF_EXTRACT_SCRIPT,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(pdf_b64),
            timeout=45,
        )
    except asyncio.TimeoutError:
        raise Exception("PDF-Extraktion: Subprocess-Timeout (45s)")

    if proc.returncode != 0:
        err = stderr.decode(errors="replace")[:300] if stderr else "unknown"
        raise pdfium.PdfiumError(f"PDF-Subprocess exit {proc.returncode}: {err}")

    data = json.loads(stdout.decode(errors="replace"))
    return data.get("text", "")

@tool(
    name="extract_text_from_pdf",
    description="Laedt ein PDF von einer URL herunter und extrahiert den gesamten Textinhalt.",
    parameters=[
        P("pdf_url", "string", "URL des herunterzuladenden PDF-Dokuments", required=True),
    ],
    capabilities=["document", "pdf"],
    category=C.DOCUMENT
)
async def extract_text_from_pdf(pdf_url: str) -> dict:
    """
    Lädt ein PDF von einer URL herunter und extrahiert den gesamten Textinhalt.
    """
    logger_doc.info(f"Extrahiere Text von PDF-URL: {pdf_url}")
    try:
        # Führe den blockierenden Download in einem Thread aus
        def download_pdf():
            headers = _download_headers(pdf_url)

            # Max 3 Retries mit exponentiellem Backoff
            for attempt in range(3):
                try:
                    response = requests.get(pdf_url, headers=headers, timeout=60, stream=True)
                    response.raise_for_status()

                    content_type = response.headers.get('content-type', '').lower()

                    # Laxere Content-Type Prüfung: akzeptiere "application/pdf" oder wenn extension .pdf
                    if 'application/pdf' not in content_type:
                        if not pdf_url.lower().endswith('.pdf'):
                            # Versuch es trotzdem wenn .pdf extension
                            logger_doc.warning(f"Content-Type '{content_type}' nicht PDF, versuche trotzdem weil URL endet mit .pdf")
                            pass
                        else:
                            raise ValueError(f"Content-Type ist nicht application/pdf, sondern '{content_type}'. URL: {pdf_url}")

                    # Streaming Speichern für große PDFs
                    pdf_content = b''
                    for chunk in response.iter_content(chunk_size=8192):
                        pdf_content += chunk

                    return pdf_content

                except requests.exceptions.RequestException as req_e:
                    if attempt < 2:
                        wait_time = 2 ** attempt
                        logger_doc.warning(f"Download-Versuch {attempt+1} gescheitert, warte {wait_time}s...")
                        import time
                        time.sleep(wait_time)
                    else:
                        raise
                except Exception as e:
                    if attempt < 2:
                        continue
                    raise

        pdf_bytes = await asyncio.to_thread(download_pdf)

        # Subprocess-Isolation: SEGV in pdfium tötet nur den Subprocess, nicht den Server.
        extracted_text = await _extract_text_with_pdfium_safe(pdf_bytes)

        logger_doc.info(f"Text aus PDF {pdf_url} extrahiert (Länge: {len(extracted_text)} Zeichen).")
        return {"text": extracted_text, "source_url": pdf_url}

    except ValueError as ve: # Fängt unseren Content-Type Fehler
        logger_doc.warning(f"Extraktion für {pdf_url} abgebrochen: {ve}")
        raise Exception(str(ve))
    except pdfium.PdfiumError as pdf_e:
        logger_doc.error(f"Pypdfium2 Fehler beim Verarbeiten von PDF {pdf_url}: {pdf_e}", exc_info=True)
        raise Exception(f"Fehler bei PDF-Verarbeitung: {str(pdf_e)}")
    except requests.exceptions.RequestException as req_e:
        logger_doc.error(f"Fehler beim Herunterladen von PDF {pdf_url}: {req_e}", exc_info=True)
        raise Exception(f"Fehler beim PDF-Download: {str(req_e)}")
    except Exception as e:
        logger_doc.error(f"Allgemeiner Fehler bei PDF-Extraktion von {pdf_url}: {e}", exc_info=True)
        raise Exception(f"Allgemeiner Fehler bei PDF-Extraktion: {str(e)}")
