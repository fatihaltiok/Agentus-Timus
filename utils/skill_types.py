# utils/skill_types.py
"""
Dataclasses für das Skill-System.
Basierend auf OpenClaw Architektur.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

log = logging.getLogger(__name__)


@dataclass
class SkillMetadata:
    """YAML Frontmatter aus SKILL.md"""
    name: str
    description: str
    # Optionale Felder
    version: Optional[str] = None
    author: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    
    @property
    def trigger_keywords(self) -> List[str]:
        """Extrahiert Keywords aus Description für Trigger-Matching"""
        # Einfache Keyword-Extraktion
        words = self.description.lower().split()
        # Filtere relevante Wörter (Substantive, Verben)
        keywords = [w for w in words if len(w) > 3 and w.isalpha()]
        return list(set(keywords))[:20]  # Max 20 Keywords


@dataclass
class SkillResource:
    """Referenz zu einem Skill-Resource (Script, Reference, Asset)"""
    name: str
    path: Path
    resource_type: str  # "script", "reference", "asset"
    
    def load_content(self) -> Optional[str]:
        """Lädt Inhalt falls textbasiert"""
        if self.resource_type in ["script", "reference"]:
            try:
                return self.path.read_text(encoding='utf-8')
            except Exception as e:
                log.error(f"Fehler beim Laden von {self.path}: {e}")
                return None
        return None
    
    def exists(self) -> bool:
        return self.path.exists()


@dataclass
class Skill:
    """
    Repräsentiert einen kompletten Skill.
    
    Entspricht einem Skill-Ordner mit:
    - SKILL.md (Metadata + Body)
    - scripts/ (optional)
    - references/ (optional)
    - assets/ (optional)
    """
    
    # Metadaten (immer geladen)
    metadata: SkillMetadata
    
    # Body (nur bei Trigger geladen)
    body: str
    body_loaded: bool = False
    
    # Pfade
    skill_dir: Path = field(default=Path())
    skill_md_path: Path = field(default=Path())
    
    # Ressourcen (on-demand geladen)
    _scripts: Dict[str, SkillResource] = field(default_factory=dict)
    _references: Dict[str, SkillResource] = field(default_factory=dict)
    _assets: Dict[str, SkillResource] = field(default_factory=dict)
    _resources_loaded: bool = False
    
    def __post_init__(self):
        """Initialisiert Ressourcen-Pfade"""
        if not self.skill_dir:
            return
            
        self._scripts_dir = self.skill_dir / "scripts"
        self._references_dir = self.skill_dir / "references"
        self._assets_dir = self.skill_dir / "assets"
    
    @property
    def name(self) -> str:
        return self.metadata.name
    
    @property
    def description(self) -> str:
        return self.metadata.description
    
    def should_trigger(self, task: str) -> bool:
        """
        Bestimmt ob dieser Skill für einen Task relevant ist.
        Einfache Keyword-Matching-Logik.
        """
        task_lower = task.lower()
        keywords = self.metadata.trigger_keywords
        
        # Zähle Keyword-Matches
        matches = sum(1 for kw in keywords if kw in task_lower)
        
        # Threshold: Mindestens 2 Keywords oder mindestens ein Namensteil im Task
        name_parts = self.name.lower().replace('-', ' ').split()
        name_match = any(part in task_lower for part in name_parts if len(part) > 2)
        return matches >= 2 or name_match
    
    def get_scripts(self) -> Dict[str, SkillResource]:
        """Liefert alle Scripts (lazy loading)"""
        if not self._resources_loaded:
            self._load_resources()
        return self._scripts
    
    def get_references(self) -> Dict[str, SkillResource]:
        """Liefert alle References (lazy loading)"""
        if not self._resources_loaded:
            self._load_resources()
        return self._references
    
    def get_assets(self) -> Dict[str, SkillResource]:
        """Liefert alle Assets (lazy loading)"""
        if not self._resources_loaded:
            self._load_resources()
        return self._assets
    
    def load_reference(self, name: str) -> Optional[str]:
        """
        Lädt eine spezifische Reference on-demand.
        
        Args:
            name: Name der Reference-Datei (z.B. "schema.md")
            
        Returns:
            Inhalt der Datei oder None
        """
        if not self._resources_loaded:
            self._load_resources()
        
        if name in self._references:
            return self._references[name].load_content()
        
        # Versuche zu finden falls noch nicht geladen
        ref_path = self._references_dir / name
        if ref_path.exists():
            try:
                return ref_path.read_text(encoding='utf-8')
            except Exception as e:
                log.error(f"Fehler beim Laden von Reference {name}: {e}")
        
        return None
    
    def execute_script(self, script_name: str, *args, **kwargs) -> Any:
        """
        Führt ein Script aus dem Skill aus.
        
        Args:
            script_name: Name des Scripts (z.B. "rotate_pdf.py")
            *args, **kwargs: Argumente für das Script
            
        Returns:
            Ergebnis der Script-Ausführung
        """
        scripts = self.get_scripts()
        if script_name not in scripts:
            raise FileNotFoundError(f"Script {script_name} nicht gefunden in Skill {self.name}")
        
        script = scripts[script_name]
        script_path = script.path
        
        # Führe Python-Script aus
        if script_path.suffix == '.py':
            import subprocess
            import sys
            
            cmd = [sys.executable, str(script_path)] + list(args)
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=str(self.skill_dir)
                )
                return {
                    "success": result.returncode == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }
            except subprocess.TimeoutExpired:
                return {"success": False, "error": "Script-Timeout (60s)"}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        # Führe Bash-Script aus
        elif script_path.suffix == '.sh':
            import subprocess
            
            try:
                result = subprocess.run(
                    ['bash', str(script_path)] + list(args),
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=str(self.skill_dir)
                )
                return {
                    "success": result.returncode == 0,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode
                }
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        else:
            raise ValueError(f"Nicht unterstütztes Script-Format: {script_path.suffix}")
    
    def _load_resources(self):
        """Lazy loading aller Ressourcen"""
        if self._resources_loaded:
            return
        
        # Scanne Verzeichnisse
        if hasattr(self, '_scripts_dir') and self._scripts_dir.exists():
            for script_file in self._scripts_dir.iterdir():
                if script_file.is_file():
                    self._scripts[script_file.name] = SkillResource(
                        name=script_file.name,
                        path=script_file,
                        resource_type="script"
                    )
        
        if hasattr(self, '_references_dir') and self._references_dir.exists():
            for ref_file in self._references_dir.iterdir():
                if ref_file.is_file():
                    self._references[ref_file.name] = SkillResource(
                        name=ref_file.name,
                        path=ref_file,
                        resource_type="reference"
                    )
        
        if hasattr(self, '_assets_dir') and self._assets_dir.exists():
            for asset_file in self._assets_dir.iterdir():
                if asset_file.is_file():
                    self._assets[asset_file.name] = SkillResource(
                        name=asset_file.name,
                        path=asset_file,
                        resource_type="asset"
                    )
        
        self._resources_loaded = True
        log.debug(f"Skill {self.name}: {len(self._scripts)} Scripts, "
                  f"{len(self._references)} References, {len(self._assets)} Assets geladen")
    
    def get_full_context(self, include_references: List[str] = None) -> str:
        """
        Baut den vollständigen Kontext für diesen Skill.
        
        Progressive Disclosure:
        1. Metadata (immer)
        2. Body (bei Trigger)
        3. References (on-demand)
        
        Args:
            include_references: Liste von Reference-Dateien die zusätzlich geladen werden sollen
            
        Returns:
            Vollständiger Kontext als String
        """
        context_parts = []
        
        # 1. Metadata (immer)
        context_parts.append(f"# Skill: {self.metadata.name}")
        context_parts.append(f"Description: {self.metadata.description}")
        if self.metadata.version:
            context_parts.append(f"Version: {self.metadata.version}")
        if self.metadata.tags:
            context_parts.append(f"Tags: {', '.join(self.metadata.tags)}")
        context_parts.append("")
        
        # 2. Body (wenn geladen)
        if self.body:
            context_parts.append("## Instructions")
            context_parts.append(self.body)
            context_parts.append("")
        
        # 3. Scripts (nur Namen, nicht Inhalt - spart Tokens)
        scripts = self.get_scripts()
        if scripts:
            context_parts.append("## Available Scripts")
            for name in scripts.keys():
                context_parts.append(f"- {name}")
            context_parts.append("")
        
        # 4. References (on-demand)
        if include_references:
            context_parts.append("## References")
            for ref_name in include_references:
                ref_content = self.load_reference(ref_name)
                if ref_content:
                    context_parts.append(f"### {ref_name}")
                    context_parts.append(ref_content[:2000])  # Max 2000 chars pro Reference
                    context_parts.append("")
        
        # 5. Available References (nur Namen)
        refs = self.get_references()
        if refs:
            context_parts.append("## Available References")
            for name in refs.keys():
                context_parts.append(f"- {name}")
            context_parts.append("")
        
        return "\n".join(context_parts)


@dataclass
class SkillRegistry:
    """Registry für alle geladenen Skills"""
    
    skills: Dict[str, Skill] = field(default_factory=dict)
    _initialized: bool = False
    
    def register(self, skill: Skill):
        """Registriert einen Skill"""
        self.skills[skill.name] = skill
        log.info(f"✅ Skill registriert: {skill.name}")
    
    def get(self, name: str) -> Optional[Skill]:
        """Holt einen Skill by Name"""
        return self.skills.get(name)
    
    def select_for_task(self, task: str, top_k: int = 3) -> List[Skill]:
        """
        Wählt die besten Skills für einen Task aus.
        
        Args:
            task: Der zu erledigende Task
            top_k: Maximale Anzahl Skills
            
        Returns:
            Liste der relevantesten Skills
        """
        scored_skills = []
        
        for skill in self.skills.values():
            # Score basierend auf Keyword-Matches
            score = self._calculate_relevance_score(skill, task)
            if score > 0:
                scored_skills.append((skill, score))
        
        # Sortiere nach Score
        scored_skills.sort(key=lambda x: x[1], reverse=True)
        
        return [skill for skill, _ in scored_skills[:top_k]]
    
    def _calculate_relevance_score(self, skill: Skill, task: str) -> float:
        """Berechnet Relevanz-Score für Skill-Task-Matching"""
        task_lower = task.lower()
        score = 0.0
        
        # Name-Match ist stark gewichtet
        if skill.name.lower().replace('-', ' ') in task_lower:
            score += 10.0
        
        # Keyword-Matches
        keywords = skill.metadata.trigger_keywords
        for kw in keywords:
            if kw in task_lower:
                score += 1.0
        
        return score
    
    def list_all(self) -> List[str]:
        """Listet alle Skill-Namen auf"""
        return list(self.skills.keys())
    
    def load_all_from_directory(self, directory: Path = Path("skills")):
        """Lädt alle Skills aus einem Verzeichnis"""
        if not directory.exists():
            log.warning(f"Skill-Verzeichnis {directory} existiert nicht")
            return
        
        from .skill_parser import parse_skill_md
        
        for skill_dir in directory.iterdir():
            if skill_dir.is_dir():
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists():
                    try:
                        skill = parse_skill_md(skill_md)
                        self.register(skill)
                    except Exception as e:
                        log.error(f"Fehler beim Laden von Skill {skill_dir.name}: {e}")
        
        self._initialized = True
        log.info(f"✅ {len(self.skills)} Skills aus {directory} geladen")
