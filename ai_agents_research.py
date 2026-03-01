#!/usr/bin/env python3
"""
Python script to search for recent information about "KI-Agenten" (AI agents, autonomous agents, multi‑agent systems).
The script uses DuckDuckGo's HTML search results, parses the top 5‑8 entries, extracts the title, URL and a short description, and saves the data as JSON to /tmp/ai_agents_research.json.
"""

import json
import os
import sys
from typing import List, Dict

import requests
from bs4 import BeautifulSoup

# ----------------------------
# Configuration
# ----------------------------
SEARCH_QUERY = "KI-Agenten OR AI agents OR autonomous agents"
MAX_RESULTS = 8
OUTPUT_JSON = "/tmp/ai_agents_research.json"
DUCKDUCKGO_SEARCH_URL = "https://duckduckgo.com/html/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; AI-Agent-Research/1.0; +https://example.com/bot)"
}

# ----------------------------
# Helper functions
# ----------------------------

def fetch_search_results(query: str, max_results: int) -> List[Dict[str, str]]:
    """Query DuckDuckGo HTML search and return a list of result dicts.

    Each dict contains:
        - title: str
        - url: str
        - snippet: str
    """
    params = {"q": query, "kl": "de-de"}
    try:
        response = requests.get(DUCKDUCKGO_SEARCH_URL, params=params, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Error fetching search results: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    results = []
    for result in soup.select(".result")[:max_results]:
        title_tag = result.select_one(".result__title a")
        snippet_tag = result.select_one(".result__snippet")
        if not title_tag or not snippet_tag:
            continue
        title = title_tag.get_text(strip=True)
        url = title_tag["href"]
        snippet = snippet_tag.get_text(strip=True)
        results.append({"title": title, "url": url, "snippet": snippet})
    return results


def save_to_json(data: List[Dict[str, str]], filepath: str) -> None:
    """Write the data list to the given JSON file with pretty printing."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Saved {len(data)} results to {filepath}")
    except OSError as e:
        print(f"Error writing JSON file: {e}", file=sys.stderr)

# ----------------------------
# Main execution
# ----------------------------

def main() -> None:
    results = fetch_search_results(SEARCH_QUERY, MAX_RESULTS)
    if not results:
        print("No results found. Exiting.", file=sys.stderr)
        return
    save_to_json(results, OUTPUT_JSON)

if __name__ == "__main__":
    main()
