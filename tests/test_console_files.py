from pathlib import Path

from server import mcp_server


def test_collect_console_files_lists_uploads_and_results(monkeypatch, tmp_path):
    project_root = tmp_path
    results_dir = project_root / "results"
    uploads_dir = project_root / "data" / "uploads"
    results_dir.mkdir(parents=True)
    uploads_dir.mkdir(parents=True)

    result_file = results_dir / "report.pdf"
    upload_file = uploads_dir / "source.txt"
    result_file.write_bytes(b"%PDF-1.4 test")
    upload_file.write_text("hello", encoding="utf-8")

    monkeypatch.setattr(mcp_server, "project_root", project_root)

    files = mcp_server._collect_console_files(limit=10)

    paths = {item["path"] for item in files}
    assert "results/report.pdf" in paths
    assert "data/uploads/source.txt" in paths
    by_path = {item["path"]: item for item in files}
    assert by_path["results/report.pdf"]["origin"] == "result"
    assert by_path["results/report.pdf"]["type"] == "pdf"
    assert by_path["data/uploads/source.txt"]["origin"] == "upload"
    assert by_path["data/uploads/source.txt"]["type"] == "document"


def test_resolve_console_file_path_rejects_outside_allowed_roots(monkeypatch, tmp_path):
    project_root = tmp_path
    results_dir = project_root / "results"
    uploads_dir = project_root / "data" / "uploads"
    results_dir.mkdir(parents=True)
    uploads_dir.mkdir(parents=True)

    allowed = results_dir / "ok.pdf"
    blocked = project_root / "secrets.txt"
    allowed.write_bytes(b"%PDF")
    blocked.write_text("nope", encoding="utf-8")

    monkeypatch.setattr(mcp_server, "project_root", project_root)

    assert mcp_server._resolve_console_file_path("results/ok.pdf") == allowed.resolve()
    assert mcp_server._resolve_console_file_path("secrets.txt") is None
    assert mcp_server._resolve_console_file_path("../secrets.txt") is None
