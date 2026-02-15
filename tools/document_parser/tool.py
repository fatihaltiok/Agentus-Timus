# tools/document_parser/tool.py

# Standard-Bibliotheken
import logging
import io
import asyncio

# Drittanbieter-Bibliotheken
import requests
import pypdfium2 as pdfium

# V2 Tool Registry
from tools.tool_registry_v2 import tool, ToolParameter as P, ToolCategory as C

# Holt den zentral konfigurierten Logger. Kein `log`-Import aus `shared_context`
# notwendig, da `getLogger` auf die globale Konfiguration zugreift.
logger_doc = logging.getLogger(__name__)

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
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/pdf,application/octet-stream",
                "Accept-Language": "en-US,en;q=0.9"
            }

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
        def parse_pdf():
            pdf_file = io.BytesIO(pdf_bytes)
            pdf_doc = pdfium.PdfDocument(pdf_file)
            text_content = ""
            for i in range(len(pdf_doc)):
                page = pdf_doc.get_page(i)
                text_content += page.get_textpage().get_text_range() + "\n"
                page.close()
            pdf_doc.close()
            return text_content

        extracted_text = await asyncio.to_thread(parse_pdf)

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
