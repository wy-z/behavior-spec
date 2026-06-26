"""Embedded meta-schema loading and structural validation of a spec file."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources

from jsonschema import Draft202012Validator

from .model import Diagnostic


def load_embedded(name: str) -> dict:
    """Load an embedded JSON resource from bspec/schemas/."""
    text = resources.files("bspec").joinpath("schemas", name).read_text("utf-8")
    return json.loads(text)


@lru_cache(maxsize=1)
def _meta_validator() -> Draft202012Validator:
    schema = load_embedded("bspec.schema.json")
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_file(raw: dict, file: str) -> list[Diagnostic]:
    """Validate one parsed spec file against the meta-schema."""
    diags: list[Diagnostic] = []
    errors = sorted(_meta_validator().iter_errors(raw), key=lambda e: list(e.absolute_path))
    for err in errors:
        loc = "/".join(str(p) for p in err.absolute_path)
        diags.append(
            Diagnostic("error", "schema", err.message, file=file, path=loc or None)
        )
    return diags
