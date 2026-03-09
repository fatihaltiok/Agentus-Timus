from xml.sax.saxutils import escape

import deal

from tools.deep_research.trend_researcher import ArXivResearcher


@deal.pre(lambda arxiv_id: bool(arxiv_id.strip()) and all(ch not in arxiv_id for ch in "<>/"))
@deal.pre(lambda title: bool(title.strip()) and "<" not in title and ">" not in title)
@deal.pre(lambda summary: bool(summary.strip()) and "<" not in summary and ">" not in summary)
@deal.post(lambda r: isinstance(r, list) and len(r) == 1)
def parse_single_entry_contract(arxiv_id: str, title: str, summary: str) -> list[dict]:
    xml_text = f"""<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/{escape(arxiv_id)}v1</id>
        <published>2026-03-09T12:00:00Z</published>
        <title>{escape(title)}</title>
        <summary>{escape(summary)}</summary>
      </entry>
    </feed>
    """
    return ArXivResearcher()._parse_atom(xml_text)


@deal.post(lambda r: r == [])
def parse_malformed_contract() -> list[dict]:
    return ArXivResearcher()._parse_atom("<feed><entry></feed>")
