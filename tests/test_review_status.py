import shutil
from pathlib import Path

from bspec import context, hashing, loader, review, status

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


def test_context_full_export(tmp_path):
    proj, _ = _proj(tmp_path)
    exp = context.export(proj, "trading.ma-cross", approved=False)
    assert {b["id"] for b in exp["behaviors"]} == {OPEN_LONG, CLOSE_LONG}
    assert len(exp["invariants"]) == 1
    obs = {o["id"] for o in exp["dependencies"]["observables"]}
    assert {"session.open", "position.quantity", "risk.max_order_notional"} <= obs
    assert {e["id"] for e in exp["dependencies"]["events"]} == {"market.bar.closed", "broker.order.requested"}
    # non-approved export annotates each item with its computed reviewStatus
    assert all(b["reviewStatus"] == "pending" for b in exp["behaviors"])
    assert "glossary" in exp and "lang" in exp


def test_context_approved_gates_per_item(tmp_path):
    proj, root = _proj(tmp_path)
    assert context.export(proj, "trading.ma-cross", approved=True)["behaviors"] == []

    review.record_decision(root, f"behavior:{OPEN_LONG}",
                           "approved", hashing.unit_hash(proj, "behavior", OPEN_LONG))
    exp = context.export(proj, "trading.ma-cross", approved=True)
    assert {b["id"] for b in exp["behaviors"]} == {OPEN_LONG}
    # the flow needs ITSELF + every step approved+fresh; only open-long is → omitted
    assert exp["flows"] == []


def test_context_approved_exports_fully_approved_flow(tmp_path):
    proj, root = _proj(tmp_path)
    flow_id = "trading.trade-cycle"
    for kind, oid in [("behavior", OPEN_LONG), ("behavior", CLOSE_LONG), ("flow", flow_id)]:
        review.record_decision(root, f"{kind}:{oid}", "approved",
                               hashing.unit_hash(proj, kind, oid))
    exp = context.export(proj, "trading.ma-cross", approved=True)
    assert [f["id"] for f in exp["flows"]] == [flow_id]
    assert exp["flows"][0]["steps"] == [OPEN_LONG, CLOSE_LONG]
    assert "_excludedSteps" not in exp["flows"][0]
