from tools.lean_tool.specs import BUILTIN_SPECS, build_combined_mathlib_specs


def test_combined_mathlib_specs_has_single_import() -> None:
    combined = build_combined_mathlib_specs()
    assert combined.count("import Mathlib") == 1


def test_combined_mathlib_specs_contains_all_theorems() -> None:
    combined = build_combined_mathlib_specs()
    for name in BUILTIN_SPECS:
        assert f"theorem {name}" in combined
