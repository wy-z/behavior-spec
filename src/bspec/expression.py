"""CEL static checking owned by bspec.

celpy parses CEL into a Lark tree; bspec does not trust it as a typed AST and
instead walks it to (1) type-check against the declared observable/event types,
(2) enforce per-clause namespace allow-lists and the function/macro whitelist,
and (3) collect referenced observable ids. The tool never evaluates expressions.
"""

from __future__ import annotations

import celpy
from lark import Token, Tree

from .model import Diagnostic, Project, Symbol

_ENV = celpy.Environment()
NAMESPACES = ("before", "after", "current", "params", "trigger", "emitted")
_NUMERIC = {"int", "uint", "double"}
_WHITELIST_FUNCS = {"size": "int", "int": "int", "double": "double"}
_STRING_METHODS = {"startsWith", "endsWith", "contains", "matches"}
_MACROS = {"all", "exists", "exists_one", "filter", "map"}


# --------------------------------------------------------------------------- #
# type model
# --------------------------------------------------------------------------- #
class Type:
    pass


class Scalar(Type):
    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return self.name


BOOL = Scalar("bool")
INT = Scalar("int")
UINT = Scalar("uint")
DOUBLE = Scalar("double")
STRING = Scalar("string")
BYTES = Scalar("bytes")
NULL = Scalar("null")
DYN = Scalar("dyn")


class ListT(Type):
    def __init__(self, elem: Type):
        self.elem = elem

    def __repr__(self):
        return f"list({self.elem})"


class ObjectT(Type):
    def __init__(self, fields: dict[str, Type], open: bool = False):
        self.fields = fields
        self.open = open  # open => field access yields dyn (used when a payload is unresolved)

    def __repr__(self):
        return "object"


class Group:
    """Intermediate node in a namespace's dotted-id tree."""

    def __init__(self):
        self.children: dict[str, "Group | Leaf"] = {}


class Leaf:
    """A declared observable reachable in a namespace."""

    def __init__(self, observable_id: str, value: Type):
        self.observable_id = observable_id
        self.value = value


def _name(t: Type) -> str:
    return repr(t)


def schema_type(s: dict) -> Type:
    if not isinstance(s, dict):
        return DYN
    t = s.get("type")
    if t == "string":
        return STRING
    if t == "integer":
        return INT
    if t == "number":
        return DOUBLE
    if t == "boolean":
        return BOOL
    if t == "array":
        items = s.get("items")
        return ListT(schema_type(items) if isinstance(items, dict) else DYN)
    if t == "object":
        props = s.get("properties") or {}
        return ObjectT({n: schema_type(v) for n, v in props.items()})
    return DYN


def _build_group(observables: list[Symbol]) -> Group:
    root = Group()
    for sym in observables:
        segs = sym.id.split(".")
        cur = root
        for i, seg in enumerate(segs):
            if i == len(segs) - 1:
                cur.children[seg] = Leaf(sym.id, schema_type(sym.obj.get("valueSchema", {})))
            else:
                nxt = cur.children.get(seg)
                if not isinstance(nxt, Group):
                    nxt = Group()
                    cur.children[seg] = nxt
                cur = nxt
    return root


def _event_object(events, eid) -> ObjectT:
    ev = events.get(eid)
    if ev is None:
        return ObjectT({}, open=True)
    t = schema_type(ev.obj.get("payloadSchema", {}))
    return t if isinstance(t, ObjectT) else ObjectT({}, open=True)


# --------------------------------------------------------------------------- #
# checker
# --------------------------------------------------------------------------- #
class Checker:
    def __init__(self, namespaces, allowed, unit, file, path):
        self.ns = namespaces
        self.allowed = allowed
        self.unit, self.file, self.path = unit, file, path
        self.errors: list[Diagnostic] = []
        self.refs: set[str] = set()
        self.scope: dict[str, Type] = {}

    def err(self, msg: str) -> None:
        self.errors.append(
            Diagnostic("error", "cel", msg, unit=self.unit, file=self.file, path=self.path)
        )

    # -- entry -- #
    def check(self, ast) -> None:
        t = self.walk(ast)
        if not _is_bool(t):
            self.err(f"expression must be boolean, got {_name(t)}")

    # -- dispatch -- #
    def walk(self, node) -> Type:
        if isinstance(node, Token):
            return DYN
        handler = getattr(self, "n_" + node.data, None)
        if handler:
            return handler(node)
        kids = [k for k in node.children if isinstance(k, Tree)]
        if len(kids) == 1:
            return self.walk(kids[0])
        for k in kids:
            self.walk(k)
        return DYN

    # -- boolean connectives -- #
    def n_expr(self, node):  # ternary
        kids = [k for k in node.children if isinstance(k, Tree)]
        if len(kids) == 1:
            return self.walk(kids[0])
        cond, a, b = (self.walk(k) for k in kids)
        if not _is_bool(cond):
            self.err("ternary condition must be boolean")
        if a is DYN or b is DYN:
            return DYN  # order-independent: one unknown arm => unknown result
        if not _same(a, b):
            self.err(f"ternary branches differ in type: {_name(a)} vs {_name(b)}")
            return DYN
        return a

    def _bool_chain(self, node):
        kids = [k for k in node.children if isinstance(k, Tree)]
        if len(kids) == 1:
            return self.walk(kids[0])
        for k in kids:
            t = self.walk(k)
            if not _is_bool(t):
                self.err(f"'&&'/'||' operands must be boolean, got {_name(t)}")
        return BOOL

    n_conditionalor = _bool_chain
    n_conditionaland = _bool_chain

    # -- comparisons -- #
    def n_relation(self, node):
        ch = node.children
        if len(ch) == 1:
            return self.walk(ch[0])
        op_node, right_node = ch[0], ch[1]
        left = self.walk(op_node.children[0])
        right = self.walk(right_node)
        op = op_node.data
        if op == "relation_in":
            if not (isinstance(right, (ListT,)) or right is DYN or isinstance(right, ObjectT)):
                self.err(f"'in' requires a list or map, got {_name(right)}")
        else:
            self._check_compare(op, left, right, op_node.children[0], right_node)
        return BOOL

    def _check_compare(self, op, left, right, lnode, rnode):
        if left is DYN or right is DYN:
            return
        lb = left.name if isinstance(left, Scalar) else None
        rb = right.name if isinstance(right, Scalar) else None
        if op in ("relation_eq", "relation_ne"):
            if lb and rb and lb != rb and not self._numeric_ok(lb, rb, lnode, rnode):
                self.err(f"cannot compare {_name(left)} and {_name(right)}")
            return
        # ordering
        if lb in _NUMERIC and rb in _NUMERIC:
            if not self._numeric_ok(lb, rb, lnode, rnode):
                self.err(f"cannot order {_name(left)} and {_name(right)} (int/double mismatch)")
        elif lb == "string" and rb == "string":
            return
        else:
            self.err(f"cannot order {_name(left)} and {_name(right)}")

    def _numeric_ok(self, lb, rb, lnode, rnode):
        if lb not in _NUMERIC or rb not in _NUMERIC:
            return False
        if lb == rb:
            return True
        if "double" in (lb, rb):
            # widen only an integer LITERAL to double
            int_node = lnode if lb in ("int", "uint") else rnode
            return _is_int_literal(int_node)
        return True  # int vs uint

    # -- arithmetic -- #
    def n_addition(self, node):
        return self._arith(node)

    def n_multiplication(self, node):
        return self._arith(node)

    def _arith(self, node):
        ch = node.children
        if len(ch) == 1:
            return self.walk(ch[0])
        op_node, right_node = ch[0], ch[1]
        left = self.walk(op_node.children[0])
        right = self.walk(right_node)
        if left is DYN or right is DYN:
            return DYN
        lb = left.name if isinstance(left, Scalar) else None
        rb = right.name if isinstance(right, Scalar) else None
        if lb in _NUMERIC and rb in _NUMERIC:
            return DOUBLE if "double" in (lb, rb) else INT
        if op_node.data == "addition_add" and lb == "string" and rb == "string":
            return STRING
        if (op_node.data == "addition_add" and isinstance(left, ListT)
                and isinstance(right, ListT) and _same(left.elem, right.elem)):
            return left
        self.err(f"invalid operands for arithmetic: {_name(left)}, {_name(right)}")
        return DYN

    # -- unary -- #
    def n_unary(self, node):
        ch = node.children
        if len(ch) == 1:
            return self.walk(ch[0])
        op, operand = ch[0].data, self.walk(ch[1])
        if op == "unary_not":
            if not _is_bool(operand):
                self.err("'!' requires a boolean")
            return BOOL
        if op == "unary_neg":
            if not (operand is DYN or (isinstance(operand, Scalar) and operand.name in _NUMERIC)):
                self.err("unary '-' requires a number")
            return operand if operand is not DYN else DYN
        return DYN

    # -- members / paths -- #
    def n_ident(self, node):
        return self._resolve(_path(node), node)

    def n_member_dot(self, node):
        p = _path(node)
        if p is not None:
            return self._resolve(p, node)
        base = self.walk(node.children[0])
        return self._field(base, str(node.children[-1]))

    def n_member_index(self, node):
        base = self.walk(node.children[0])
        self.walk(node.children[-1])
        if isinstance(base, ListT):
            return base.elem
        if isinstance(base, ObjectT):
            return DYN
        return DYN

    def n_paren_expr(self, node):
        return self.walk(node.children[0])

    def n_list_lit(self, node):
        elems = []
        for kid in node.children:
            if isinstance(kid, Tree) and kid.data == "exprlist":
                elems = [self.walk(e) for e in kid.children if isinstance(e, Tree)]
        if elems and all(_same(elems[0], e) for e in elems):
            return ListT(elems[0])
        return ListT(DYN)

    def n_literal(self, node):
        tok = node.children[0]
        return {
            "INT_LIT": INT, "UINT_LIT": UINT, "FLOAT_LIT": DOUBLE,
            "STRING_LIT": STRING, "MLSTRING_LIT": STRING, "BYTES_LIT": BYTES,
            "BOOL_LIT": BOOL, "NULL_LIT": NULL,
        }.get(getattr(tok, "type", ""), DYN)

    # -- calls -- #
    def n_ident_arg(self, node):  # function call:  name(args)
        name = str(node.children[0])
        args = _exprlist(node)
        if name == "has":
            for a in args:
                self.walk(a)
            path = _path(args[0]) if len(args) == 1 else None
            if path is None or len(path) < 2:
                self.err("has() requires exactly one field-selection argument, e.g. has(trigger.note)")
            return BOOL
        if name in _WHITELIST_FUNCS:
            for a in args:
                self.walk(a)
            return Scalar(_WHITELIST_FUNCS[name])
        self.err(f"function '{name}' is not in the v0.1 whitelist")
        for a in args:
            self.walk(a)
        return DYN

    def n_member_dot_arg(self, node):  # method/macro:  recv.name(args)
        receiver = node.children[0]
        method = str(node.children[1])
        args = _exprlist(node)
        if method in _MACROS:
            return self._macro(method, receiver, args)
        recv = self.walk(receiver)
        if method in _STRING_METHODS:
            if not _is_string(recv):
                self.err(f"'{method}' requires a string receiver, got {_name(recv)}")
            for a in args:
                at = self.walk(a)
                if not _is_string(at):
                    self.err(f"'{method}' argument must be a string, got {_name(at)}")
            return BOOL
        self.err(f"method '{method}' is not in the v0.1 whitelist")
        for a in args:
            self.walk(a)
        return DYN

    def _macro(self, method, receiver, args):
        recv = self.walk(receiver)
        elem = recv.elem if isinstance(recv, ListT) else DYN
        if not isinstance(recv, ListT) and recv is not DYN:
            self.err(f"'{method}' requires a list, got {_name(recv)}")
        if len(args) != 2:
            self.err(f"'{method}' expects (var, predicate)")
            return DYN
        var = _path(args[0])
        varname = var[0] if var and len(var) == 1 else None
        if varname is None:
            self.err("macro variable must be a simple identifier")
        saved = self.scope.get(varname) if varname else None
        if varname:
            self.scope[varname] = elem
        pred = self.walk(args[1])
        if varname:
            if saved is None:
                self.scope.pop(varname, None)
            else:
                self.scope[varname] = saved
        if method in ("all", "exists", "exists_one", "filter") and not _is_bool(pred):
            self.err(f"'{method}' predicate must be boolean")
        if method in ("all", "exists", "exists_one"):
            return BOOL
        if method == "filter":
            return ListT(elem)
        return ListT(pred)  # map

    # -- name resolution -- #
    def _resolve(self, segs, node) -> Type:
        if segs is None:
            return DYN
        root = segs[0]
        if root in self.scope:
            return self._fields(self.scope[root], segs[1:])
        if root in NAMESPACES:
            if root not in self.allowed:
                self.err(f"namespace '{root}' is not allowed in this clause")
                return DYN
            nsroot = self.ns.get(root)
            if nsroot is None:
                return DYN
            if isinstance(nsroot, ObjectT):
                return self._fields(nsroot, segs[1:])
            return self._group(nsroot, root, segs[1:])
        self.err(f"unknown identifier '{root}'")
        return DYN

    def _group(self, group, nsname, rest) -> Type:
        cur = group
        for i, seg in enumerate(rest):
            if not isinstance(cur, Group):
                break
            nxt = cur.children.get(seg)
            if nxt is None:
                path = ".".join(rest[: i + 1])
                self.err(f"undeclared observable '{nsname}.{path}'")
                return DYN
            cur = nxt
            if isinstance(cur, Leaf):
                self.refs.add(cur.observable_id)
                return self._fields(cur.value, rest[i + 1:])
        self.err(f"'{nsname}.{'.'.join(rest)}' is a group, not a complete observable")
        return DYN

    def _fields(self, t, segs) -> Type:
        for seg in segs:
            t = self._field(t, seg)
        return t

    def _field(self, t, name) -> Type:
        if t is DYN:
            return DYN
        if isinstance(t, ObjectT):
            if t.open:
                return DYN
            if name in t.fields:
                return t.fields[name]
            self.err(f"no field '{name}' on object")
            return DYN
        self.err(f"cannot access field '{name}' on {_name(t)}")
        return DYN


# --------------------------------------------------------------------------- #
# tree helpers
# --------------------------------------------------------------------------- #
# Single-child grammar nodes that are pure pass-throughs (precedence chain +
# member/primary/paren). A call/index node is NOT here, so `_path` never flattens
# through `a.b().c` or `a[i].b` (which would drop the call/index).
_PASS_THROUGH = {
    "expr", "conditionalor", "conditionaland", "relation", "addition",
    "multiplication", "unary", "member", "primary", "paren_expr",
}


def _path(node):
    """Flatten a pure ident / member_dot chain into [root, seg, ...] or None.

    Unwraps only pass-through precedence nodes, so a bare identifier or dotted
    path resolves regardless of grammar nesting (e.g. a macro argument arrives as
    a full `expr`), while chains containing a call or index resolve to None.
    """
    if isinstance(node, Token):
        return None
    if node.data == "ident":
        return [str(node.children[0])]
    if node.data == "member_dot":
        base = _path(node.children[0])
        return base + [str(node.children[-1])] if base is not None else None
    if node.data in _PASS_THROUGH:
        kids = [k for k in node.children if isinstance(k, Tree)]
        if len(kids) == 1:
            return _path(kids[0])
    return None


def _exprlist(node):
    for kid in node.children:
        if isinstance(kid, Tree) and kid.data == "exprlist":
            return [e for e in kid.children if isinstance(e, Tree)]
    return []


def _lit_token(node):
    cur = node
    while isinstance(cur, Tree):
        if cur.data == "literal":
            return cur.children[0]
        kids = [k for k in cur.children if isinstance(k, Tree)]
        if len(kids) == 1:
            cur = kids[0]
        else:
            return None
    return None


def _is_int_literal(node) -> bool:
    tok = _lit_token(node)
    return tok is not None and getattr(tok, "type", "") in ("INT_LIT", "UINT_LIT")


def _is_bool(t) -> bool:
    return t is DYN or (isinstance(t, Scalar) and t.name in ("bool", "dyn"))


def _is_string(t) -> bool:
    return t is DYN or (isinstance(t, Scalar) and t.name in ("string", "dyn"))


def _same(a, b) -> bool:
    if a is DYN or b is DYN:
        return True
    if isinstance(a, Scalar) and isinstance(b, Scalar):
        return a.name == b.name
    if isinstance(a, ListT) and isinstance(b, ListT):
        return _same(a.elem, b.elem)
    return type(a) is type(b)


# --------------------------------------------------------------------------- #
# project entry
# --------------------------------------------------------------------------- #
def _check_clause(text, namespaces, allowed, unit, file, path):
    try:
        ast = _ENV.compile(text)
    except Exception as e:  # celpy raises a variety of parse errors
        first = str(e).strip().splitlines()[0] if str(e).strip() else e.__class__.__name__
        return [Diagnostic("error", "cel-parse", f"CEL parse error: {first}",
                           unit=unit, file=file, path=path)], set()
    c = Checker(namespaces, allowed, unit, file, path)
    c.check(ast)
    return c.errors, c.refs


def check_project(proj: Project) -> list[Diagnostic]:
    obs = list(proj.kind("observable").values())
    value_tree = _build_group([s for s in obs if s.obj.get("role") == "state"])
    params_tree = _build_group([s for s in obs if s.obj.get("role") == "parameter"])
    events = proj.kind("event")

    diags: list[Diagnostic] = []
    refs: set[str] = set()

    for sym in proj.kind("behavior").values():
        d, r = _check_behavior(sym, value_tree, params_tree, events)
        diags += d
        refs |= r
    for sym in proj.kind("invariant").values():
        d, r = _check_invariant(sym, value_tree, params_tree)
        diags += d
        refs |= r

    for sym in obs:
        if sym.id not in refs:
            diags.append(Diagnostic("warning", "unused",
                                    f"observable '{sym.id}' is never referenced",
                                    unit=f"observable:{sym.id}", file=sym.file))
    return diags


def _check_behavior(sym, value_tree, params_tree, events):
    b, unit, file = sym.obj, f"behavior:{sym.id}", sym.file
    diags: list[Diagnostic] = []
    refs: set[str] = set()
    trigger = _event_object(events, b.get("when", {}).get("event"))
    base = {"before": value_tree, "after": value_tree, "current": value_tree,
            "params": params_tree, "trigger": trigger}

    def run(text, allowed, path):
        e, r = _check_clause(text, base, allowed, unit, file, path)
        diags.extend(e)
        refs.update(r)

    if "given" in b:
        run(b["given"]["cel"], {"before", "params"}, "given")
    where = b.get("when", {}).get("where")
    if where:
        run(where["cel"], {"before", "params", "trigger"}, "when.where")
    for i, entry in enumerate(b.get("then", [])):
        if "assert" in entry:
            run(entry["assert"]["cel"], {"before", "after", "params", "trigger"}, f"then[{i}].assert")
        elif "emit" in entry and "where" in entry["emit"]:
            base_emitted = dict(base)
            base_emitted["emitted"] = _event_object(events, entry["emit"].get("event"))
            e, r = _check_clause(entry["emit"]["where"]["cel"], base_emitted,
                                 {"before", "after", "params", "trigger", "emitted"},
                                 unit, file, f"then[{i}].emit.where")
            diags.extend(e)
            refs.update(r)
    return diags, refs


def _check_invariant(sym, value_tree, params_tree):
    inv, unit, file = sym.obj, f"invariant:{sym.id}", sym.file
    diags: list[Diagnostic] = []
    refs: set[str] = set()
    ns = {"current": value_tree, "params": params_tree}
    for key, path in (("while", "while"), ("assert", "assert")):
        if key in inv:
            e, r = _check_clause(inv[key]["cel"], ns, {"current", "params"}, unit, file, path)
            diags.extend(e)
            refs.update(r)
    return diags, refs


# --------------------------------------------------------------------------- #
# observable reference extraction (for the semantic hash)
# --------------------------------------------------------------------------- #
def _trees(proj: Project):
    obs = list(proj.kind("observable").values())
    return (
        _build_group([s for s in obs if s.obj.get("role") == "state"]),
        _build_group([s for s in obs if s.obj.get("role") == "parameter"]),
        proj.kind("event"),
    )


def referenced_observables(proj: Project, sym: Symbol, kind: str) -> set[str]:
    value_tree, params_tree, events = _trees(proj)
    if kind == "behavior":
        return _check_behavior(sym, value_tree, params_tree, events)[1]
    if kind == "invariant":
        return _check_invariant(sym, value_tree, params_tree)[1]
    return set()


# --------------------------------------------------------------------------- #
# CEL canonicalization for the semantic hash
#
# The celpy Lark tree is parser IR, not a stable AST contract, so we re-emit a
# normalized S-expression that ignores whitespace / comments / parentheses but
# changes under any operator or operand edit. Golden-tested against the pinned
# celpy version (see test_hashing).
# --------------------------------------------------------------------------- #
_OP = {
    "relation_lt": "<", "relation_le": "<=", "relation_gt": ">", "relation_ge": ">=",
    "relation_eq": "==", "relation_ne": "!=", "relation_in": "in",
    "addition_add": "+", "addition_sub": "-",
    "multiplication_mul": "*", "multiplication_div": "/", "multiplication_mod": "%",
}


def canonical(text: str) -> str:
    """Canonical S-expression for a (already valid) CEL string."""
    return _sexpr(_ENV.compile(text))


def _sexpr(node) -> str:
    if isinstance(node, Token):
        return str(node)
    d = node.data
    if d in ("ident", "member_dot"):
        p = _path(node)
        if p is not None:
            return ".".join(p)
    if d == "literal":
        tok = node.children[0]
        ty, v = getattr(tok, "type", ""), str(tok)
        prefix = {"INT_LIT": "i:", "UINT_LIT": "u:", "FLOAT_LIT": "d:",
                  "BOOL_LIT": "b:", "BYTES_LIT": "y:"}.get(ty)
        if prefix:
            return prefix + v
        if ty in ("STRING_LIT", "MLSTRING_LIT"):
            # Keep the raw literal (quotes/prefix/escapes verbatim) so two
            # different string VALUES can never collide to the same hash. This is
            # cosmetically over-sensitive (a quote-style change triggers a safe
            # re-review) but never under-sensitive (which would leak approvals).
            return "s:" + v
        if ty == "NULL_LIT":
            return "null"
        return v
    if d == "member_dot":
        return f"(. {_sexpr(node.children[0])} {node.children[-1]})"
    if d == "member_index":
        return f"(index {_sexpr(node.children[0])} {_sexpr(node.children[-1])})"
    if d == "member_dot_arg":
        args = " ".join(_sexpr(a) for a in _exprlist(node))
        return f"(call {node.children[1]} {_sexpr(node.children[0])}{' ' + args if args else ''})"
    if d == "ident_arg":
        args = " ".join(_sexpr(a) for a in _exprlist(node))
        return f"(fn {node.children[0]}{' ' + args if args else ''})"
    if d == "list_lit":
        args = " ".join(_sexpr(a) for a in _exprlist(node))
        return f"(list{' ' + args if args else ''})"
    if d == "unary" and len([k for k in node.children if isinstance(k, Tree)]) > 1:
        op = "!" if node.children[0].data == "unary_not" else "neg"
        return f"({op} {_sexpr(node.children[1])})"
    if d in ("relation", "addition", "multiplication"):
        ch = node.children
        if len(ch) > 1:
            return f"({_OP[ch[0].data]} {_sexpr(ch[0].children[0])} {_sexpr(ch[1])})"
    if d in ("conditionalor", "conditionaland"):
        kids = [k for k in node.children if isinstance(k, Tree)]
        if len(kids) > 1:
            op = "||" if d == "conditionalor" else "&&"
            return f"({op} {' '.join(_sexpr(k) for k in kids)})"
    if d == "expr":
        kids = [k for k in node.children if isinstance(k, Tree)]
        if len(kids) > 1:
            return f"(?: {' '.join(_sexpr(k) for k in kids)})"
    kids = [k for k in node.children if isinstance(k, Tree)]
    if len(kids) == 1:
        return _sexpr(kids[0])
    return f"({d} {' '.join(_sexpr(k) for k in kids)})"
