"""Utilities related to determining the reachability of code (in semantic analysis)."""

from __future__ import annotations

from typing import Tuple, TypeVar
from typing import Final

from mypy.literals import literal
from mypy.nodes import (
    LITERAL_YES,
    AssertStmt,
    Block,
    CallExpr,
    ComparisonExpr,
    Expression,
    FuncDef,
    IfStmt,
    Import,
    ImportAll,
    ImportFrom,
    IndexExpr,
    IntExpr,
    MatchStmt,
    MemberExpr,
    NameExpr,
    OpExpr,
    SliceExpr,
    StrExpr,
    TupleExpr,
    UnaryExpr,
)
from mypy.options import Options
from mypy.patterns import AsPattern, OrPattern, Pattern
from mypy.traverser import TraverserVisitor

# Inferred truth value of an expression.
ALWAYS_TRUE: Final = 1
MYPY_TRUE: Final = 2  # True in mypy, False at runtime
ALWAYS_FALSE: Final = 3
MYPY_FALSE: Final = 4  # False in mypy, True at runtime
TRUTH_VALUE_UNKNOWN: Final = 5

inverted_truth_mapping: Final = {
    ALWAYS_TRUE: ALWAYS_FALSE,
    ALWAYS_FALSE: ALWAYS_TRUE,
    TRUTH_VALUE_UNKNOWN: TRUTH_VALUE_UNKNOWN,
    MYPY_TRUE: MYPY_FALSE,
    MYPY_FALSE: MYPY_TRUE,
}

reverse_op: Final = {"==": "==", "!=": "!=", "<": ">", ">": "<", "<=": ">=", ">=": "<="}


def infer_reachability_of_if_statement(s: IfStmt, options: Options) -> None:
    for i in range(len(s.expr)):
        result = infer_condition_value(s.expr[i], options)
        if result in (ALWAYS_FALSE, MYPY_FALSE):
            # The condition is considered always false, so we skip the if/elif body.
            mark_block_unreachable(s.body[i])
        elif result in (ALWAYS_TRUE, MYPY_TRUE):
            # This condition is considered always true, so all of the remaining
            # elif/else bodies should not be checked.
            if result == MYPY_TRUE:
                # This condition is false at runtime; this will affect
                # import priorities.
                mark_block_mypy_only(s.body[i])
            for body in s.body[i + 1 :]:
                mark_block_unreachable(body)

            # Make sure else body always exists and is marked as
            # unreachable so the type checker always knows that
            # all control flow paths will flow through the if
            # statement body.
            if not s.else_body:
                s.else_body = Block([])
            mark_block_unreachable(s.else_body)
            break


def infer_reachability_of_match_statement(s: MatchStmt, options: Options) -> None:
    for i, guard in enumerate(s.guards):
        pattern_value = infer_pattern_value(s.patterns[i])

        if guard is not None:
            guard_value = infer_condition_value(guard, options)
        else:
            guard_value = ALWAYS_TRUE

        if pattern_value in (ALWAYS_FALSE, MYPY_FALSE) or guard_value in (
            ALWAYS_FALSE,
            MYPY_FALSE,
        ):
            # The case is considered always false, so we skip the case body.
            mark_block_unreachable(s.bodies[i])
        elif pattern_value in (ALWAYS_FALSE, MYPY_TRUE) and guard_value in (
            ALWAYS_TRUE,
            MYPY_TRUE,
        ):
            for body in s.bodies[i + 1 :]:
                mark_block_unreachable(body)

        if guard_value == MYPY_TRUE:
            # This condition is false at runtime; this will affect
            # import priorities.
            mark_block_mypy_only(s.bodies[i])


def assert_will_always_fail(s: AssertStmt, options: Options) -> bool:
    return infer_condition_value(s.expr, options) in (ALWAYS_FALSE, MYPY_FALSE)


def infer_condition_value(expr: Expression, options: Options) -> int:
    """Infer whether the given condition is always true/false.

    Return ALWAYS_TRUE if always true, ALWAYS_FALSE if always false,
    MYPY_TRUE if true under mypy and false at runtime, MYPY_FALSE if
    false under mypy and true at runtime, else TRUTH_VALUE_UNKNOWN.
    """
    pyversion = options.python_version
    name = ""
    negated = False
    alias = expr
    if isinstance(alias, UnaryExpr):
        if alias.op == "not":
            expr = alias.expr
            negated = True
    result = TRUTH_VALUE_UNKNOWN
    if isinstance(expr, NameExpr):
        name = expr.name
    elif isinstance(expr, MemberExpr):
        name = expr.name
    elif isinstance(expr, OpExpr) and expr.op in ("and", "or"):
        left = infer_condition_value(expr.left, options)
        if (left in (ALWAYS_TRUE, MYPY_TRUE) and expr.op == "and") or (
            left in (ALWAYS_FALSE, MYPY_FALSE) and expr.op == "or"
        ):
            # Either `True and <other>` or `False or <other>`: the result will
            # always be the right-hand-side.
            return infer_condition_value(expr.right, options)
        else:
            # The result will always be the left-hand-side (e.g. ALWAYS_* or
            # TRUTH_VALUE_UNKNOWN).
            return left
    else:
        result = consider_sys_version_info(expr, pyversion)
        if result == TRUTH_VALUE_UNKNOWN:
            result = consider_sys_platform(expr, options.platform)
    if result == TRUTH_VALUE_UNKNOWN:
        if name == "PY2":
            result = ALWAYS_FALSE
        elif name == "PY3":
            result = ALWAYS_TRUE
        elif name == "MYPY" or name == "TYPE_CHECKING":
            result = MYPY_TRUE
        elif name in options.always_true:
            result = ALWAYS_TRUE
        elif name in options.always_false:
            result = ALWAYS_FALSE
    if negated:
        result = inverted_truth_mapping[result]
    return result


def infer_pattern_value(pattern: Pattern) -> int:
    if isinstance(pattern, AsPattern) and pattern.pattern is None:
        return ALWAYS_TRUE
    elif isinstance(pattern, OrPattern) and any(
        infer_pattern_value(p) == ALWAYS_TRUE for p in pattern.patterns
    ):
        return ALWAYS_TRUE
    else:
        return TRUTH_VALUE_UNKNOWN


def consider_sys_version_info(expr: Expression, pyversion: tuple[int, ...]) -> int:
    """Consider whether expr is a comparison involving sys.version_info.

    Return ALWAYS_TRUE, ALWAYS_FALSE, or TRUTH_VALUE_UNKNOWN.
    """
    # Cases supported:
    # - sys.version_info[<int>] <compare_op> <int>
    # - sys.version_info[:<int>] <compare_op> <tuple_of_n_ints>
    # - sys.version_info <compare_op> <tuple_of_1_or_2_ints>
    #   (in this case <compare_op> must be >, >=, <, <=, but cannot be ==, !=)
    if not isinstance(expr, ComparisonExpr):
        return TRUTH_VALUE_UNKNOWN
    # Let's not yet support chained comparisons.
    if len(expr.operators) > 1:
        return TRUTH_VALUE_UNKNOWN
    op = expr.operators[0]
    if op not in ("==", "!=", "<=", ">=", "<", ">"):
        return TRUTH_VALUE_UNKNOWN

    index = contains_sys_version_info(expr.operands[0])
    thing = contains_int_or_tuple_of_ints(expr.operands[1])
    if index is None or thing is None:
        index = contains_sys_version_info(expr.operands[1])
        thing = contains_int_or_tuple_of_ints(expr.operands[0])
        op = reverse_op[op]
    if isinstance(index, int) and isinstance(thing, int):
        # sys.version_info[i] <compare_op> k
        if 0 <= index <= 1:
            return fixed_comparison(pyversion[index], op, thing)
        else:
            return TRUTH_VALUE_UNKNOWN
    elif isinstance(index, tuple) and isinstance(thing, tuple):
        lo, hi = index
        if lo is None:
            lo = 0
        if hi is None:
            hi = 2
        if 0 <= lo < hi <= 2:
            val = pyversion[lo:hi]
            if len(val) == len(thing) or len(val) > len(thing) and op not in ("==", "!="):
                return fixed_comparison(val, op, thing)
    return TRUTH_VALUE_UNKNOWN


def consider_sys_platform(expr: Expression, platform: str) -> int:
    """Consider whether expr is a comparison involving sys.platform.

    Return ALWAYS_TRUE, ALWAYS_FALSE, or TRUTH_VALUE_UNKNOWN.
    """
    # Cases supported:
    # - sys.platform == 'posix'
    # - sys.platform != 'win32'
    # - sys.platform.startswith('win')
    if isinstance(expr, ComparisonExpr):
        # Let's not yet support chained comparisons.
        if len(expr.operators) > 1:
            return TRUTH_VALUE_UNKNOWN
        op = expr.operators[0]
        if op not in ("==", "!="):
            return TRUTH_VALUE_UNKNOWN
        if not is_sys_attr(expr.operands[0], "platform"):
            return TRUTH_VALUE_UNKNOWN
        right = expr.operands[1]
        if not isinstance(right, StrExpr):
            return TRUTH_VALUE_UNKNOWN
        return fixed_comparison(platform, op, right.value)
    elif isinstance(expr, CallExpr):
        if not isinstance(expr.callee, MemberExpr):
            return TRUTH_VALUE_UNKNOWN
        if len(expr.args) != 1 or not isinstance(expr.args[0], StrExpr):
            return TRUTH_VALUE_UNKNOWN
        if not is_sys_attr(expr.callee.expr, "platform"):
            return TRUTH_VALUE_UNKNOWN
        if expr.callee.name != "startswith":
            return TRUTH_VALUE_UNKNOWN
        if platform.startswith(expr.args[0].value):
            return ALWAYS_TRUE
        else:
            return ALWAYS_FALSE
    else:
        return TRUTH_VALUE_UNKNOWN


Targ = TypeVar("Targ", int, str, Tuple[int, ...])


def fixed_comparison(left: Targ, op: str, right: Targ) -> int:
    rmap = {False: ALWAYS_FALSE, True: ALWAYS_TRUE}
    if op == "==":
        return rmap[left == right]
    if op == "!=":
        return rmap[left != right]
    if op == "<=":
        return rmap[left <= right]
    if op == ">=":
        return rmap[left >= right]
    if op == "<":
        return rmap[left < right]
    if op == ">":
        return rmap[left > right]
    return TRUTH_VALUE_UNKNOWN


def contains_int_or_tuple_of_ints(expr: Expression) -> None | int | tuple[int, ...]:
    if isinstance(expr, IntExpr):
        return expr.value
    if isinstance(expr, TupleExpr):
        if literal(expr) == LITERAL_YES:
            thing = []
            for x in expr.items:
                if not isinstance(x, IntExpr):
                    return None
                thing.append(x.value)
            return tuple(thing)
    return None


def contains_sys_version_info(expr: Expression) -> None | int | tuple[int | None, int | None]:
    if is_sys_attr(expr, "version_info"):
        return (None, None)  # Same as sys.version_info[:]
    if isinstance(expr, IndexExpr) and is_sys_attr(expr.base, "version_info"):
        index = expr.index
        if isinstance(index, IntExpr):
            return index.value
        if isinstance(index, SliceExpr):
            if index.stride is not None:
                if not isinstance(index.stride, IntExpr) or index.stride.value != 1:
                    return None
            begin = end = None
            if index.begin_index is not None:
                if not isinstance(index.begin_index, IntExpr):
                    return None
                begin = index.begin_index.value
            if index.end_index is not None:
                if not isinstance(index.end_index, IntExpr):
                    return None
                end = index.end_index.value
            return (begin, end)
    return None


def is_sys_attr(expr: Expression, name: str) -> bool:
    # TODO: This currently doesn't work with code like this:
    # - import sys as _sys
    # - from sys import version_info
    if isinstance(expr, MemberExpr) and expr.name == name:
        if isinstance(expr.expr, NameExpr) and expr.expr.name == "sys":
            # TODO: Guard against a local named sys, etc.
            # (Though later passes will still do most checking.)
            return True
    return False


def mark_block_unreachable(block: Block) -> None:
    block.is_unreachable = True
    block.accept(MarkImportsUnreachableVisitor())


class MarkImportsUnreachableVisitor(TraverserVisitor):
    """Visitor that flags all imports nested within a node as unreachable."""

    def visit_import(self, node: Import) -> None:
        node.is_unreachable = True

    def visit_import_from(self, node: ImportFrom) -> None:
        node.is_unreachable = True

    def visit_import_all(self, node: ImportAll) -> None:
        node.is_unreachable = True


def mark_block_mypy_only(block: Block) -> None:
    block.accept(MarkImportsMypyOnlyVisitor())


class MarkImportsMypyOnlyVisitor(TraverserVisitor):
    """Visitor that sets is_mypy_only (which affects priority)."""

    def visit_import(self, node: Import) -> None:
        node.is_mypy_only = True

    def visit_import_from(self, node: ImportFrom) -> None:
        node.is_mypy_only = True

    def visit_import_all(self, node: ImportAll) -> None:
        node.is_mypy_only = True

    def visit_func_def(self, node: FuncDef) -> None:
        node.is_mypy_only = True
