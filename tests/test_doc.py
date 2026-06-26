from pathlib import Path

from bspec import doc, loader

FIXTURES = Path(__file__).parent / "fixtures"


def _md():
    proj, _ = loader.load_project(str(FIXTURES / "valid"))
    return doc.render(proj, "trading.ma-cross")


def test_module_heading_and_both_diagrams():
    md = _md()
    assert "# MA-cross strategy" in md
    assert "`trading.ma-cross`" in md
    assert "flowchart LR" in md  # module context graph (mermaid)
    assert "flowchart TD" in md  # flow pipeline (mermaid)
    assert md.count("```mermaid") >= 2


def test_behavior_and_invariant_rules_as_text():
    md = _md()
    assert "## Behaviors" in md
    assert "### Open long" in md
    assert "- **WHEN** `market.bar.closed`" in md
    assert "- **MUST** emit `broker.order.requested`" in md
    assert "## Invariants" in md
    assert "- **ASSERT** `current.portfolio.gross_exposure <= params.risk.max_gross_exposure`" in md


def test_origin_rendered():
    assert "_origin: strategies/ma_cross.py_" in _md()


def test_unknown_module_yields_empty_doc():
    proj, _ = loader.load_project(str(FIXTURES / "valid"))
    assert doc.render(proj, "no.such.module").strip() == ""
