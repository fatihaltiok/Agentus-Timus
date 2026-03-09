import deal

from tools.planner.tool import _safe_eval_expression


@deal.pre(lambda left, right: isinstance(left, int) and isinstance(right, int))
@deal.post(lambda r: isinstance(r, int))
def safe_floor_div_center(left: int, right: int) -> int:
    context = {"bbox": {"x1": left, "x2": right}}
    return _safe_eval_expression("(bbox.x1 + bbox.x2) // 2", context)


@deal.pre(lambda value: isinstance(value, str) and value.strip() != "")
@deal.post(lambda r: isinstance(r, str))
def safe_name_lookup(value: str) -> str:
    return _safe_eval_expression("query", {"query": value})
