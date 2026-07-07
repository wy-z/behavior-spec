import json
from pathlib import Path

from bspec import schema

FIXTURES = Path(__file__).parent / "fixtures"


def _errors(diags):
    return [d for d in diags if d.severity == "error"]


def test_valid_file_passes():
    raw = json.loads((FIXTURES / "valid/behavior/trading-ma-cross.bspec.json").read_text())
    assert _errors(schema.validate_file(raw, "trading-ma-cross.bspec.json")) == []


def test_unknown_field_rejected():
    raw = {
        "bspecVersion": "v1",
        "module": {"id": "m"},
        "observables": [
            {"id": "x.y", "role": "state", "valueSchema": {"type": "number"}, "extra": True}
        ],
    }
    diags = _errors(schema.validate_file(raw, "f"))
    assert diags and all(d.code == "schema" for d in diags)


def test_missing_required_module_rejected():
    diags = _errors(schema.validate_file({"bspecVersion": "v1"}, "f"))
    assert diags


def test_general_id_allows_underscore():
    # event/module/behavior ids may use underscores (only observable ids forbid '-')
    raw = {
        "bspecVersion": "v1",
        "module": {"id": "m", "name": "M", "rationale": "underscore id fixture"},
        "interfaces": [{"id": "io", "name": "IO", "direction": "input"}],
        "events": [
            {"id": "order_created", "name": "Order created", "direction": "input", "interface": "io",
             "payloadSchema": {"type": "object", "additionalProperties": False}}
        ],
    }
    assert _errors(schema.validate_file(raw, "f")) == []


def test_observable_id_must_be_cel_identifier():
    # hyphen is allowed in general ids but NOT in CEL-addressable observable ids
    raw = {
        "bspecVersion": "v1",
        "module": {"id": "m"},
        "observables": [
            {"id": "ma-cross.signal", "role": "state", "valueSchema": {"type": "number"}}
        ],
    }
    assert _errors(schema.validate_file(raw, "f"))


def test_behavior_then_oneof_rejects_mixed_entry():
    raw = {
        "bspecVersion": "v1",
        "module": {"id": "m"},
        "behaviors": [
            {
                "id": "b",
                "when": {"event": "e"},
                "then": [{"assert": {"cel": "true"}, "forbid": {"event": "e"}}],
            }
        ],
    }
    assert _errors(schema.validate_file(raw, "f"))


def test_embedded_meta_schema_is_itself_valid():
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(schema.load_embedded("bspec.schema.json"))
    Draft202012Validator.check_schema(schema.load_embedded("review_state.schema.json"))


def test_disputed_review_requires_a_comment():
    """A `disputed` record is meaningless without its reason, so the review-state schema
    requires `comment` for it — and only it (other decisions stay comment-optional)."""
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(schema.load_embedded("review_state.schema.json"))

    def state(rec):
        return {"version": "0.1.0", "reviews": {"behavior:x": rec}}

    base = {"semanticHash": "sha256:" + "0" * 64, "reviewedAt": "2026-07-07T00:00:00+08:00"}
    assert not validator.is_valid(state({**base, "decision": "disputed"}))
    assert validator.is_valid(state({**base, "decision": "disputed", "comment": "agent-disputed: why"}))
    assert validator.is_valid(state({**base, "decision": "approved"}))
