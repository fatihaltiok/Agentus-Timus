# M4.1 Formale Policy-Gates + Audit-Entscheidungen

Stand: 2026-02-25

## Ziel
Kritische Pfade nutzen jetzt ein einheitliches, formales Policy-Entscheidungsmodell:
1. `allow` (normal)
2. `observe` (Hinweis ohne harte Blockierung)
3. `block` (harte Blockierung)

Zusätzlich werden Policy-Entscheidungen als Audit-Ereignisse erfasst.

## Architektur (additiv)
`utils/policy_gate.py` erweitert:
1. `evaluate_policy_gate(...)` fuer Gate-Typen:
   - `query`
   - `tool`
   - `delegation`
2. `audit_policy_decision(...)` fuer strukturierte Decision-Audit-Logs.
3. Strict-/Audit-Modus via bestehender Flags:
   - `AUTONOMY_POLICY_GATES_STRICT`
   - `AUTONOMY_AUDIT_DECISIONS_ENABLED`
   - kompatibel mit `AUTONOMY_COMPAT_MODE`

Wichtig:
1. Bestehende Funktionen `check_query_policy`, `check_tool_policy`, `audit_tool_call` bleiben kompatibel erhalten.
2. Bestehende harte Tool-Blockierungen (Blocklist) bleiben weiterhin harte Blockierungen.

## Kritische Pfade (M4.1)
1. Dispatcher Query-Gate:
   - `main_dispatcher.run_agent(...)`
   - strict blockiert sofort, observe fragt bestaetigend (bestehendes Verhalten).
2. MCP JSON-RPC Tool-Gate:
   - `server/mcp_server.py` (`POST /`)
   - blockierte Entscheidungen liefern HTTP 403 / JSON-RPC Fehler.
3. Agent Tool-Execution:
   - `agent/base_agent.py` (`_call_tool`)
   - einheitliche Gate-Entscheidung pro Tool-Call.
4. Agent-Delegation:
   - `agent/agent_registry.py` (`delegate`)
   - dangerous Tasks zu `shell/system` werden in strict blockiert.

## Audit-Entscheidungen
1. Jede Entscheidung wird als Log-Ereignis geschrieben (`[policy-decision] ...`).
2. Bei aktivem Audit-Flag werden Entscheidungen zusaetzlich als JSONL persistiert:
   - `logs/YYYY-MM-DD_policy_decisions.jsonl`
3. Payloads werden vor Persistierung maskiert (z. B. `password`, `token`, `api_key`).

## Kompatibilitaet
1. Keine Signatur-Breaks in Dispatcher/Registry/Server.
2. Flags bleiben default-safe (`strict=false`, `audit=false`).
3. M0-, Milestone5-, Milestone6-Gates bleiben gruen.
