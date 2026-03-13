**SM3: Isolierte Patch Pipeline**

Stand: 13.03.2026

Ziel:
- Self-Modification darf nicht direkt im laufenden Repo testen und anwenden.
- Änderungen sollen zuerst in einem isolierten Workspace vorbereitet und verifiziert werden.

Umsetzung:
- neues Modul [orchestration/self_modification_patch_pipeline.py](/home/fatih-ubuntu/dev/timus/orchestration/self_modification_patch_pipeline.py)
- bevorzugter Modus:
  - `git worktree --detach` auf `HEAD`
- Fallback ohne Git:
  - isolierte Spiegelkopie (`mirror_copy`)
- pro Änderung werden erzeugt:
  - isolierter Workspace
  - `patch.diff`
  - `metadata.json`

Integration:
- [orchestration/self_modifier_engine.py](/home/fatih-ubuntu/dev/timus/orchestration/self_modifier_engine.py)
  - `modify_file()` schreibt nicht mehr direkt ins Live-Repo
  - Tests laufen zuerst im isolierten Workspace
  - Promotion ins Live-Repo erst nach bestandenem Testlauf
  - `approve_pending()` nutzt dieselbe Isolationslogik

Neue Result-Metadaten:
- `workspace_mode`
- `patch_diff`

Tests:
- [tests/test_self_modification_patch_pipeline.py](/home/fatih-ubuntu/dev/timus/tests/test_self_modification_patch_pipeline.py)
- [tests/test_self_modification_patch_pipeline_contracts.py](/home/fatih-ubuntu/dev/timus/tests/test_self_modification_patch_pipeline_contracts.py)
- erweiterte [tests/test_self_modifier_engine.py](/home/fatih-ubuntu/dev/timus/tests/test_self_modifier_engine.py)

Erwarteter Effekt:
- laufender Stand bleibt bis zum Ende unberührt
- fehlgeschlagene Tests hinterlassen keine halbangewandte Änderung
- Diff und Workspace sind nachvollziehbar erzeugt
