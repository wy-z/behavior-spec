from pathlib import Path

from bspec import checks, loader
from bspec.model import ALL_KINDS, Project, Symbol

FIXTURES = Path(__file__).parent / "fixtures"


def _proj(**kinds) -> Project:
    p = Project(root="/nonexistent", symbols={k: {} for k in ALL_KINDS})
    for kind, objs in kinds.items():
        for o in objs:
            p.symbols[kind][o["id"]] = Symbol(kind, o["id"], o, "f.bspec.json")
    return p


def _codes(diags, severity=None):
    return {d.code for d in diags if severity is None or d.severity == severity}


def test_valid_fixture_is_clean():
    proj, ld = loader.load_project(str(FIXTURES / "valid"))
    diags = ld + checks.run(proj)
    assert [d.to_dict() for d in diags if d.severity == "error"] == []
    assert [d.to_dict() for d in diags if d.severity == "warning"] == []


def test_unresolved_event():
    p = _proj(behavior=[{"id": "b", "when": {"event": "ghost"}, "then": [{"assert": {"cel": "true"}}]}])
    assert "unresolved-ref" in _codes(checks.run(p), "error")


def test_direction_mismatch_on_trigger():
    p = _proj(
        interface=[{"id": "io", "direction": "bidirectional"}],
        event=[{"id": "e.out", "direction": "output", "interface": "io", "payloadSchema": {"type": "object", "additionalProperties": False}}],
        behavior=[{"id": "b", "when": {"event": "e.out"}, "then": [{"assert": {"cel": "true"}}]}],
    )
    assert "direction-mismatch" in _codes(checks.run(p), "error")


def test_observable_prefix_collision():
    p = _proj(observable=[
        {"id": "portfolio", "role": "state", "valueSchema": {"type": "number"}},
        {"id": "portfolio.gross", "role": "state", "valueSchema": {"type": "number"}},
    ])
    assert "observable-prefix" in _codes(checks.run(p), "error")


def test_prefix_collision_is_global_across_roles():
    # spec 4.3: the prefix ban is global, not per-namespace-bucket
    p = _proj(observable=[
        {"id": "limit", "role": "state", "valueSchema": {"type": "number"}},
        {"id": "limit.max", "role": "parameter", "valueSchema": {"type": "number"}},
    ])
    assert "observable-prefix" in _codes(checks.run(p), "error")


def test_schema_subset_rejects_oneof():
    p = _proj(observable=[
        {"id": "x", "role": "state", "valueSchema": {"oneOf": [{"type": "number"}, {"type": "string"}]}},
    ])
    assert "schema-subset" in _codes(checks.run(p), "error")


def test_schema_subset_requires_additional_properties_false():
    p = _proj(observable=[
        {"id": "x", "role": "state", "valueSchema": {"type": "object", "properties": {"a": {"type": "number"}}}},
    ])
    assert "schema-subset" in _codes(checks.run(p), "error")


def test_stub_summary_rejected():
    # a summary that just echoes the title carries no explanation for the reviewer
    p = _proj(behavior=[
        {"id": "b", "title": "X", "summary": "X",
         "when": {"event": "e"}, "then": [{"assert": {"cel": "true"}}]},
    ])
    assert "stub-summary" in _codes(checks.run(p), "error")


def test_schema_subset_requires_type():
    # an untyped schema becomes `dyn` and silently defeats CEL type-checking
    p = _proj(observable=[{"id": "x", "role": "state", "valueSchema": {}}])
    assert "schema-subset" in _codes(checks.run(p), "error")


def test_schema_subset_rejects_unknown_keyword():
    p = _proj(observable=[
        {"id": "x", "role": "state", "valueSchema": {"type": "number", "minimun": 0}},
    ])
    assert "schema-subset" in _codes(checks.run(p), "error")
