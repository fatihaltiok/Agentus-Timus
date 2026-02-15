# tests/test_skill_parser.py
"""
Tests für den SKILL.md Parser.
"""

import pytest
from pathlib import Path
import tempfile
import shutil

# Add project root to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.skill_parser import (
    parse_skill_md,
    validate_skill,
    _parse_frontmatter_and_body,
    _sanitize_name,
    SkillParseError
)
from utils.skill_types import Skill, SkillMetadata


class TestSkillParser:
    """Tests für parse_skill_md Funktion"""
    
    def test_parse_valid_skill_with_frontmatter(self, tmp_path):
        """Test: Gültige SKILL.md mit YAML Frontmatter"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: test-skill
description: A test skill for unit testing
version: 1.0.0
author: Test Author
tags: test, unit, example
---

# Test Skill

## Quick Start
This is a test skill.

## Usage
```python
print("Hello World")
```
""")
        
        skill = parse_skill_md(skill_md)
        
        assert skill.name == "test-skill"
        assert skill.description == "A test skill for unit testing"
        assert skill.metadata.version == "1.0.0"
        assert skill.metadata.author == "Test Author"
        assert skill.metadata.tags == ["test", "unit", "example"]
        assert "Test Skill" in skill.body
        assert skill.body_loaded is True
    
    def test_parse_skill_without_frontmatter(self, tmp_path):
        """Test: SKILL.md ohne Frontmatter (nur Body)"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""# My Awesome Skill

This is the description of my awesome skill.

## Instructions
Do something awesome.
""")
        
        skill = parse_skill_md(skill_md)
        
        # Sollte aus ersten Header ableiten
        assert skill.name == "my-awesome-skill"  # Normalized
        assert "My Awesome Skill" in skill.description
        assert "awesome" in skill.body.lower()
    
    def test_parse_skill_minimal(self, tmp_path):
        """Test: Minimalistische SKILL.md"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: minimal
description: Minimal description here
---

Minimal body.
""")
        
        skill = parse_skill_md(skill_md)
        
        assert skill.name == "minimal"
        assert skill.description == "Minimal description here"
        assert "Minimal body" in skill.body
    
    def test_parse_empty_file_raises_error(self, tmp_path):
        """Test: Leere Datei sollte Fehler werfen"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("")
        
        with pytest.raises(SkillParseError, match="leer"):
            parse_skill_md(skill_md)
    
    def test_parse_invalid_yaml_raises_error(self, tmp_path):
        """Test: Ungültiges YAML sollte Fehler werfen"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: test
invalid: yaml: here: unbalanced
---

Body.
""")
        
        with pytest.raises(SkillParseError, match="YAML"):
            parse_skill_md(skill_md)
    
    def test_file_not_found_raises_error(self, tmp_path):
        """Test: Fehlende Datei sollte FileNotFoundError werfen"""
        non_existent = tmp_path / "NONEXISTENT.md"
        
        with pytest.raises(FileNotFoundError):
            parse_skill_md(non_existent)


class TestSkillValidation:
    """Tests für validate_skill Funktion"""
    
    def test_valid_skill_passes_validation(self, tmp_path):
        """Test: Gültiger Skill sollte validiert werden"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: valid-skill
description: This is a valid description for testing
---

# Valid Skill

This is the body of the valid skill. It has more than 50 characters here.
""")
        
        skill = parse_skill_md(skill_md)
        is_valid, error = validate_skill(skill)
        
        assert is_valid is True
        assert error is None
    
    def test_short_name_fails_validation(self, tmp_path):
        """Test: Zu kurzer Name sollte fehlschlagen"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: a
description: Valid description here
---

Body content here with enough characters to pass the body length check.
""")
        
        skill = parse_skill_md(skill_md)
        is_valid, error = validate_skill(skill)
        
        assert is_valid is False
        assert "zu kurz" in error.lower()
    
    def test_short_description_fails_validation(self, tmp_path):
        """Test: Zu kurze Description sollte fehlschlagen"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: test-skill
description: Short
---

Body content here with enough characters to pass the body length check.
""")
        
        skill = parse_skill_md(skill_md)
        is_valid, error = validate_skill(skill)
        
        assert is_valid is False
        assert "description" in error.lower()
    
    def test_short_body_fails_validation(self, tmp_path):
        """Test: Zu kurzer Body sollte fehlschlagen"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: test-skill
description: Valid description here for testing
---

Short.
""")
        
        skill = parse_skill_md(skill_md)
        is_valid, error = validate_skill(skill)
        
        assert is_valid is False
        assert "body" in error.lower()


class TestNameSanitization:
    """Tests für _sanitize_name Funktion"""
    
    def test_lowercase_conversion(self):
        assert _sanitize_name("MySkill") == "myskill"
    
    def test_space_to_hyphen(self):
        assert _sanitize_name("my skill") == "my-skill"
    
    def test_underscore_to_hyphen(self):
        assert _sanitize_name("my_skill") == "my-skill"
    
    def test_invalid_chars_removed(self):
        assert _sanitize_name("my@skill#123!") == "myskill123"
    
    def test_multiple_hyphens_collapsed(self):
        assert _sanitize_name("my---skill") == "my-skill"
    
    def test_leading_trailing_hyphens_removed(self):
        assert _sanitize_name("-my-skill-") == "my-skill"


class TestSkillTypes:
    """Tests für Skill Dataclass"""
    
    def test_should_trigger_with_name_match(self, tmp_path):
        """Test: Skill sollte bei Name-Match triggern"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: pdf-processor
description: Process PDF files
---

Process PDFs.
""")
        
        skill = parse_skill_md(skill_md)
        
        # Sollte triggern wenn Task den Namen enthält
        assert skill.should_trigger("process a pdf file") is True
        assert skill.should_trigger("use pdf processor") is True
        
        # Sollte nicht triggern bei unabhängigem Task
        # (außer Keywords matchen zufällig)
    
    def test_get_full_context(self, tmp_path):
        """Test: Context-Generierung"""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("""---
name: context-test
description: Test context generation
version: 1.0
tags: test, context
---

# Instructions

Do this and that.
""")
        
        skill = parse_skill_md(skill_md)
        context = skill.get_full_context()
        
        assert "Skill: context-test" in context
        assert "Test context generation" in context
        assert "Instructions" in context
        assert "1.0" in context


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
