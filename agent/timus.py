import os
import json
import logging
import textwrap
import time
import requests
import sys
import re
from openai import OpenAI
from dotenv import load_dotenv

# Logging-Konfiguration
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
MCP_URL = "http://127.0.0.1:5000"
load_dotenv()

# ─── OpenAI Client ─────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
if client.api_key is None:
    sys.exit("❌ OPENAI_API_KEY fehlt in .env")
# Für timus.py - Ersetze den SYSTEM_PROMPT:

SYSTEM_PROMPT = f"""Du bist Timus, ein KI-Agent für Web-Recherche und -Analyse.

WICHTIG: Das heutige Datum ist {time.strftime("%d.%m.%Y")} und es ist das Jahr {time.strftime("%Y")}!

VERFÜGBARE TOOLS:
• search_web(query, max_results=5) - Sucht im Web nach aktuellen Informationen
• open_url(url) - Öffnet eine Webseite
• list_links() - Zeigt Links der aktuellen Seite
• click_link(index) - Klickt auf einen Link (niedrige Indizes verwenden!)
• click_by_text(description) - Klickt auf ein Element basierend auf einer textuellen Beschreibung  
• get_text() - Gibt Seitentext zurück
• dismiss_overlays() - Entfernt Cookie-Banner/Popups
• summarize_article() - Fasst Artikel zusammen

KRITISCHE REGELN:
1. FÜR AKTUELLE INFORMATIONEN: Verwende IMMER zuerst search_web()
2. Bei Fragen nach Datum, Zeit, aktuellen Ereignissen → SOFORT suchen!
3. Bei "heute", "aktuell", "neueste", "jetzt" → SOFORT suchen!
4. NIEMALS aus dem Gedächtnis antworten bei aktuellen Themen!

ANTWORTFORMAT: Gib nur gültiges JSON zurück:
{{"method": "tool_name", "params": {{"param1": "value1"}}}}

Beispiele:
{{"method": "search_web", "params": {{"query": "aktuelles Datum heute", "max_results": 3}}}}
{{"method": "search_web", "params": {{"query": "aktuelle Nachrichten Deutschland", "max_results": 5}}}}
{{"method": "open_url", "params": {{"url": "https://example.com"}}}}
{{"method": "get_text", "params": {{}}}}

Vergiss dein Training - verwende IMMER das Web für aktuelle Informationen!"""


# ─── Farbige Ausgabe ───────────────────────
def green(s): return f"\033[92m{s}\033[0m"
def red(s):   return f"\033[91m{s}\033[0m"
def blue(s):  return f"\033[94m{s}\033[0m"
def yellow(s): return f"\033[93m{s}\033[0m"

# ─── RPC-Call ─────────────────────────────────
def call_tool(method: str, params: dict | None = None):
    """Ruft ein Tool über den MCP-Server auf."""
    payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": 1}
    
    try:
        logging.info(blue(f"🔧 Rufe auf: {method}({params or {}})"))
        response = requests.post(MCP_URL, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Fehlerbehandlung
        if "error" in data:
            error_msg = data["error"].get("message", str(data["error"]))
            return red(f"Tool-Fehler: {error_msg}")
        
        return data.get("result")
        
    except requests.exceptions.ConnectionError:
        return red("❌ MCP-Server nicht erreichbar! Ist der Server gestartet?")
    except requests.exceptions.Timeout:
        return red("❌ Timeout beim Tool-Aufruf")
    except requests.RequestException as e:
        return red(f"HTTP-Fehler: {e}")
    except json.JSONDecodeError:
        return red("❌ Ungültige JSON-Antwort vom Server")
    except Exception as e:
        return red(f"Unerwarteter Fehler: {e}")

# ─── LLM-Entscheidung ─────────────────────────
def decide_action(user_input: str):
    """Fragt das LLM nach der nächsten Aktion."""
    try:
        resp = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_input},
            ],
            temperature=0,
        )
        text = resp.choices[0].message.content.strip()
        
        # JSON aus Antwort extrahieren
        if text.startswith("```"):
            text = text.strip("`").lstrip("json").strip()
        
        # Versuche JSON zu parsen
        return json.loads(text)
        
    except json.JSONDecodeError as e:
        logging.error(red(f"❌ LLM gab kein gültiges JSON zurück: {text[:100]}..."))
        return None
    except Exception as e:
        logging.error(red(f"❌ LLM-Fehler: {e}"))
        return None

def test_connection():
    """Testet die Verbindung zum MCP-Server."""
    try:
        response = requests.get(f"{MCP_URL}/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            logging.info(green(f"✅ MCP-Server läuft: {data.get('status')}"))
            return True
        else:
            logging.warning(red(f"⚠️ Server antwortet mit Status {response.status_code}"))
            return False
    except Exception as e:
        logging.error(red(f"❌ Server nicht erreichbar: {e}"))
        return False

def format_search_results(results):
    """Formatiert Suchergebnisse für die Anzeige."""
    if not isinstance(results, list):
        return str(results)
    
    output = []
    for i, item in enumerate(results[:5], 1):
        title = item.get('title', 'Kein Titel')[:60]
        url = item.get('url', '')
        snippet = item.get('snippet', '')[:100]
        
        output.append(f"[{i}] {title}")
        if url:
            output.append(f"    🔗 {url}")
        if snippet:
            output.append(f"    📄 {snippet}...")
        output.append("")
    
    return "\n".join(output)

def format_links(links):
    """Formatiert Links für die Anzeige."""
    if not isinstance(links, list):
        return str(links)
    
    output = []
    for link in links[:20]:  # Nur erste 20 Links
        idx = link.get('idx', '?')
        text = link.get('text', 'Kein Text')[:70]
        href = link.get('href', '')
        
        output.append(f"[{idx:>2}] {text}")
        if href and len(href) < 80:
            output.append(f"     → {href}")
        output.append("")
    
    return "\n".join(output)

# ─── Interaktive Shell ────────────────────────
def shell():
    """Hauptinteraktionsschleife."""
    logging.info(yellow("🤖 Timus - Einfacher Web-Agent"))
    logging.info(f"🔌 MCP-Server: {MCP_URL}")
    
    # Verbindung testen
    if not test_connection():
        logging.error(red("\n❌ Kann nicht ohne MCP-Server fortfahren."))
        logging.info("Starte den Server: cd server && python mcp_server.py")
        return
    
    logging.info(green("\n📖 Verfügbare Befehle:"))
    logging.info("  open URL       - Seite laden")
    logging.info("  search QUERY   - Web-Suche")
    logging.info("  links          - Links der aktuellen Seite")
    logging.info("  click IDX/TEXT - Link anklicken")
    logging.info("  text           - Seitentext anzeigen")
    logging.info("  summary        - Artikel zusammenfassen")
    logging.info("  dismiss        - Popups schließen")
    logging.info("  quit           - Beenden")
    logging.info("  ODER: Natürliche Sprache für automatische Tool-Auswahl")
    
    last_llm_call = 0.0
    
    while True:
        try:
            cmd = input(f"\n{blue('Timus>')} ").strip()
            
            if cmd.lower() in {"quit", "exit", "q"}:
                logging.info(yellow("👋 Auf Wiedersehen!"))
                break
            
            if not cmd:
                continue
            
            # Rate-Limiting für LLM-Aufrufe
            def rate_limit():
                nonlocal last_llm_call
                elapsed = time.time() - last_llm_call
                if elapsed < 1.0:
                    time.sleep(1.0 - elapsed)
                last_llm_call = time.time()
            
            # Direkte Befehle
            if cmd.startswith("open "):
                url = cmd[5:].strip()
                result = call_tool("open_url", {"url": url})
                print(green(f"✅ {result}"))
                
            elif cmd.startswith("search "):
                query = cmd[7:].strip()
                if query:
                    result = call_tool("search_web", {"query": query, "max_results": 5})
                    if isinstance(result, list):
                        logging.info(green("🔍 Suchergebnisse:"))
                        logging.info(format_search_results(result))
                    else:
                        print(result)
                else:
                    print(red("❌ Bitte Suchbegriff angeben"))
                    
            elif cmd == "links":
                result = call_tool("list_links")
                if isinstance(result, list):
                    print(green("🔗 Verfügbare Links:"))
                    print(format_links(result))
                else:
                    print(result)
                    
            elif cmd.startswith("click "):
                arg = cmd[6:].strip()
                if arg.isdigit():
                    result = call_tool("click_link", {"index": int(arg)})
                else:
                    result = call_tool("click_by_text", {"description": arg})
                print(green(f"👆 {result}"))
                
            elif cmd == "text":
                result = call_tool("get_text")
                if isinstance(result, dict) and "text" in result:
                    text = result["text"]
                    print(green("📄 Seitentext:"))
                    print(textwrap.fill(text[:1000], width=80))
                    if len(text) > 1000:
                        print(f"\n... ({len(text)-1000} weitere Zeichen)")
                else:
                    print(result)
                    
            elif cmd == "summary":
                result = call_tool("summarize_article")
                if isinstance(result, dict) and "summary" in result:
                    print(green("📋 Zusammenfassung:"))
                    print(textwrap.fill(result["summary"], width=80))
                else:
                    print(result)
                    
            elif cmd == "dismiss":
                result = call_tool("dismiss_overlays")
                print(green(f"🚫 {result}"))
                
            elif cmd in {"help", "hilfe", "?"}:
                print(green("\n📚 Hilfe:"))
                print("Direkte Befehle:")
                print("  search KI Nachrichten - Sucht nach KI-Nachrichten")
                print("  open heise.de        - Öffnet heise.de")
                print("  links                - Zeigt alle Links")
                print("  click 0              - Klickt auf Link 0")
                print("  text                 - Zeigt Seitentext")
                print("  summary              - Fasst Artikel zusammen")
                print("\nNatürliche Sprache:")
                print("  'Suche nach Tesla Aktie'")
                print("  'Öffne Spiegel Online und zeige Schlagzeilen'")
                
            else:
                # Natürliche Sprache -> LLM entscheidet
                rate_limit()
                print(blue("🧠 LLM wählt Tool..."))
                
                action = decide_action(cmd)
                if action and isinstance(action, dict) and "method" in action:
                    method = action.get("method", "")
                    params = action.get("params", {})
                    
                    result = call_tool(method, params)
                    
                    # Intelligente Ausgabe je nach Tool
                    if method == "search_web" and isinstance(result, list):
                        logging.info(green("🔍 Suchergebnisse:"))
                        logging.info(format_search_results(result))
                    elif method == "list_links" and isinstance(result, list):
                        logging.info(green("🔗 Links:"))
                        logging.info(format_links(result))
                    elif method == "get_text" and isinstance(result, dict) and "text" in result:
                        text = result["text"]
                        logging.info(green("📄 Seitentext:"))
                        logging.info(textwrap.fill(text[:800], width=80))
                        if len(text) > 800:
                            logging.info(f"\n... ({len(text)-800} weitere Zeichen)")
                    elif method == "summarize_article" and isinstance(result, dict) and "summary" in result:
                        logging.info(green("📋 Zusammenfassung:"))
                        logging.info(textwrap.fill(result["summary"], width=80))
                    else:
                        print(f"🔧 {result}")
                else:
                    logging.error(red("❌ Konnte keine passende Aktion bestimmen"))
                    
        except KeyboardInterrupt:
            logging.warning(yellow("\n⚠️ Unterbrochen. 'quit' zum Beenden."))
        except Exception as e:
            logging.error(red(f"\n❌ Unerwarteter Fehler: {e}"))

if __name__ == "__main__":
    shell()
def click_by_text(description):
    """Klickt auf ein Element basierend auf einer textuellen Beschreibung."""
    
    # Einfache NLP-Analyse der Beschreibung
    position_keywords = {
        "oben": "top",
        "unten": "bottom",
        "rechts": "right",
        "links": "left",
        "mitte": "center"
    }
    
    # Beispiel für die Extraktion von Position und Typ
    position = None
    element_type = None
    
    for keyword, pos in position_keywords.items():
        if keyword in description:
            position = pos
            break
    
    if "button" in description:
        element_type = "button"
    elif "feld" in description:
        element_type = "field"
    
    # Erstellen der Parameter für den Tool-Aufruf
    params = {"description": description, "position": position, "type": element_type}
    
    result = call_tool("click_by_text", params)
    print(green(f"👆 {result}"))
