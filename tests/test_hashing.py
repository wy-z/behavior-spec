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


def test_hash_stable_under_title_change():
    proj = _proj()
    sym = proj.get("behavior", "trading.ma-cross.open-long")
    before = hashing.unit_hash(proj, "behavior", sym.id)
    sym.obj["title"] = "totally different title"
    sym.obj["origin"] = [{"kind": "code", "uri": "x.py", "lineStart": 999, "lineEnd": 1000}]
    assert hashing.unit_hash(proj, "behavior", sym.id) == before


def test_hash_changes_on_summary_edit():
    # summary is the human-approved explanation, so it IS review-significant
    proj = _proj()
    sym = proj.get("behavior", "trading.ma-cross.open-long")
    before = hashing.unit_hash(proj, "behavior", sym.id)
    sym.obj["summary"] = "a materially different plain-language explanation"
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
