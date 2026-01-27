# tools/document_parser/tool.py

# Standard-Bibliotheken
import logging
import io
from typing import Union
import asyncio

# Drittanbieter-Bibliotheken
import requests
import pypdfium2 as pdfium
from jsonrpcserver import method, Success, Error

# Interne Imports
from tools.universal_tool_caller import register_tool

# Holt den zentral konfigurierten Logger. Kein `log`-Import aus `shared_context`
# notwendig, da `getLogger` auf die globale Konfiguration zugreift.
logger_doc = logging.getLogger(__name__)

@method
async def extract_text_from_pdf(pdf_url: str) -> Union[Success, Error]:
    """
    Lädt ein PDF von einer URL herunter und extrahiert den gesamten Textinhalt.
    """
    logger_doc.info(f"Extrahiere Text von PDF-URL: {pdf_url}")
    try:
        # Führe den blockierenden Download in einem Thread aus
        def download_pdf():
            response = requests.get(pdf_url, timeout=30, stream=True)
            response.raise_for_status()
            
            content_type = response.headers.get('content-type', '').lower()
            if 'application/pdf' not in content_type:
                # Wirf einen spezifischen Fehler, der im Hauptthread gefangen wird
                raise ValueError(f"Content-Type ist nicht application/pdf, sondern '{content_type}'.")
                
            return response.content

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
        return Success({"text": extracted_text, "source_url": pdf_url})
    
    except ValueError as ve: # Fängt unseren Content-Type Fehler
        logger_doc.warning(f"Extraktion für {pdf_url} abgebrochen: {ve}")
        return Error(code=-32001, message=str(ve))
    except pdfium.PdfiumError as pdf_e:
        logger_doc.error(f"Pypdfium2 Fehler beim Verarbeiten von PDF {pdf_url}: {pdf_e}", exc_info=True)
        return Error(code=-32002, message=f"Fehler bei PDF-Verarbeitung: {str(pdf_e)}")
    except requests.exceptions.RequestException as req_e:
        logger_doc.error(f"Fehler beim Herunterladen von PDF {pdf_url}: {req_e}", exc_info=True)
        return Error(code=-32003, message=f"Fehler beim PDF-Download: {str(req_e)}")
    except Exception as e:
        logger_doc.error(f"Allgemeiner Fehler bei PDF-Extraktion von {pdf_url}: {e}", exc_info=True)
        return Error(code=-32000, message=f"Allgemeiner Fehler bei PDF-Extraktion: {str(e)}")

register_tool("extract_text_from_pdf", extract_text_from_pdf)
logger_doc.info("✅ PDF Extraction Tool (extract_text_from_pdf) registriert.")