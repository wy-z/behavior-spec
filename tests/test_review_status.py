import shutil
from pathlib import Path

from bspec import hashing, loader, review, status

FIX = Path(__file__).parent / "fixtures" / "valid"
OPEN_LONG = "trading.ma-cross.open-long"
CLOSE_LONG = "trading.ma-cross.close-long"


def _proj(tmp_path):
    dst = tmp_path / "proj"
    shutil.copytree(FIX, dst)
    proj, _ = loader.load_project(str(dst))
    return proj, str(dst)


def test_pending_then_approved_then_stale(tmp_path):
    proj, root = _proj(tmp_path)
    key = f"behavior:{OPEN_LONG}"
    assert status.compute(proj)[key]["status"] == "pending"

    h = hashing.unit_hash(proj, "behavior", OPEN_LONG)
    review.record_decision(root, key, "approved", h)
    assert status.compute(proj)[key]["status"] == "approved"

    proj.get("behavior", OPEN_LONG).obj["given"]["cel"] = "before.session.open"
    info = status.compute(proj)[key]
    assert info["status"] == "stale"
    assert info["prior"] == "approved"


def test_written_review_state_is_schema_valid(tmp_path):
    from jsonschema import Draft202012Validator

    from bspec.schema import load_embedded

    proj, root = _proj(tmp_path)
    review.record_decision(root, f"behavior:{OPEN_LONG}",
                           "changes_requested",
                           hashing.unit_hash(proj, "behavior", OPEN_LONG),
                           comment="produce at next bar open")
    state = status.load_review_state(root)
    Draft202012Validator(load_embedded("review_state.schema.json")).validate(state)
    rec = state["reviews"][f"behavior:{OPEN_LONG}"]
    assert "reviewer" not in rec
    assert state["lang"] == "en"
