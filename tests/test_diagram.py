from pathlib import Path

from bspec import diagram, loader
from bspec.model import Symbol

FIXTURES = Path(__file__).parent / "fixtures"


def _valid():
    proj, _ = loader.load_project(str(FIXTURES / "valid"))
    return proj


def test_flow_mermaid_is_ordered_pipeline():
    proj = _valid()
    m = diagram.flow_mermaid(proj, proj.get("flow", "trading.trade-cycle"))
    assert m.startswith("flowchart TD")
    # node per position, labelled with the behavior name (not the id)
    assert 's1["Open long"]' in m
    assert 's2["Close long"]' in m
    # ordered edge, exactly one direction
    assert "s1 --> s2" in m
    assert "s2 --> s1" not in m


def test_flow_nodes_keyed_by_position_not_id():
    # a repeated step must not collapse into a self-cycle; positions stay distinct
    proj = _valid()
    flow = Symbol("flow", "f", {"steps": ["trading.ma-cross.open-long",
                                          "trading.ma-cross.open-long"]}, "x.bspec.json")
    m = diagram.flow_mermaid(proj, flow)
    assert "s1 --> s2" in m
    assert "s1 --> s1" not in m


def test_empty_flow_renders_nothing():
    proj = _valid()
    assert diagram.flow_mermaid(proj, Symbol("flow", "f", {"steps": []}, "x")) == ""


def test_module_mermaid_context_graph():
    proj = _valid()
    m = diagram.module_mermaid(proj, proj.get("module", "trading.ma-cross"))
    assert m.startswith("flowchart LR")
    assert 'mod["trading.ma-cross"]' in m
    # nodes/edges use readable names; input points INTO the module, output OUT
    assert 'if_trading_market_bars(["Market bar feed"])' in m
    assert 'if_trading_market_bars -->|"Bar closed"| mod' in m
    assert 'mod -->|"Order requested"| if_trading_broker_orders' in m


def test_module_io_groups_events_by_direction():
    proj = _valid()
    edges = diagram.module_io(proj, proj.get("module", "trading.ma-cross"))
    got = {(e.direction, e.interface, e.event) for e in edges}
    assert got == {
        ("input", "trading.market-bars", "market.bar.closed"),
        ("output", "trading.broker-orders", "broker.order.requested"),
    }


def test_module_without_events_is_black_box():
    proj = _valid()
    m = diagram.module_mermaid(proj, Symbol("module", "empty.mod", {"id": "empty.mod"}, "none"))
    assert m == 'flowchart LR\n  mod["empty.mod"]'


def test_label_neutralizes_delimiters_and_caps():
    assert diagram._label('a "b" c | d [e]') == "a 'b' c / d (e)"
    assert diagram._label("x\ny  z") == "x y z"
    long = "x" * 80
    out = diagram._label(long)
    assert len(out) == 60 and out.endswith("…")
