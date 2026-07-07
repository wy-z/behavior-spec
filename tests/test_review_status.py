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


def test_disputed_decision_is_stored_and_carries_reason(tmp_path):
    """`disputed` is a stored decision: fresh while the hash holds (reason retained),
    and it drifts to stale like any decision once the spec changes (prior kept)."""
    proj, root = _proj(tmp_path)
    key = f"behavior:{OPEN_LONG}"
    reason = "agent-disputed: entry price is ambiguous"
    review.record_decision(root, key, "disputed",
                           hashing.unit_hash(proj, "behavior", OPEN_LONG), comment=reason)
    info = status.compute(proj)[key]
    assert info["status"] == "disputed"
    assert info["comment"] == reason

    proj.get("behavior", OPEN_LONG).obj["given"]["cel"] = "before.session.open"
    drifted = status.compute(proj)[key]
    assert drifted["status"] == "stale"
    assert drifted["prior"] == "disputed"
    assert drifted["comment"] == reason


def test_disputed_is_in_default_review_scope():
    """A delegated agent's flag must reach the human: `disputed` is in `bspec review`'s
    default status set, so it is surfaced without an explicit --status."""
    assert "disputed" in review._REVIEW_DEFAULT_STATUS


def test_card_renders_the_review_reason(tmp_path):
    """The reason is shown on the card — a current *Dispute* while fresh, a *Prior dispute*
    once the unit drifts to stale (so a stale note never reads as a live one)."""
    import io

    from rich.console import Console

    proj, root = _proj(tmp_path)
    key = f"behavior:{OPEN_LONG}"
    review.record_decision(root, key, "disputed",
                           hashing.unit_hash(proj, "behavior", OPEN_LONG),
                           comment="agent-disputed: entry price is ambiguous")

    def render(info):
        sink = io.StringIO()
        Console(width=100, file=sink).print(review._card(proj, "behavior", OPEN_LONG, info))
        return sink.getvalue()

    fresh = render(status.compute(proj)[key])
    assert "ambiguous" in fresh
    assert "Dispute" in fresh

    proj.get("behavior", OPEN_LONG).obj["given"]["cel"] = "before.session.open"
    stale = render(status.compute(proj)[key])
    assert "ambiguous" in stale
    assert "Prior dispute" in stale


def test_written_review_state_is_schema_valid(tmp_path):
    from jsonschema import Draft202012Validator

    from bspec.schema import load_embedded

    proj, root = _proj(tmp_path)
    review.record_decision(root, f"behavior:{OPEN_LONG}",
                           "disputed",
                           hashing.unit_hash(proj, "behavior", OPEN_LONG),
                           comment="produce at next bar open")
    state = status.load_review_state(root)
    Draft202012Validator(load_embedded("review_state.schema.json")).validate(state)
    rec = state["reviews"][f"behavior:{OPEN_LONG}"]
    assert "reviewer" not in rec
    assert state["lang"] == "en"
