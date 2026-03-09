from tools.planner.tool import _safe_eval_expression, _substitute_variables


def test_planner_substitute_keeps_numeric_type_for_full_expression() -> None:
    context = {"coords": {"bbox": {"x1": 10, "x2": 14}}}

    result = _substitute_variables("{{ (coords.bbox.x1 + coords.bbox.x2) // 2 }}", context)

    assert result == 12
    assert isinstance(result, int)


def test_planner_substitute_interpolates_inside_string() -> None:
    context = {"query": "berlin hotels"}

    result = _substitute_variables("https://google.com/search?q={{query}}", context)

    assert result == "https://google.com/search?q=berlin hotels"


def test_planner_safe_eval_supports_attribute_and_subscript_access() -> None:
    context = {"items": [{"value": 3}, {"value": 9}]}

    result = _safe_eval_expression("items[1].value - items[0].value", context)

    assert result == 6


def test_planner_safe_eval_rejects_function_calls() -> None:
    context = {"coords": {"bbox": {"x1": 10}}}

    result = _substitute_variables("{{ __import__('os').system('id') }}", context)

    assert result == "{{ __import__('os').system('id') }}"
