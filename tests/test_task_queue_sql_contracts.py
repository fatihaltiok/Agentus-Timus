import json

import deal

from orchestration.task_queue import _json_array_param


@deal.post(lambda r: isinstance(r, str) and r.startswith("[") and r.endswith("]"))
def build_json_array(values: list[str]) -> str:
    return _json_array_param(values)


@deal.pre(lambda values: all(isinstance(v, str) for v in values))
@deal.post(lambda r: isinstance(r, list))
@deal.post(lambda r: all(isinstance(v, str) for v in r))
def roundtrip_json_array(values: list[str]) -> list[str]:
    return json.loads(_json_array_param(values))
