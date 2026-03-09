# tools/document_parser/tool.py

# Standard-Bibliotheken
import logging
import io
import asyncio
from urllib.parse import urlparse

# Drittanbieter-Bibliotheken
import requests
import pypdfium2 as pdfium

# V2 Tool Registry
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# Holt den zentral konfigurierten Logger. Kein `log`-Import aus `shared_context`
# notwendig, da `getLogger` auf die globale Konfiguration zugreift.
logger_doc = logging.getLogger(__name__)


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


def _extract_text_with_pdfium(pdf_bytes: bytes) -> str:
    pdf_file = io.BytesIO(pdf_bytes)
    pdf_doc = pdfium.PdfDocument(pdf_file)
    text_parts = []
    page_errors = 0
    for i in range(len(pdf_doc)):
        try:
            page = pdf_doc.get_page(i)
            text_parts.append(page.get_textpage().get_text_range())
            page.close()
        except pdfium.PdfiumError as page_error:
            page_errors += 1
            logger_doc.warning("PDF-Seite %s konnte nicht geladen werden: %s", i, page_error)
            continue
    pdf_doc.close()
    if not text_parts and page_errors:
        raise pdfium.PdfiumError("Keine PDF-Seite konnte erfolgreich verarbeitet werden.")
    return "\n".join(text_parts)

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

        # Die PDF-Verarbeitung selbst ist auch CPU-intensiv und sollte in einem Thread laufen.
        extracted_text = await asyncio.to_thread(_extract_text_with_pdfium, pdf_bytes)

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
