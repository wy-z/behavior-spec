from bspec import expression as ex
from bspec.model import Symbol


def _obs(oid, vs, role="state"):
    return Symbol("observable", oid, {"id": oid, "role": role, "valueSchema": vs}, "f")


VALUE = ex._build_group([
    _obs("orders.count", {"type": "integer"}),
    _obs("price", {"type": "number"}),
    _obs("session.open", {"type": "boolean"}),
    _obs("items", {"type": "array", "items": {
        "type": "object", "additionalProperties": False,
        "properties": {"v": {"type": "string"}}}}),
])
PARAMS = ex._build_group([_obs("limit", {"type": "number"}, role="parameter")])
TRIGGER = ex.ObjectT({"sym": ex.STRING, "qty": ex.INT})

NS = {"before": VALUE, "after": VALUE, "current": VALUE, "params": PARAMS, "trigger": TRIGGER}


def chk(text, allowed=("before", "params", "trigger")):
    errors, refs = ex._check_clause(text, NS, set(allowed), "u", "f", "p")
    return [e.code for e in errors], refs


def test_valid_paths_and_refs():
    codes, refs = chk("before.orders.count == 0 && before.session.open")
    assert codes == []
    assert refs == {"orders.count", "session.open"}


def test_undeclared_observable():
    codes, _ = chk("before.ghost == 1")
    assert "cel" in codes


def test_incomplete_group_reference():
    codes, _ = chk("before.orders == 0")  # 'orders' is a group, not a leaf
    assert "cel" in codes


def test_non_boolean_result_rejected():
    codes, _ = chk("before.orders.count")
    assert "cel" in codes


def test_namespace_not_allowed():
    codes, _ = chk("after.price > 0", allowed=("before",))
    assert "cel" in codes


def test_nonexistent_payload_field():
    codes, _ = chk("trigger.missing == 'x'")
    assert "cel" in codes


def test_int_literal_widens_to_double():
    codes, _ = chk("before.price <= 10")  # double <= int-literal -> ok
    assert codes == []


def test_variable_int_double_mismatch_errors():
    codes, _ = chk("before.price == before.orders.count")  # double vs int (both vars)
    assert "cel" in codes


def test_string_vs_int_comparison_errors():
    codes, _ = chk("trigger.sym == before.orders.count")
    assert "cel" in codes


def test_macro_over_list():
    codes, refs = chk("before.items.all(x, x.v == 'open')")
    assert codes == []
    assert "items" in refs


def test_unknown_function_rejected():
    codes, _ = chk("frobnicate(before.price) == 0")
    assert "cel" in codes


def test_parse_error():
    codes, _ = chk("before.price <=")
    assert "cel-parse" in codes


def test_whitelisted_size_function():
    codes, _ = chk("size(before.items) > 0")
    assert codes == []


def test_string_function_rejected():  # not in v0.1 whitelist
    codes, _ = chk("string(before.orders.count) == 'x'")
    assert "cel" in codes


def test_string_method_requires_string_receiver():
    codes, _ = chk("before.orders.count.startsWith('x')")  # receiver is int
    assert "cel" in codes


def test_filter_requires_boolean_predicate():
    codes, _ = chk("size(before.items.filter(x, x.v)) > 0")  # x.v is string, not bool
    assert "cel" in codes


def test_ternary_branch_type_mismatch():
    codes, _ = chk("true ? 1 : 'x'")
    assert "cel" in codes


def test_ternary_with_dyn_arm_is_order_independent():
    ns = {"before": VALUE, "trigger": ex.ObjectT({}, open=True)}

    def c(text):
        errs, _ = ex._check_clause(text, ns, {"before", "trigger"}, "u", "f", "p")
        return [e.code for e in errs]

    # one arm is dyn (open payload) -> result dyn regardless of arm order; no spurious error
    assert c("true ? trigger.x : 1") == []
    assert c("true ? 1 : trigger.x") == []


def test_path_rejects_call_and_index_chains():
    env = ex._ENV
    assert ex._path(env.compile("before.a.b")) == ["before", "a", "b"]
    assert ex._path(env.compile("before.items.all(x, x == 1)")) is None
    assert ex._path(env.compile("before.a[0]")) is None
