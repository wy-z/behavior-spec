import json
import shutil
from pathlib import Path

from bspec import hashing, loader, review, status
from bspec.model import REVIEW_STATE_FILENAME

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


def test_legacy_unsupported_decision_downgrades_to_stale(tmp_path):
    """A review-state file from an older version may hold a decision type since
    removed (e.g. `deferred`). compute() must downgrade it to stale — keeping the
    prior for display — and summary() must not KeyError on the unknown status."""
    proj, root = _proj(tmp_path)
    key = f"behavior:{OPEN_LONG}"
    h = hashing.unit_hash(proj, "behavior", OPEN_LONG)
    state = status.load_review_state(root)
    state["reviews"] = {key: {"semanticHash": h, "decision": "deferred",
                              "reviewedAt": "2026-01-01T00:00:00+08:00"}}
    with open(Path(root) / REVIEW_STATE_FILENAME, "w", encoding="utf-8") as f:
        json.dump(state, f)

    info = status.compute(proj)[key]
    assert info["status"] == "stale"
    assert info["prior"] == "deferred"
    status.summary(proj)  # must not raise


def test_view_is_read_only(tmp_path):
    """`view` browses cards but is read-only — it must never create the review-state file."""
    proj, root = _proj(tmp_path)
    review.run_view(proj)  # non-tty under pytest -> prints cards, no carousel
    assert not (Path(root) / REVIEW_STATE_FILENAME).exists()


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
