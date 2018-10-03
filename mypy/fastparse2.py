"""
This file is nearly identical to `fastparse.py`, except that it works with a Python 2
AST instead of a Python 3 AST.

Previously, how we handled Python 2 code was by first obtaining the Python 2 AST via
typed_ast, converting it into a Python 3 AST by using typed_ast.conversion, then
running it through mypy.fastparse.

While this worked, it did add some overhead, especially in larger Python 2 codebases.
This module allows us to skip the conversion step, saving us some time.

The reason why this file is not easily merged with mypy.fastparse despite the large amount
of redundancy is because the Python 2 AST and the Python 3 AST nodes belong to two completely
different class hierarchies, which made it difficult to write a shared visitor between the
two in a typesafe way.
"""
import sys

from typing import Tuple, Union, TypeVar, Callable, Sequence, Optional, Any, Dict, cast, List
MYPY = False
if MYPY:
    import typing  # for typing.Type, which conflicts with types.Type
    from typing_extensions import Final

from mypy.sharedparse import (
    special_function_elide_names, argument_elide_name,
)
from mypy.nodes import (
    MypyFile, Node, ImportBase, Import, ImportAll, ImportFrom, FuncDef, OverloadedFuncDef,
    ClassDef, Decorator, Block, Var, OperatorAssignmentStmt,
    ExpressionStmt, AssignmentStmt, ReturnStmt, RaiseStmt, AssertStmt,
    DelStmt, BreakStmt, ContinueStmt, PassStmt, GlobalDecl,
    WhileStmt, ForStmt, IfStmt, TryStmt, WithStmt,
    TupleExpr, GeneratorExpr, ListComprehension, ListExpr, ConditionalExpr,
    DictExpr, SetExpr, NameExpr, IntExpr, StrExpr, UnicodeExpr,
    FloatExpr, CallExpr, SuperExpr, MemberExpr, IndexExpr, SliceExpr, OpExpr,
    UnaryExpr, LambdaExpr, ComparisonExpr, DictionaryComprehension,
    SetComprehension, ComplexExpr, EllipsisExpr, YieldExpr, Argument,
    Expression, Statement, BackquoteExpr, PrintStmt, ExecStmt,
    ARG_POS, ARG_OPT, ARG_STAR, ARG_NAMED, ARG_STAR2, OverloadPart, check_arg_names,
    FakeInfo,
)
from mypy.types import (
    Type, CallableType, AnyType, UnboundType, EllipsisType, TypeOfAny, Instance,
)
from mypy import messages
from mypy.errors import Errors
from mypy.fastparse import TypeConverter, parse_type_comment
from mypy.options import Options

try:
    from typed_ast import ast27
    from typed_ast.ast27 import (
        AST,
        Call,
        Name,
        Attribute,
        Tuple as ast27_Tuple,
    )
    from typed_ast import ast3
    from typed_ast.ast3 import (
        FunctionType,
        Ellipsis as ast3_Ellipsis,
    )
except ImportError:
    if sys.version_info.minor > 2:
        try:
            from typed_ast import ast35  # type: ignore
        except ImportError:
            print('The typed_ast package is not installed.\n'
                  'You can install it with `python3 -m pip install typed-ast`.',
                  file=sys.stderr)
        else:
            print('You need a more recent version of the typed_ast package.\n'
                  'You can update to the latest version with '
                  '`python3 -m pip install -U typed-ast`.',
                  file=sys.stderr)
    else:
        print('Mypy requires the typed_ast package, which is only compatible with\n'
              'Python 3.3 and greater.', file=sys.stderr)
    sys.exit(1)

N = TypeVar('N', bound=Node)

# There is no way to create reasonable fallbacks at this stage,
# they must be patched later.
MISSING_FALLBACK = FakeInfo("fallback can't be filled out until semanal")  # type: Final
_dummy_fallback = Instance(MISSING_FALLBACK, [], -1)  # type: Final

TYPE_COMMENT_SYNTAX_ERROR = 'syntax error in type comment'  # type: Final
TYPE_COMMENT_AST_ERROR = 'invalid type comment'  # type: Final


def parse(source: Union[str, bytes],
          fnam: str,
          module: Optional[str],
          errors: Optional[Errors] = None,
          options: Optional[Options] = None) -> MypyFile:
    """Parse a source file, without doing any semantic analysis.

    Return the parse tree. If errors is not provided, raise ParseError
    on failure. Otherwise, use the errors object to report parse errors.
    """
    raise_on_error = False
    if errors is None:
        errors = Errors()
        raise_on_error = True
    if options is None:
        options = Options()
    errors.set_file(fnam, module)
    is_stub_file = fnam.endswith('.pyi')
    try:
        assert options.python_version[0] < 3 and not is_stub_file
        ast = ast27.parse(source, fnam, 'exec')
        tree = ASTConverter(options=options,
                            is_stub=is_stub_file,
                            errors=errors,
                            ).visit(ast)
        assert isinstance(tree, MypyFile)
        tree.path = fnam
        tree.is_stub = is_stub_file
    except SyntaxError as e:
        errors.report(e.lineno, e.offset, e.msg, blocker=True)
        tree = MypyFile([], [], False, set())

    if raise_on_error and errors.is_errors():
        errors.raise_error()

    return tree


def is_no_type_check_decorator(expr: ast27.expr) -> bool:
    if isinstance(expr, Name):
        return expr.id == 'no_type_check'
    elif isinstance(expr, Attribute):
        if isinstance(expr.value, Name):
            return expr.value.id == 'typing' and expr.attr == 'no_type_check'
    return False


class ASTConverter:
    def __init__(self,
                 options: Options,
                 is_stub: bool,
                 errors: Errors) -> None:
        self.class_nesting = 0
        self.imports = []  # type: List[ImportBase]

        self.options = options
        self.is_stub = is_stub
        self.errors = errors

        # Cache of visit_X methods keyed by type of visited object
        self.visitor_cache = {}  # type: Dict[type, Callable[[Optional[AST]], Any]]

    def fail(self, msg: str, line: int, column: int) -> None:
        self.errors.report(line, column, msg, blocker=True)

    def visit(self, node: Optional[AST]) -> Any:  # same as in typed_ast stub
        if node is None:
            return None
        typeobj = type(node)
        visitor = self.visitor_cache.get(typeobj)
        if visitor is None:
            method = 'visit_' + node.__class__.__name__
            visitor = getattr(self, method)
            self.visitor_cache[typeobj] = visitor
        return visitor(node)

    def set_line(self, node: N, n: Union[ast27.expr, ast27.stmt]) -> N:
        node.line = n.lineno
        node.column = n.col_offset
        return node

    def translate_expr_list(self, l: Sequence[AST]) -> List[Expression]:
        res = []  # type: List[Expression]
        for e in l:
            exp = self.visit(e)
            assert isinstance(exp, Expression)
            res.append(exp)
        return res

    def translate_stmt_list(self, l: Sequence[AST]) -> List[Statement]:
        res = []  # type: List[Statement]
        for e in l:
            stmt = self.visit(e)
            assert isinstance(stmt, Statement)
            res.append(stmt)
        return res

    op_map = {
        ast27.Add: '+',
        ast27.Sub: '-',
        ast27.Mult: '*',
        ast27.Div: '/',
        ast27.Mod: '%',
        ast27.Pow: '**',
        ast27.LShift: '<<',
        ast27.RShift: '>>',
        ast27.BitOr: '|',
        ast27.BitXor: '^',
        ast27.BitAnd: '&',
        ast27.FloorDiv: '//'
    }  # type: Final[Dict[typing.Type[AST], str]]

    def from_operator(self, op: ast27.operator) -> str:
        op_name = ASTConverter.op_map.get(type(op))
        if op_name is None:
            raise RuntimeError('Unknown operator ' + str(type(op)))
        elif op_name == '@':
            raise RuntimeError('mypy does not support the MatMult operator')
        else:
            return op_name

    comp_op_map = {
        ast27.Gt: '>',
        ast27.Lt: '<',
        ast27.Eq: '==',
        ast27.GtE: '>=',
        ast27.LtE: '<=',
        ast27.NotEq: '!=',
        ast27.Is: 'is',
        ast27.IsNot: 'is not',
        ast27.In: 'in',
        ast27.NotIn: 'not in'
    }  # type: Final[Dict[typing.Type[AST], str]]

    def from_comp_operator(self, op: ast27.cmpop) -> str:
        op_name = ASTConverter.comp_op_map.get(type(op))
        if op_name is None:
            raise RuntimeError('Unknown comparison operator ' + str(type(op)))
        else:
            return op_name

    def as_block(self, stmts: List[ast27.stmt], lineno: int) -> Optional[Block]:
        b = None
        if stmts:
            b = Block(self.fix_function_overloads(self.translate_stmt_list(stmts)))
            b.set_line(lineno)
        return b

    def as_required_block(self, stmts: List[ast27.stmt], lineno: int) -> Block:
        assert stmts  # must be non-empty
        b = Block(self.fix_function_overloads(self.translate_stmt_list(stmts)))
        b.set_line(lineno)
        return b

    def fix_function_overloads(self, stmts: List[Statement]) -> List[Statement]:
        ret = []  # type: List[Statement]
        current_overload = []  # type: List[OverloadPart]
        current_overload_name = None  # type: Optional[str]
        for stmt in stmts:
            if (current_overload_name is not None
                    and isinstance(stmt, (Decorator, FuncDef))
                    and stmt.name() == current_overload_name):
                current_overload.append(stmt)
            else:
                if len(current_overload) == 1:
                    ret.append(current_overload[0])
                elif len(current_overload) > 1:
                    ret.append(OverloadedFuncDef(current_overload))

                if isinstance(stmt, Decorator):
                    current_overload = [stmt]
                    current_overload_name = stmt.name()
                else:
                    current_overload = []
                    current_overload_name = None
                    ret.append(stmt)

        if len(current_overload) == 1:
            ret.append(current_overload[0])
        elif len(current_overload) > 1:
            ret.append(OverloadedFuncDef(current_overload))
        return ret

    def in_class(self) -> bool:
        return self.class_nesting > 0

    def translate_module_id(self, id: str) -> str:
        """Return the actual, internal module id for a source text id.

        For example, translate '__builtin__' in Python 2 to 'builtins'.
        """
        if id == self.options.custom_typing_module:
            return 'typing'
        elif id == '__builtin__':
            # HACK: __builtin__ in Python 2 is aliases to builtins. However, the implementation
            #   is named __builtin__.py (there is another layer of translation elsewhere).
            return 'builtins'
        return id

    def visit_Module(self, mod: ast27.Module) -> MypyFile:
        body = self.fix_function_overloads(self.translate_stmt_list(mod.body))

        return MypyFile(body,
                        self.imports,
                        False,
                        {ti.lineno for ti in mod.type_ignores},
                        )

    # --- stmt ---
    # FunctionDef(identifier name, arguments args,
    #             stmt* body, expr* decorator_list, expr? returns, string? type_comment)
    # arguments = (arg* args, arg? vararg, arg* kwonlyargs, expr* kw_defaults,
    #              arg? kwarg, expr* defaults)
    def visit_FunctionDef(self, n: ast27.FunctionDef) -> Statement:
        lineno = n.lineno
        converter = TypeConverter(self.errors, line=lineno)
        args, decompose_stmts = self.transform_args(n.args, lineno)

        arg_kinds = [arg.kind for arg in args]
        arg_names = [arg.variable.name() for arg in args]  # type: List[Optional[str]]
        arg_names = [None if argument_elide_name(name) else name for name in arg_names]
        if special_function_elide_names(n.name):
            arg_names = [None] * len(arg_names)

        arg_types = []  # type: List[Optional[Type]]
        type_comment = n.type_comment
        if (n.decorator_list and any(is_no_type_check_decorator(d) for d in n.decorator_list)):
            arg_types = [None] * len(args)
            return_type = None
        elif type_comment is not None and len(type_comment) > 0:
            try:
                func_type_ast = ast3.parse(type_comment, '<func_type>', 'func_type')
                assert isinstance(func_type_ast, FunctionType)
                # for ellipsis arg
                if (len(func_type_ast.argtypes) == 1 and
                        isinstance(func_type_ast.argtypes[0], ast3_Ellipsis)):
                    arg_types = [a.type_annotation
                                 if a.type_annotation is not None
                                 else AnyType(TypeOfAny.unannotated)
                                 for a in args]
                else:
                    # PEP 484 disallows both type annotations and type comments
                    if any(a.type_annotation is not None for a in args):
                        self.fail(messages.DUPLICATE_TYPE_SIGNATURES, lineno, n.col_offset)
                    arg_types = [a if a is not None else AnyType(TypeOfAny.unannotated) for
                                 a in converter.translate_expr_list(func_type_ast.argtypes)]
                return_type = converter.visit(func_type_ast.returns)

                # add implicit self type
                if self.in_class() and len(arg_types) < len(args):
                    arg_types.insert(0, AnyType(TypeOfAny.special_form))
            except SyntaxError:
                self.fail(TYPE_COMMENT_SYNTAX_ERROR, lineno, n.col_offset)
                arg_types = [AnyType(TypeOfAny.from_error)] * len(args)
                return_type = AnyType(TypeOfAny.from_error)
        else:
            arg_types = [a.type_annotation for a in args]
            return_type = converter.visit(None)

        for arg, arg_type in zip(args, arg_types):
            self.set_type_optional(arg_type, arg.initializer)

        func_type = None
        if any(arg_types) or return_type:
            if len(arg_types) != 1 and any(isinstance(t, EllipsisType) for t in arg_types):
                self.fail("Ellipses cannot accompany other argument types "
                          "in function type signature.", lineno, 0)
            elif len(arg_types) > len(arg_kinds):
                self.fail('Type signature has too many arguments', lineno, 0)
            elif len(arg_types) < len(arg_kinds):
                self.fail('Type signature has too few arguments', lineno, 0)
            else:
                any_type = AnyType(TypeOfAny.unannotated)
                func_type = CallableType([a if a is not None else any_type for a in arg_types],
                                        arg_kinds,
                                        arg_names,
                                        return_type if return_type is not None else any_type,
                                        _dummy_fallback)

        body = self.as_required_block(n.body, lineno)
        if decompose_stmts:
            body.body = decompose_stmts + body.body
        func_def = FuncDef(n.name,
                       args,
                       body,
                       func_type)
        if isinstance(func_def.type, CallableType):
            # semanal.py does some in-place modifications we want to avoid
            func_def.unanalyzed_type = func_def.type.copy_modified()
        if func_type is not None:
            func_type.definition = func_def
            func_type.line = lineno

        if n.decorator_list:
            var = Var(func_def.name())
            var.is_ready = False
            var.set_line(n.decorator_list[0].lineno)

            func_def.is_decorated = True
            func_def.set_line(lineno + len(n.decorator_list))
            func_def.body.set_line(func_def.get_line())
            dec = Decorator(func_def, self.translate_expr_list(n.decorator_list), var)
            dec.set_line(lineno, n.col_offset)
            return dec
        else:
            # Overrides set_line -- can't use self.set_line
            func_def.set_line(lineno, n.col_offset)
            return func_def

    def set_type_optional(self, type: Optional[Type], initializer: Optional[Expression]) -> None:
        if self.options.no_implicit_optional:
            return
        # Indicate that type should be wrapped in an Optional if arg is initialized to None.
        optional = isinstance(initializer, NameExpr) and initializer.name == 'None'
        if isinstance(type, UnboundType):
            type.optional = optional

    def transform_args(self,
                       n: ast27.arguments,
                       line: int,
                       ) -> Tuple[List[Argument], List[Statement]]:
        type_comments = n.type_comments  # type: Sequence[Optional[str]]
        converter = TypeConverter(self.errors, line=line)
        decompose_stmts = []  # type: List[Statement]

        n_args = n.args
        args = [(self.convert_arg(i, arg, line, decompose_stmts),
                 self.get_type(i, type_comments, converter))
                for i, arg in enumerate(n_args)]
        defaults = self.translate_expr_list(n.defaults)
        names = [name for arg in n_args for name in self.extract_names(arg)]  # type: List[str]

        new_args = []  # type: List[Argument]
        num_no_defaults = len(args) - len(defaults)
        # positional arguments without defaults
        for a, annotation in args[:num_no_defaults]:
            new_args.append(Argument(a, annotation, None, ARG_POS))

        # positional arguments with defaults
        for (a, annotation), d in zip(args[num_no_defaults:], defaults):
            new_args.append(Argument(a, annotation, d, ARG_OPT))

        # *arg
        if n.vararg is not None:
            new_args.append(Argument(Var(n.vararg),
                                     self.get_type(len(args), type_comments, converter),
                                     None,
                                     ARG_STAR))
            names.append(n.vararg)

        # **kwarg
        if n.kwarg is not None:
            typ = self.get_type(len(args) + (0 if n.vararg is None else 1),
                                type_comments,
                                converter)
            new_args.append(Argument(Var(n.kwarg), typ, None, ARG_STAR2))
            names.append(n.kwarg)

        # We don't have any context object to give, but we have closed around the line num
        def fail_arg(msg: str, arg: None) -> None:
            self.fail(msg, line, 0)
        check_arg_names(names, [None] * len(names), fail_arg)

        return new_args, decompose_stmts

    def extract_names(self, arg: ast27.expr) -> List[str]:
        if isinstance(arg, Name):
            return [arg.id]
        elif isinstance(arg, ast27_Tuple):
            return [name for elt in arg.elts for name in self.extract_names(elt)]
        else:
            return []

    def convert_arg(self, index: int, arg: ast27.expr, line: int,
                    decompose_stmts: List[Statement]) -> Var:
        if isinstance(arg, Name):
            v = arg.id
        elif isinstance(arg, ast27_Tuple):
            v = '__tuple_arg_{}'.format(index + 1)
            rvalue = NameExpr(v)
            rvalue.set_line(line)
            assignment = AssignmentStmt([self.visit(arg)], rvalue)
            assignment.set_line(line)
            decompose_stmts.append(assignment)
        else:
            raise RuntimeError("'{}' is not a valid argument.".format(ast27.dump(arg)))
        return Var(v)

    def get_type(self, i: int, type_comments: Sequence[Optional[str]],
                 converter: TypeConverter) -> Optional[Type]:
        if i < len(type_comments):
            comment = type_comments[i]
            if comment is not None:
                return converter.visit_raw_str(comment)
        return None

    def stringify_name(self, n: AST) -> str:
        if isinstance(n, Name):
            return n.id
        elif isinstance(n, Attribute):
            return "{}.{}".format(self.stringify_name(n.value), n.attr)
        else:
            assert False, "can't stringify " + str(type(n))

    # ClassDef(identifier name,
    #  expr* bases,
    #  keyword* keywords,
    #  stmt* body,
    #  expr* decorator_list)
    def visit_ClassDef(self, n: ast27.ClassDef) -> ClassDef:
        self.class_nesting += 1

        cdef = ClassDef(n.name,
                        self.as_required_block(n.body, n.lineno),
                        None,
                        self.translate_expr_list(n.bases),
                        metaclass=None)
        cdef.decorators = self.translate_expr_list(n.decorator_list)
        self.set_line(cdef, n)
        self.class_nesting -= 1
        return cdef

    # Return(expr? value)
    def visit_Return(self, n: ast27.Return) -> ReturnStmt:
        s = ReturnStmt(self.visit(n.value))
        return self.set_line(s, n)

    # Delete(expr* targets)
    def visit_Delete(self, n: ast27.Delete) -> DelStmt:
        if len(n.targets) > 1:
            tup = TupleExpr(self.translate_expr_list(n.targets))
            tup.set_line(n.lineno)
            s = DelStmt(tup)
        else:
            s = DelStmt(self.visit(n.targets[0]))
        return self.set_line(s, n)

    # Assign(expr* targets, expr value, string? type_comment)
    def visit_Assign(self, n: ast27.Assign) -> AssignmentStmt:
        typ = None
        if n.type_comment:
            typ = parse_type_comment(n.type_comment, n.lineno, self.errors)

        s = AssignmentStmt(self.translate_expr_list(n.targets),
                           self.visit(n.value),
                           type=typ)
        return self.set_line(s, n)

    # AugAssign(expr target, operator op, expr value)
    def visit_AugAssign(self, n: ast27.AugAssign) -> OperatorAssignmentStmt:
        s = OperatorAssignmentStmt(self.from_operator(n.op),
                                   self.visit(n.target),
                                   self.visit(n.value))
        return self.set_line(s, n)

    # For(expr target, expr iter, stmt* body, stmt* orelse, string? type_comment)
    def visit_For(self, n: ast27.For) -> ForStmt:
        if n.type_comment is not None:
            target_type = parse_type_comment(n.type_comment, n.lineno, self.errors)
        else:
            target_type = None
        s = ForStmt(self.visit(n.target),
                    self.visit(n.iter),
                    self.as_required_block(n.body, n.lineno),
                    self.as_block(n.orelse, n.lineno),
                    target_type)
        return self.set_line(s, n)

    # While(expr test, stmt* body, stmt* orelse)
    def visit_While(self, n: ast27.While) -> WhileStmt:
        s = WhileStmt(self.visit(n.test),
                      self.as_required_block(n.body, n.lineno),
                      self.as_block(n.orelse, n.lineno))
        return self.set_line(s, n)

    # If(expr test, stmt* body, stmt* orelse)
    def visit_If(self, n: ast27.If) -> IfStmt:
        s = IfStmt([self.visit(n.test)],
                   [self.as_required_block(n.body, n.lineno)],
                   self.as_block(n.orelse, n.lineno))
        return self.set_line(s, n)

    # With(withitem* items, stmt* body, string? type_comment)
    def visit_With(self, n: ast27.With) -> WithStmt:
        if n.type_comment is not None:
            target_type = parse_type_comment(n.type_comment, n.lineno, self.errors)
        else:
            target_type = None
        s = WithStmt([self.visit(n.context_expr)],
                     [self.visit(n.optional_vars)],
                     self.as_required_block(n.body, n.lineno),
                     target_type)
        return self.set_line(s, n)

    def visit_Raise(self, n: ast27.Raise) -> RaiseStmt:
        if n.type is None:
            e = None
        else:
            if n.inst is None:
                e = self.visit(n.type)
            else:
                if n.tback is None:
                    e = TupleExpr([self.visit(n.type), self.visit(n.inst)])
                else:
                    e = TupleExpr([self.visit(n.type), self.visit(n.inst), self.visit(n.tback)])

        s = RaiseStmt(e, None)
        return self.set_line(s, n)

    # TryExcept(stmt* body, excepthandler* handlers, stmt* orelse)
    def visit_TryExcept(self, n: ast27.TryExcept) -> TryStmt:
        s = self.try_handler(n.body, n.handlers, n.orelse, [], n.lineno)
        return self.set_line(s, n)

    def visit_TryFinally(self, n: ast27.TryFinally) -> TryStmt:
        if len(n.body) == 1 and isinstance(n.body[0], ast27.TryExcept):
            s = self.try_handler([n.body[0]], [], [], n.finalbody, n.lineno)
        else:
            s = self.try_handler(n.body, [], [], n.finalbody, n.lineno)
        return self.set_line(s, n)

    def try_handler(self,
                    body: List[ast27.stmt],
                    handlers: List[ast27.ExceptHandler],
                    orelse: List[ast27.stmt],
                    finalbody: List[ast27.stmt],
                    lineno: int) -> TryStmt:
        vs = []  # type: List[Optional[NameExpr]]
        for item in handlers:
            if item.name is None:
                vs.append(None)
            elif isinstance(item.name, Name):
                vs.append(NameExpr(item.name.id))
            else:
                self.fail("Sorry, `except <expr>, <anything but a name>` is not supported",
                          item.lineno, item.col_offset)
                vs.append(None)
        types = [self.visit(h.type) for h in handlers]
        handlers_ = [self.as_required_block(h.body, h.lineno) for h in handlers]

        return TryStmt(self.as_required_block(body, lineno),
                       vs,
                       types,
                       handlers_,
                       self.as_block(orelse, lineno),
                       self.as_block(finalbody, lineno))

    def visit_Print(self, n: ast27.Print) -> PrintStmt:
        s = PrintStmt(self.translate_expr_list(n.values), n.nl, self.visit(n.dest))
        return self.set_line(s, n)

    def visit_Exec(self, n: ast27.Exec) -> ExecStmt:
        s = ExecStmt(self.visit(n.body),
                     self.visit(n.globals),
                     self.visit(n.locals))
        return self.set_line(s, n)

    def visit_Repr(self, n: ast27.Repr) -> BackquoteExpr:
        s = BackquoteExpr(self.visit(n.value))
        return self.set_line(s, n)

    # Assert(expr test, expr? msg)
    def visit_Assert(self, n: ast27.Assert) -> AssertStmt:
        s = AssertStmt(self.visit(n.test), self.visit(n.msg))
        return self.set_line(s, n)

    # Import(alias* names)
    def visit_Import(self, n: ast27.Import) -> Import:
        names = []  # type: List[Tuple[str, Optional[str]]]
        for alias in n.names:
            name = self.translate_module_id(alias.name)
            asname = alias.asname
            if asname is None and name != alias.name:
                # if the module name has been translated (and it's not already
                # an explicit import-as), make it an implicit import-as the
                # original name
                asname = alias.name
            names.append((name, asname))
        i = Import(names)
        self.imports.append(i)
        return self.set_line(i, n)

    # ImportFrom(identifier? module, alias* names, int? level)
    def visit_ImportFrom(self, n: ast27.ImportFrom) -> ImportBase:
        assert n.level is not None
        if len(n.names) == 1 and n.names[0].name == '*':
            mod = n.module if n.module is not None else ''
            i = ImportAll(mod, n.level)  # type: ImportBase
        else:
            i = ImportFrom(self.translate_module_id(n.module) if n.module is not None else '',
                           n.level,
                           [(a.name, a.asname) for a in n.names])
        self.imports.append(i)
        return self.set_line(i, n)

    # Global(identifier* names)
    def visit_Global(self, n: ast27.Global) -> GlobalDecl:
        s = GlobalDecl(n.names)
        return self.set_line(s, n)

    # Expr(expr value)
    def visit_Expr(self, n: ast27.Expr) -> ExpressionStmt:
        value = self.visit(n.value)
        s = ExpressionStmt(value)
        return self.set_line(s, n)

    # Pass
    def visit_Pass(self, n: ast27.Pass) -> PassStmt:
        s = PassStmt()
        return self.set_line(s, n)

    # Break
    def visit_Break(self, n: ast27.Break) -> BreakStmt:
        s = BreakStmt()
        return self.set_line(s, n)

    # Continue
    def visit_Continue(self, n: ast27.Continue) -> ContinueStmt:
        s = ContinueStmt()
        return self.set_line(s, n)

    # --- expr ---

    # BoolOp(boolop op, expr* values)
    def visit_BoolOp(self, n: ast27.BoolOp) -> OpExpr:
        # mypy translates (1 and 2 and 3) as (1 and (2 and 3))
        assert len(n.values) >= 2
        if isinstance(n.op, ast27.And):
            op = 'and'
        elif isinstance(n.op, ast27.Or):
            op = 'or'
        else:
            raise RuntimeError('unknown BoolOp ' + str(type(n)))

        # potentially inefficient!
        e = self.group(self.translate_expr_list(n.values), op)
        return self.set_line(e, n)

    def group(self, vals: List[Expression], op: str) -> OpExpr:
        if len(vals) == 2:
            return OpExpr(op, vals[0], vals[1])
        else:
            return OpExpr(op, vals[0], self.group(vals[1:], op))

    # BinOp(expr left, operator op, expr right)
    def visit_BinOp(self, n: ast27.BinOp) -> OpExpr:
        op = self.from_operator(n.op)

        if op is None:
            raise RuntimeError('cannot translate BinOp ' + str(type(n.op)))

        e = OpExpr(op, self.visit(n.left), self.visit(n.right))
        return self.set_line(e, n)

    # UnaryOp(unaryop op, expr operand)
    def visit_UnaryOp(self, n: ast27.UnaryOp) -> UnaryExpr:
        op = None
        if isinstance(n.op, ast27.Invert):
            op = '~'
        elif isinstance(n.op, ast27.Not):
            op = 'not'
        elif isinstance(n.op, ast27.UAdd):
            op = '+'
        elif isinstance(n.op, ast27.USub):
            op = '-'

        if op is None:
            raise RuntimeError('cannot translate UnaryOp ' + str(type(n.op)))

        e = UnaryExpr(op, self.visit(n.operand))
        return self.set_line(e, n)

    # Lambda(arguments args, expr body)
    def visit_Lambda(self, n: ast27.Lambda) -> LambdaExpr:
        args, decompose_stmts = self.transform_args(n.args, n.lineno)

        n_body = ast27.Return(n.body)
        n_body.lineno = n.lineno
        n_body.col_offset = n.col_offset
        body = self.as_required_block([n_body], n.lineno)
        if decompose_stmts:
            body.body = decompose_stmts + body.body

        e = LambdaExpr(args, body)
        e.set_line(n.lineno, n.col_offset)  # Overrides set_line -- can't use self.set_line
        return e

    # IfExp(expr test, expr body, expr orelse)
    def visit_IfExp(self, n: ast27.IfExp) -> ConditionalExpr:
        e = ConditionalExpr(self.visit(n.test),
                            self.visit(n.body),
                            self.visit(n.orelse))
        return self.set_line(e, n)

    # Dict(expr* keys, expr* values)
    def visit_Dict(self, n: ast27.Dict) -> DictExpr:
        e = DictExpr(list(zip(self.translate_expr_list(n.keys),
                              self.translate_expr_list(n.values))))
        return self.set_line(e, n)

    # Set(expr* elts)
    def visit_Set(self, n: ast27.Set) -> SetExpr:
        e = SetExpr(self.translate_expr_list(n.elts))
        return self.set_line(e, n)

    # ListComp(expr elt, comprehension* generators)
    def visit_ListComp(self, n: ast27.ListComp) -> ListComprehension:
        e = ListComprehension(self.visit_GeneratorExp(cast(ast27.GeneratorExp, n)))
        return self.set_line(e, n)

    # SetComp(expr elt, comprehension* generators)
    def visit_SetComp(self, n: ast27.SetComp) -> SetComprehension:
        e = SetComprehension(self.visit_GeneratorExp(cast(ast27.GeneratorExp, n)))
        return self.set_line(e, n)

    # DictComp(expr key, expr value, comprehension* generators)
    def visit_DictComp(self, n: ast27.DictComp) -> DictionaryComprehension:
        targets = [self.visit(c.target) for c in n.generators]
        iters = [self.visit(c.iter) for c in n.generators]
        ifs_list = [self.translate_expr_list(c.ifs) for c in n.generators]
        e = DictionaryComprehension(self.visit(n.key),
                                    self.visit(n.value),
                                    targets,
                                    iters,
                                    ifs_list,
                                    [False for _ in n.generators])
        return self.set_line(e, n)

    # GeneratorExp(expr elt, comprehension* generators)
    def visit_GeneratorExp(self, n: ast27.GeneratorExp) -> GeneratorExpr:
        targets = [self.visit(c.target) for c in n.generators]
        iters = [self.visit(c.iter) for c in n.generators]
        ifs_list = [self.translate_expr_list(c.ifs) for c in n.generators]
        e = GeneratorExpr(self.visit(n.elt),
                          targets,
                          iters,
                          ifs_list,
                          [False for _ in n.generators])
        return self.set_line(e, n)

    # Yield(expr? value)
    def visit_Yield(self, n: ast27.Yield) -> YieldExpr:
        e = YieldExpr(self.visit(n.value))
        return self.set_line(e, n)

    # Compare(expr left, cmpop* ops, expr* comparators)
    def visit_Compare(self, n: ast27.Compare) -> ComparisonExpr:
        operators = [self.from_comp_operator(o) for o in n.ops]
        operands = self.translate_expr_list([n.left] + n.comparators)
        e = ComparisonExpr(operators, operands)
        return self.set_line(e, n)

    # Call(expr func, expr* args, keyword* keywords)
    # keyword = (identifier? arg, expr value)
    def visit_Call(self, n: Call) -> CallExpr:
        arg_types = []  # type: List[ast27.expr]
        arg_kinds = []  # type: List[int]
        signature = []  # type: List[Optional[str]]

        args = n.args
        arg_types.extend(args)
        arg_kinds.extend(ARG_POS for a in args)
        signature.extend(None for a in args)

        if n.starargs is not None:
            arg_types.append(n.starargs)
            arg_kinds.append(ARG_STAR)
            signature.append(None)

        keywords = n.keywords
        arg_types.extend(k.value for k in keywords)
        arg_kinds.extend(ARG_NAMED for k in keywords)
        signature.extend(k.arg for k in keywords)

        if n.kwargs is not None:
            arg_types.append(n.kwargs)
            arg_kinds.append(ARG_STAR2)
            signature.append(None)

        e = CallExpr(self.visit(n.func),
                     self.translate_expr_list(arg_types),
                     arg_kinds,
                     signature)
        return self.set_line(e, n)

    # Num(object n) -- a number as a PyObject.
    def visit_Num(self, n: ast27.Num) -> Expression:
        value = n.n
        is_inverse = False
        if str(n.n).startswith('-'):  # Hackish because of complex.
            value = -n.n
            is_inverse = True

        if isinstance(value, int):
            expr = IntExpr(value)  # type: Expression
        elif isinstance(value, float):
            expr = FloatExpr(value)
        elif isinstance(value, complex):
            expr = ComplexExpr(value)
        else:
            raise RuntimeError('num not implemented for ' + str(type(n.n)))

        if is_inverse:
            expr = UnaryExpr('-', expr)

        return self.set_line(expr, n)

    # Str(string s)
    def visit_Str(self, n: ast27.Str) -> Expression:
        # Hack: assume all string literals in Python 2 stubs are normal
        # strs (i.e. not unicode).  All stubs are parsed with the Python 3
        # parser, which causes unprefixed string literals to be interpreted
        # as unicode instead of bytes.  This hack is generally okay,
        # because mypy considers str literals to be compatible with
        # unicode.
        if isinstance(n.s, bytes):
            s = n.s
            # The following line is a bit hacky, but is the best way to maintain
            # compatibility with how mypy currently parses the contents of bytes literals.
            contents = str(s)[2:-1]
            e = StrExpr(contents)
            return self.set_line(e, n)
        else:
            e = UnicodeExpr(n.s)
            return self.set_line(e, n)

    # Ellipsis
    def visit_Ellipsis(self, n: ast27.Ellipsis) -> EllipsisExpr:
        return EllipsisExpr()

    # Attribute(expr value, identifier attr, expr_context ctx)
    def visit_Attribute(self, n: Attribute) -> Expression:
        member_expr = MemberExpr(self.visit(n.value), n.attr)
        obj = member_expr.expr
        if (isinstance(obj, CallExpr) and
                isinstance(obj.callee, NameExpr) and
                obj.callee.name == 'super'):
            e = SuperExpr(member_expr.name, obj)  # type: Expression
        else:
            e = member_expr
        return self.set_line(e, n)

    # Subscript(expr value, slice slice, expr_context ctx)
    def visit_Subscript(self, n: ast27.Subscript) -> IndexExpr:
        e = IndexExpr(self.visit(n.value), self.visit(n.slice))
        return self.set_line(e, n)

    # Name(identifier id, expr_context ctx)
    def visit_Name(self, n: Name) -> NameExpr:
        e = NameExpr(n.id)
        return self.set_line(e, n)

    # List(expr* elts, expr_context ctx)
    def visit_List(self, n: ast27.List) -> Union[ListExpr, TupleExpr]:
        expr_list = [self.visit(e) for e in n.elts]  # type: List[Expression]
        if isinstance(n.ctx, ast27.Store):
            # [x, y] = z and (x, y) = z means exactly the same thing
            e = TupleExpr(expr_list)  # type: Union[ListExpr, TupleExpr]
        else:
            e = ListExpr(expr_list)
        return self.set_line(e, n)

    # Tuple(expr* elts, expr_context ctx)
    def visit_Tuple(self, n: ast27_Tuple) -> TupleExpr:
        e = TupleExpr([self.visit(e) for e in n.elts])
        return self.set_line(e, n)

    # --- slice ---

    # Slice(expr? lower, expr? upper, expr? step)
    def visit_Slice(self, n: ast27.Slice) -> SliceExpr:
        return SliceExpr(self.visit(n.lower),
                         self.visit(n.upper),
                         self.visit(n.step))

    # ExtSlice(slice* dims)
    def visit_ExtSlice(self, n: ast27.ExtSlice) -> TupleExpr:
        return TupleExpr(self.translate_expr_list(n.dims))

    # Index(expr value)
    def visit_Index(self, n: ast27.Index) -> Expression:
        return self.visit(n.value)
