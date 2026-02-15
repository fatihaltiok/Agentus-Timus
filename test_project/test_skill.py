import os
import pytest


if os.getenv("RUN_SKILL_TEST") != "1":
    pytest.skip("Skill-Test ist manuell und benötigt UI-Umgebung.", allow_module_level=True)


def test_visual_navigator_skill():
    import sys
    from pathlib import Path
    from dotenv import load_dotenv

    project_root = Path(__file__).parent
    dotenv_path = project_root / ".env"
    load_dotenv(dotenv_path=dotenv_path)

    sys.path.insert(0, str(project_root))

    from skills.visual_navigator_skill import click_element_on_screen

    description = "die 'Aktivitäten' Schaltfläche ganz oben links in der Ecke des Bildschirms"
    result = click_element_on_screen(description)
    assert result is not None