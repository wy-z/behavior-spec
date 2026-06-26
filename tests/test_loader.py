import json
from pathlib import Path

from bspec import loader

FIXTURES = Path(__file__).parent / "fixtures"


def _write(p: Path, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj))


def _errors(diags):
    return [d for d in diags if d.severity == "error"]


def test_load_valid_project_indexes_all_kinds():
    proj, diags = loader.load_project(str(FIXTURES / "valid"))
    assert _errors(diags) == []
    assert len(proj.kind("module")) == 1
    assert len(proj.kind("observable")) == 6
    assert len(proj.kind("event")) == 2
    assert len(proj.kind("interface")) == 2
    assert len(proj.kind("behavior")) == 2
    assert len(proj.kind("invariant")) == 1
    assert len(proj.kind("flow")) == 1
    assert proj.get("behavior", "trading.ma-cross.open-long") is not None
    assert proj.membership[("behavior", "trading.ma-cross.open-long")] == "trading.ma-cross"


def test_duplicate_ids_reported():
    _, diags = loader.load_project(str(FIXTURES / "dups"))
    codes = {d.code for d in _errors(diags)}
    assert "duplicate-id" in codes


def test_invalid_file_reports_schema_error():
    _, diags = loader.load_project(str(FIXTURES / "invalid"))
    assert any(d.code == "schema" for d in _errors(diags))


def test_find_root_locates_behavior_dir():
    nested = FIXTURES / "valid" / "behavior"
    assert loader.find_root(str(nested)) == str(FIXTURES / "valid")


def test_find_root_searches_down_for_bspec_json(tmp_path):
    # run from a parent (e.g. repo root): root is discovered downward at bspec.json
    _write(tmp_path / "docs" / "behavior" / "bspec.json",
           {"version": "0.1.0", "specGlobs": ["**/*.bspec.json"], "reviews": {}})
    assert loader.find_root(str(tmp_path)) == str(tmp_path / "docs" / "behavior")


def test_find_root_prefers_bspec_json_over_behavior_dir(tmp_path):
    # bspec.json is authoritative; a behavior/ dir above it must not shadow it
    _write(tmp_path / "behavior" / "x.bspec.json", {"bspecVersion": "0.1.0",
           "module": {"id": "x", "summary": "above"}})
    root = tmp_path / "docs" / "specs"
    _write(root / "bspec.json", {"version": "0.1.0", "specGlobs": ["**/*.bspec.json"], "reviews": {}})
    assert loader.find_root(str(root / "deep" / "deeper")) == str(root)


def test_specglobs_honored(tmp_path):
    root = tmp_path / "p"
    _write(root / "bspec.json", {"version": "0.1.0", "specGlobs": ["specs/**/*.bspec.json"], "reviews": {}})
    _write(root / "specs" / "m.bspec.json",
           {"bspecVersion": "0.1.0", "module": {"id": "m", "summary": "specglob fixture"}})
    proj, diags = loader.load_project(str(root))
    assert proj.get("module", "m") is not None
    assert _errors(diags) == []


def test_specglobs_defaults_when_absent(tmp_path):
    root = tmp_path / "p"
    _write(root / "behavior" / "m.bspec.json",
           {"bspecVersion": "0.1.0", "module": {"id": "m", "summary": "default-glob fixture"}})
    proj, _ = loader.load_project(str(root))
    assert proj.get("module", "m") is not None


def test_specglobs_escaping_root_is_ignored(tmp_path):
    _write(tmp_path / "outside.bspec.json", {"bspecVersion": "0.1.0", "module": {"id": "out"}})
    root = tmp_path / "p"
    _write(root / "bspec.json", {"version": "0.1.0", "specGlobs": ["../*.bspec.json"], "reviews": {}})
    proj, diags = loader.load_project(str(root))
    assert proj.get("module", "out") is None
    assert any(d.code == "spec-glob-escape" for d in diags)
