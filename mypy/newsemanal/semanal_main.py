"""Top-level logic for the new semantic analyzer.

The semantic analyzer binds names, resolves imports, detects various
special constructs that don't have dedicated AST nodes after parse
(such as 'cast' which looks like a call), and performs various simple
consistency checks.

Semantic analysis of each SCC (strongly connected component; import
cycle) is performed in one unit. Each module is analyzed as multiple
separate *targets*; the module top level is one target and each function
is a target. Nested functions are not separate targets, however. This is
mostly identical to targets used by mypy daemon (but classes aren't
targets in semantic analysis).

We first analyze each module top level in an SCC. If we encounter some
names that we can't bind because the target of the name may not have
been processed yet, we *defer* the current target for further
processing. Deferred targets will be analyzed additional times until
everything can be bound, or we reach a maximum number of iterations.

We keep track of a set of incomplete namespaces, i.e. namespaces that we
haven't finished populating yet. References to these namespaces cause a
deferral if they can't be satisfied. Initially every module in the SCC
will be incomplete.
"""

from typing import List, Tuple, Optional, Union

from mypy.nodes import (
    Node, SymbolTable, SymbolNode, MypyFile, TypeInfo, FuncDef, Decorator, OverloadedFuncDef
)

MYPY = False
if MYPY:
    from mypy.build import Graph, State


# Perform up to this many semantic analysis iterations until giving up trying to bind all names.
MAX_ITERATIONS = 10


def semantic_analysis_for_scc(graph: 'Graph', scc: List[str]) -> None:
    """Perform semantic analysis for all modules in a SCC (import cycle).

    Assume that reachability analysis has already been performed.
    """
    # Note that functions can't define new module-level attributes
    # using 'global x', since module top levels are fully processed
    # before functions. This limitation is unlikely to go away soon.
    process_top_levels(graph, scc)
    process_functions(graph, scc)


def process_top_levels(graph: 'Graph', scc: List[str]) -> None:
    # Process top levels until everything has been bound.

    # Initialize ASTs and symbol tables.
    for id in scc:
        state = graph[id]
        assert state.tree is not None
        state.manager.new_semantic_analyzer.prepare_file(state.tree)

    # Initially all namespaces in the SCC are incomplete (well they are empty).
    state.manager.incomplete_namespaces.update(scc)

    worklist = scc[:]
    iteration = 0
    while worklist:
        iteration += 1
        if iteration == MAX_ITERATIONS:
            # Give up. Likely it's impossible to bind all names.
            state.manager.incomplete_namespaces.clear()
        all_deferred = []  # type: List[str]
        while worklist:
            next_id = worklist.pop()
            state = graph[next_id]
            assert state.tree is not None
            deferred, incomplete = semantic_analyze_module(next_id, state, state.tree)
            all_deferred += deferred
            if not incomplete:
                state.manager.incomplete_namespaces.discard(next_id)
        worklist = all_deferred


def process_functions(graph: 'Graph', scc: List[str]) -> None:
    # TODO: This doesn't quite work yet
    # Process functions.
    deferred = []  # type: List[str]
    for module in scc:
        tree = graph[module].tree
        assert tree is not None
        symtable = tree.names
        targets = get_all_leaf_targets(symtable, module, None)
        for target, node, active_type in targets:
            semantic_analyze_function(graph[module], node, active_type)


TargetInfo = Tuple[str, Union[MypyFile, FuncDef], Optional[TypeInfo]]


def get_all_leaf_targets(symtable: SymbolTable,
                         prefix: str,
                         active_type: Optional[TypeInfo]) -> List[TargetInfo]:
    """Return all leaf targets in a symbol table (module-level and methods)."""
    result = []  # type: List[TargetInfo]
    for name, node in symtable.items():
        new_prefix = prefix + '.' + name
        # TODO: Decorated function
        # TODO: Overloaded function
        if isinstance(node.node, (FuncDef, TypeInfo)):
            if '@' in node.node.fullname() and isinstance(node.node, TypeInfo):
                new_prefix += '@' + str(node.node.defn.line)
            if node.node.fullname() == new_prefix:
                if isinstance(node.node, TypeInfo):
                    result += get_all_leaf_targets(node.node.names, new_prefix, node.node)
                else:
                    result.append((new_prefix, node.node, active_type))
    return result


def semantic_analyze_module(target: str,
                            state: 'State',
                            node: Union[MypyFile, FuncDef]) -> Tuple[List[str], bool]:
    tree = state.tree
    assert tree is not None
    analyzer = state.manager.new_semantic_analyzer
    # TODO: Move initialization to somewhere else
    analyzer.global_decls = [set()]
    analyzer.nonlocal_decls = [set()]
    analyzer.globals = tree.names
    with state.wrap_context():
        with analyzer.file_context(file_node=tree,
                                   fnam=tree.path,
                                   options=state.options,
                                   active_type=None):
            analyzer.refresh_partial(node, [])
    if analyzer.deferred:
        return [target], analyzer.incomplete
    else:
        return [], analyzer.incomplete


def semantic_analyze_function(state: 'State', node: FuncDef, active_type: Optional[TypeInfo]) -> None:
    """Analyze function body."""
    analyzer = state.manager.new_semantic_analyzer
    tree = state.tree
    assert tree is not None
    # TODO: Move initialization to somewhere else
    analyzer.global_decls = [set()]
    analyzer.nonlocal_decls = [set()]
    analyzer.globals = tree.names
    analyzer.incomplete_namespaces.add(tree.fullname())
    defer = True
    iteration = 0
    while defer:
        iteration += 1
        if iteration == MAX_ITERATIONS:
            if tree.fullname() in analyzer.incomplete_namespaces:
                analyzer.incomplete_namespaces.remove(tree.fullname())
        with state.wrap_context():
            with analyzer.file_context(file_node=tree,
                                       fnam=tree.path,
                                       options=state.options,
                                       active_type=active_type):
                analyzer.refresh_partial(node, [], recurse_nested=False)
                defer = analyzer.deferred
                analyzer.override_locals = analyzer.last_locals

    analyzer.override_locals = None
    targets = get_all_leaf_targets(analyzer.last_locals, tree.fullname(), active_type)
    analyzer.locals.append(analyzer.last_locals)
    for target, node, active_type in targets:
        semantic_analyze_function(state, node, active_type)
    analyzer.locals.pop()
    if tree.fullname() in analyzer.incomplete_namespaces:
        analyzer.incomplete_namespaces.remove(tree.fullname())
