#!/usr/bin/env python3
# utils/timus_mail_cli.py
"""
Timus E-Mail CLI — manuelles Testen (Microsoft Graph / OAuth2).

Verwendung:
  python utils/timus_mail_cli.py status
  python utils/timus_mail_cli.py send --to x@y.de --subject "Test" --body "Hallo"
  python utils/timus_mail_cli.py read [--limit 5] [--unread] [--mailbox inbox] [--search "fatih"]

Voraussetzung: einmalig python utils/timus_mail_oauth.py ausführen.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from dotenv import load_dotenv
load_dotenv(dotenv_path=_root / ".env", override=True)

from tools.email_tool.tool import send_email, read_emails, get_email_status


def _pretty(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def cmd_status(_args: argparse.Namespace) -> int:
    print("Prüfe E-Mail-Verbindung …")
    result = get_email_status()
    print(_pretty(result))
    ok = "✅" if result.get("success") else "❌"
    print(f"\nGraph-API {ok}  Konto: {result.get('address', '?')}")
    return 0 if result.get("success") else 1


def cmd_send(args: argparse.Namespace) -> int:
    print(f"Sende E-Mail an {args.to} …")
    result = send_email(
        to=args.to,
        subject=args.subject,
        body=args.body,
        cc=args.cc or None,
        bcc=args.bcc or None,
    )
    print(_pretty(result))
    return 0 if result.get("success") else 1


def cmd_read(args: argparse.Namespace) -> int:
    print(f"Lese Postfach '{args.mailbox}' (limit={args.limit}, unread={args.unread}) …")
    result = read_emails(
        mailbox=args.mailbox,
        limit=args.limit,
        unread_only=args.unread,
        search=args.search or "",
    )
    if not result.get("success"):
        print(f"Fehler: {result.get('error')}", file=sys.stderr)
        return 1

    emails = result.get("emails", [])
    print(f"\n{result['count']} E-Mail(s) gefunden:\n")
    for i, mail in enumerate(emails, 1):
        status = "●" if not mail["is_read"] else "○"
        print(f"  {i}. {status} [{mail['date']}]")
        print(f"     Von:     {mail['from']}")
        print(f"     Betreff: {mail['subject']}")
        print(f"     Body:    {mail['body'][:200]}")
        print()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Timus E-Mail CLI (Graph API)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Graph-Verbindung prüfen")

    p_send = sub.add_parser("send", help="E-Mail senden")
    p_send.add_argument("--to",      required=True)
    p_send.add_argument("--subject", required=True)
    p_send.add_argument("--body",    required=True)
    p_send.add_argument("--cc",      default="")
    p_send.add_argument("--bcc",     default="")

    p_read = sub.add_parser("read", help="E-Mails lesen")
    p_read.add_argument("--mailbox", default="inbox")
    p_read.add_argument("--limit",   type=int, default=10)
    p_read.add_argument("--unread",  action="store_true")
    p_read.add_argument("--search",  default="")

    args = parser.parse_args()
    dispatch = {"status": cmd_status, "send": cmd_send, "read": cmd_read}
    sys.exit(dispatch[args.command](args))


if __name__ == "__main__":
    main()
