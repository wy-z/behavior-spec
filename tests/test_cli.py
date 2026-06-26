import json

from jsonschema import Draft202012Validator

from bspec.cli import build_parser
from bspec.schema import load_embedded


def _init(tmp_path, *args):
    ns = build_parser().parse_args(["init", str(tmp_path), *args])
    ns.func(ns)
    return json.loads((tmp_path / "bspec.json").read_text())


def test_init_default_lang_en_no_glossary(tmp_path):
    state = _init(tmp_path)
    assert state["lang"] == "en"
    assert "glossary" not in state
    Draft202012Validator(load_embedded("review_state.schema.json")).validate(state)


def test_init_lang_scaffolds_type_glossary(tmp_path):
    state = _init(tmp_path, "--lang", "zh")
    assert state["lang"] == "zh"
    # scaffolds the type words to translate (placeholder = the English token)
    assert {"module", "behavior", "interface", "event", "observable",
            "input", "output", "state", "parameter"} <= set(state["glossary"])
    assert state["glossary"]["interface"] == "interface"
    Draft202012Validator(load_embedded("review_state.schema.json")).validate(state)
