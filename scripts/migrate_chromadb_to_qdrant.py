#!/usr/bin/env python3
"""
scripts/migrate_chromadb_to_qdrant.py — M16: ChromaDB → Qdrant Migration

Liest alle Einträge aus ChromaDB collection 'timus_long_term_memory'
und schreibt sie in Qdrant (QDRANT_PATH, QDRANT_COLLECTION).

Verwendung:
  python scripts/migrate_chromadb_to_qdrant.py [--dry-run]

ENV:
  QDRANT_PATH=./data/qdrant_db
  QDRANT_COLLECTION=timus_memory
"""

import argparse
import os
import sys
from pathlib import Path

# Projekt-Root in PYTHONPATH
sys.path.insert(0, str(Path(__file__).parent.parent))

BATCH_SIZE = 100


def migrate(dry_run: bool = False) -> int:
    """
    Migriert alle ChromaDB-Einträge nach Qdrant.

    Returns:
        Anzahl migrierter Einträge
    """
    # 1. ChromaDB öffnen
    try:
        import chromadb
        from utils.embedding_provider import get_embedding_function

        db_path = Path(__file__).parent.parent / "memory_db"
        client = chromadb.PersistentClient(
            path=str(db_path),
            settings=chromadb.config.Settings(anonymized_telemetry=False),
        )
        collection = client.get_collection(
            name="timus_long_term_memory",
            embedding_function=get_embedding_function(),
        )
        total = collection.count()
        print(f"ChromaDB: {total} Einträge in 'timus_long_term_memory'")
    except Exception as e:
        print(f"❌ ChromaDB nicht verfügbar: {e}")
        return 0

    if total == 0:
        print("ChromaDB ist leer — nichts zu migrieren.")
        return 0

    # 2. Qdrant vorbereiten
    if not dry_run:
        try:
            from memory.qdrant_provider import QdrantProvider
            qdrant = QdrantProvider()
            before_count = qdrant.count()
            print(f"Qdrant: {before_count} Einträge vorher")
        except Exception as e:
            print(f"❌ Qdrant nicht verfügbar: {e}")
            return 0
    else:
        qdrant = None
        print("Dry-Run: Kein Schreiben nach Qdrant")

    # 3. Batch-weise migrieren
    migrated = 0
    offset = 0

    while offset < total:
        try:
            result = collection.get(
                limit=BATCH_SIZE,
                offset=offset,
                include=["documents", "metadatas", "embeddings"],
            )
        except TypeError:
            # Ältere ChromaDB ohne offset-Support
            result = collection.get(
                limit=total,
                include=["documents", "metadatas", "embeddings"],
            )
            offset = total  # Einmaliger Fetch

        ids = result.get("ids", [])
        docs = result.get("documents", [])
        metas = result.get("metadatas", [])
        embeddings = result.get("embeddings")

        if not ids:
            break

        if dry_run:
            print(f"  [Dry-Run] Batch {offset}–{offset+len(ids)}: {len(ids)} Einträge")
        else:
            qdrant.add(
                ids=ids,
                documents=docs,
                metadatas=metas,
                embeddings=embeddings,
            )

        migrated += len(ids)
        offset += len(ids)
        print(f"  Migriert: {migrated}/{total} ({100*migrated//total}%)")

        if offset >= total:
            break

    # 4. Validierung
    if not dry_run and qdrant is not None:
        after_count = qdrant.count()
        print(f"\nQdrant: {after_count} Einträge nachher (vorher: {before_count})")
        added = after_count - before_count
        print(f"Neu hinzugefügt: {added}")

        if added == migrated:
            print(f"✅ Migration erfolgreich: {migrated} Einträge")
        else:
            print(f"⚠️  Zähler-Abweichung: migriert={migrated}, neu={added}")
    else:
        print(f"\nDry-Run abgeschlossen: {migrated} Einträge würden migriert")

    return migrated


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ChromaDB → Qdrant Migration")
    parser.add_argument("--dry-run", action="store_true", help="Nur simulieren, nicht schreiben")
    args = parser.parse_args()

    count = migrate(dry_run=args.dry_run)
    sys.exit(0 if count >= 0 else 1)
