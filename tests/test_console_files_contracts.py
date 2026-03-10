import deal


@deal.pre(lambda rel_path: isinstance(rel_path, str))
@deal.post(lambda result: isinstance(result, bool))
def is_allowed_console_rel_path(rel_path: str) -> bool:
    normalized = rel_path.strip().lstrip("/")
    if not normalized or ".." in normalized.split("/"):
        return False
    return normalized.startswith("results/") or normalized.startswith("data/uploads/")


def test_allowed_console_paths():
    assert is_allowed_console_rel_path("results/report.pdf") is True
    assert is_allowed_console_rel_path("data/uploads/input.txt") is True


def test_blocked_console_paths():
    assert is_allowed_console_rel_path("../secret.txt") is False
    assert is_allowed_console_rel_path("timus_server.log") is False
