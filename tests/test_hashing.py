import re
from pathlib import Path

from bspec import expression, hashing, loader

FIXTURES = Path(__file__).parent / "fixtures"


def _proj():
    proj, _ = loader.load_project(str(FIXTURES / "valid"))
    return proj


def test_canonical_ignores_formatting_and_parens():
    a = expression.canonical("before.orders.count == 0 && before.session.open")
    b = expression.canonical("(before.orders.count==0)   &&  before.session.open")
    assert a == b


def test_canonical_changes_on_operand():
    assert expression.canonical("e.side == 'BUY'") != expression.canonical("e.side == 'SELL'")


def test_canonical_changes_on_operator():
    assert expression.canonical("a.b > c.d") != expression.canonical("a.b >= c.d")


def test_hash_format():
    h = hashing.unit_hash(_proj(), "behavior", "trading.ma-cross.open-long")
    assert re.fullmatch(r"sha256:[0-9a-f]{64}", h)


def test_hash_stable_under_name_change():
    # name is a cosmetic display label, not part of the approved contract
    proj = _proj()
    sym = proj.get("behavior", "trading.ma-cross.open-long")
    before = hashing.unit_hash(proj, "behavior", sym.id)
    sym.obj["name"] = "totally different name"
    sym.obj["origin"] = [{"kind": "code", "uri": "x.py"}]
    assert hashing.unit_hash(proj, "behavior", sym.id) == before


def test_hash_changes_on_title_edit():
    # title is the EARS requirement the layperson approves, so it IS hashed
    proj = _proj()
    sym = proj.get("behavior", "trading.ma-cross.open-long")
    before = hashing.unit_hash(proj, "behavior", sym.id)
    sym.obj["title"] = "a materially different requirement statement"
    assert hashing.unit_hash(proj, "behavior", sym.id) != before


def test_hash_changes_on_rationale_edit():
    # rationale is the human-approved why, so it IS review-significant
    proj = _proj()
    sym = proj.get("behavior", "trading.ma-cross.open-long")
    before = hashing.unit_hash(proj, "behavior", sym.id)
    sym.obj["rationale"] = "a materially different plain-language explanation"
    assert hashing.unit_hash(proj, "behavior", sym.id) != before


def test_hash_changes_on_referenced_description_edit():
    # an observable's description shapes how a reviewer understands the rule
    proj = _proj()
    sym = proj.get("behavior", "trading.ma-cross.open-long")
    before = hashing.unit_hash(proj, "behavior", sym.id)
    proj.get("observable", "position.quantity").obj["description"] = "now means something else"
    assert hashing.unit_hash(proj, "behavior", sym.id) != before


def test_hash_changes_on_cel_edit():
    proj = _proj()
    sym = proj.get("behavior", "trading.ma-cross.open-long")
    before = hashing.unit_hash(proj, "behavior", sym.id)
    sym.obj["given"]["cel"] = "before.session.open && before.position.quantity == 1"
    assert hashing.unit_hash(proj, "behavior", sym.id) != before


def test_hash_changes_when_referenced_schema_changes():
    proj = _proj()
    sym = proj.get("behavior", "trading.ma-cross.open-long")
    before = hashing.unit_hash(proj, "behavior", sym.id)
    # position.quantity is referenced by this behavior's `given`
    proj.get("observable", "position.quantity").obj["valueSchema"] = {"type": "number"}
    assert hashing.unit_hash(proj, "behavior", sym.id) != before


def test_module_hash_is_membership_only():
    proj = _proj()
    before = hashing.unit_hash(proj, "module", "trading.ma-cross")
    # changing a member behavior's CEL must NOT change the module hash (non-cascade)
    proj.get("behavior", "trading.ma-cross.open-long").obj["given"]["cel"] = "before.session.open"
    assert hashing.unit_hash(proj, "module", "trading.ma-cross") == before
    # adding a member DOES change the module hash (scope change)
    proj.membership[("behavior", "trading.ma-cross.new")] = "trading.ma-cross"
    assert hashing.unit_hash(proj, "module", "trading.ma-cross") != before


def test_actor_absent_not_in_payload():
    # actor was added after these behaviors were authored; an absent actor must NOT
    # enter the hash payload, so existing approvals stay valid (no mass re-review)
    proj = _proj()
    sym = proj.get("behavior", "trading.ma-cross.open-long")
    assert "actor" not in sym.obj
    assert "actor" not in hashing.unit_payload(proj, "behavior", sym.id)


def test_actor_added_changes_hash():
    # actor scopes who the requirement is about → normative when present
    proj = _proj()
    sym = proj.get("behavior", "trading.ma-cross.open-long")
    before = hashing.unit_hash(proj, "behavior", sym.id)
    sym.obj["actor"] = "strategy-scheduler"
    assert hashing.unit_hash(proj, "behavior", sym.id) != before
