# utils/skill_parser.py
"""
Parser für SKILL.md Dateien.
Parst YAML Frontmatter + Markdown Body (OpenClaw kompatibel).
"""

import re
import yaml
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
import logging

from .skill_types import Skill, SkillMetadata

log = logging.getLogger(__name__)


class SkillParseError(Exception):
    """Fehler beim Parsen einer SKILL.md Datei"""
    pass


def parse_skill_md(skill_md_path: Path) -> Skill:
    """
    Parst eine SKILL.md Datei.
    
    Format:
    ```
    ---
    name: skill-name
    description: Beschreibung wann dieser Skill verwendet wird
    ---
    
    # Markdown Content
    Instructions...
    ```
    
    Args:
        skill_md_path: Pfad zur SKILL.md Datei
        
    Returns:
        Skill Objekt mit Metadata und Body
        
    Raises:
        SkillParseError: Bei ungültigem Format
        FileNotFoundError: Wenn Datei nicht existiert
    """
    if not skill_md_path.exists():
        raise FileNotFoundError(f"SKILL.md nicht gefunden: {skill_md_path}")
    
    try:
        content = skill_md_path.read_text(encoding='utf-8')
    except Exception as e:
        raise SkillParseError(f"Fehler beim Lesen von {skill_md_path}: {e}")
    
    # Parse Frontmatter und Body
    metadata, body = _parse_frontmatter_and_body(content, skill_md_path.name)
    
    # Erstelle Skill-Objekt
    skill_dir = skill_md_path.parent
    
    return Skill(
        metadata=metadata,
        body=body,
        body_loaded=True,  # Body ist sofort geladen (im Gegensatz zu OpenClaw)
        skill_dir=skill_dir,
        skill_md_path=skill_md_path
    )


def _parse_frontmatter_and_body(content: str, filename: str = "SKILL.md") -> Tuple[SkillMetadata, str]:
    """
    Extrahiert YAML Frontmatter und Markdown Body.
    
    Unterstützt:
    - Standard YAML Frontmatter (--- ... ---)
    - Fehlendes Frontmatter (nur Body)
    - Leere Dateien
    
    Returns:
        Tuple von (SkillMetadata, body_string)
    """
    content = content.strip()
    
    if not content:
        raise SkillParseError(f"{filename} ist leer")
    
    # Suche YAML Frontmatter
    # Pattern: --- am Anfang, dann YAML, dann ---
    frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n?'
    match = re.match(frontmatter_pattern, content, re.DOTALL)
    
    if match:
        # Frontmatter gefunden
        yaml_content = match.group(1)
        body = content[match.end():].strip()
        
        # Parse YAML
        try:
            yaml_data = yaml.safe_load(yaml_content) or {}
        except yaml.YAMLError as e:
            raise SkillParseError(f"Ungültiges YAML in Frontmatter: {e}")
        
        # Erstelle Metadata
        metadata = _create_metadata_from_yaml(yaml_data, filename)
        
    else:
        # Kein Frontmatter - versuche aus Body zu extrahieren oder Default
        log.warning(f"{filename}: Kein YAML Frontmatter gefunden, verwende Defaults")
        
        # Versuche ersten Header als Name zu nehmen
        name_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        name = name_match.group(1).strip() if name_match else Path(filename).stem
        
        # Erste Zeile als Description
        lines = content.strip().split('\n')
        description = lines[0][:100] if lines else f"Skill {name}"
        
        metadata = SkillMetadata(
            name=_sanitize_name(name),
            description=description
        )
        body = content
    
    return metadata, body


def _create_metadata_from_yaml(yaml_data: Dict[str, Any], filename: str) -> SkillMetadata:
    """
    Erstellt SkillMetadata aus YAML-Daten.
    
    Validiert required fields und setzt Defaults.
    """
    # Required: name
    name = yaml_data.get('name')
    if not name:
        # Versuche aus Filename zu extrahieren
        name = Path(filename).stem
        log.warning(f"Kein 'name' in Frontmatter, verwende: {name}")
    
    name = _sanitize_name(str(name))
    
    # Required: description
    description = yaml_data.get('description')
    if not description:
        description = f"Skill for {name}"
        log.warning(f"Kein 'description' in Frontmatter, verwende: {description}")
    
    # Optionale Felder
    version = yaml_data.get('version')
    author = yaml_data.get('author')
    
    # Tags können String oder List sein
    tags = yaml_data.get('tags', [])
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',')]
    
    return SkillMetadata(
        name=name,
        description=str(description),
        version=str(version) if version else None,
        author=str(author) if author else None,
        tags=tags
    )


def _sanitize_name(name: str) -> str:
    """
    Bereinigt Skill-Namen für konsistente Formatierung.
    
    Konvertiert zu: lowercase, letters/digits/hyphens only
    """
    # Convert to lowercase
    name = name.lower()
    
    # Replace spaces and underscores with hyphens
    name = name.replace(' ', '-').replace('_', '-')
    
    # Remove invalid characters (keep only letters, digits, hyphens)
    name = re.sub(r'[^a-z0-9\-]', '', name)
    
    # Remove multiple consecutive hyphens
    name = re.sub(r'-+', '-', name)
    
    # Remove leading/trailing hyphens
    name = name.strip('-')
    
    return name


def validate_skill(skill: Skill) -> Tuple[bool, Optional[str]]:
    """
    Validiert einen Skill.
    
    Returns:
        Tuple von (is_valid, error_message)
    """
    errors = []
    
    # Check: Name
    if not skill.name or len(skill.name) < 2:
        errors.append("Name ist zu kurz (min. 2 Zeichen)")
    
    if len(skill.name) > 64:
        errors.append("Name ist zu lang (max. 64 Zeichen)")
    
    # Check: Description
    if not skill.description or len(skill.description) < 10:
        errors.append("Description ist zu kurz (min. 10 Zeichen)")
    
    if len(skill.description) > 500:
        errors.append("Description ist zu lang (max. 500 Zeichen, aktuell: " + 
                     f"{len(skill.description)})")
    
    # Check: Body
    if not skill.body or len(skill.body) < 50:
        errors.append("Body ist zu kurz (min. 50 Zeichen)")
    
    # Check: Skill-Dir existiert
    if not skill.skill_dir.exists():
        errors.append(f"Skill-Ordner existiert nicht: {skill.skill_dir}")
    
    # Check: Scripts sind ausführbar (optional Warnung)
    scripts = skill.get_scripts()
    for script_name, script in scripts.items():
        if script.resource_type == "script":
            # Prüfe ob Python/Bash
            if not script.path.suffix in ['.py', '.sh', '.bash']:
                errors.append(f"Script {script_name} hat unbekanntes Format: {script.path.suffix}")
    
    if errors:
        return False, "; ".join(errors)
    
    return True, None


def extract_skill_info(skill_md_path: Path) -> Dict[str, Any]:
    """
    Extrahiert alle Informationen aus einer SKILL.md (für Debugging/Übersicht).
    
    Returns:
        Dict mit allen Skill-Informationen
    """
    skill = parse_skill_md(skill_md_path)
    
    return {
        "name": skill.name,
        "description": skill.description,
        "version": skill.metadata.version,
        "author": skill.metadata.author,
        "tags": skill.metadata.tags,
        "body_length": len(skill.body),
        "scripts": list(skill.get_scripts().keys()),
        "references": list(skill.get_references().keys()),
        "assets": list(skill.get_assets().keys()),
        "path": str(skill.skill_dir)
    }


def find_all_skills(base_dir: Path = Path("skills")) -> Dict[str, Path]:
    """
    Findet alle Skills in einem Verzeichnis.
    
    Args:
        base_dir: Basis-Verzeichnis (default: skills/)
        
    Returns:
        Dict von {skill_name: skill_md_path}
    """
    skills = {}
    
    if not base_dir.exists():
        log.warning(f"Skill-Verzeichnis nicht gefunden: {base_dir}")
        return skills
    
    for skill_dir in base_dir.iterdir():
        if skill_dir.is_dir():
            skill_md = skill_dir / "SKILL.md"
            if skill_md.exists():
                try:
                    # Parse um Namen zu bekommen
                    skill = parse_skill_md(skill_md)
                    skills[skill.name] = skill_md
                except Exception as e:
                    log.error(f"Fehler beim Parsen von {skill_md}: {e}")
    
    return skills


# Für direkte Nutzung
if __name__ == "__main__":
    # Test-Code
    import sys
    
    if len(sys.argv) > 1:
        test_path = Path(sys.argv[1])
        if test_path.exists():
            try:
                skill = parse_skill_md(test_path)
                print(f"✅ Parsed: {skill.name}")
                print(f"   Description: {skill.description[:50]}...")
                print(f"   Scripts: {len(skill.get_scripts())}")
                print(f"   References: {len(skill.get_references())}")
                
                is_valid, error = validate_skill(skill)
                if is_valid:
                    print("   Status: ✅ Valid")
                else:
                    print(f"   Status: ❌ Invalid - {error}")
            except Exception as e:
                print(f"❌ Fehler: {e}")
        else:
            print(f"❌ Datei nicht gefunden: {test_path}")
    else:
        print("Verwendung: python skill_parser.py <path/to/SKILL.md>")
