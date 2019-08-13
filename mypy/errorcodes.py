"""Classification of possible errors mypy can detect.

These can be used for filtering specific errors.
"""

from typing import List
from typing_extensions import Final


# All created error codes are implicitly stored in this list.
all_error_codes = []  # type: List[ErrorCode]


class ErrorCode:
    def __init__(self, code: str, description: str, category: str) -> None:
        self.code = code
        self.description = description
        self.category = category

    def __str__(self) -> str:
        return '<ErrorCode {}>'.format(self.code)


ATTR_DEFINED = ErrorCode(
    'attr-defined', "Check that attribute exists", 'General')  # type: Final
NAME_DEFINED = ErrorCode(
    'name-defined', "Check that name is defined", 'General')  # type: Final
CALL_ARG = ErrorCode(
    'call-arg', "Check number, names and kinds of arguments in calls", 'General')  # type: Final
ARG_TYPE = ErrorCode(
    'arg-type', "Check argument types in calls", 'General')  # type: Final
CALL_OVERLOAD = ErrorCode(
    'call-overload', "Check that an overload variant matches arguments", 'General')  # type: Final
VALID_TYPE = ErrorCode(
    'valid-type', "Check that type (annotation) is valid", 'General')  # type: Final
VAR_ANNOTATED = ErrorCode(
    'var-annotated', "Require variable annotation if type can't be inferred",
    'General')  # type: Final
OVERRIDE = ErrorCode(
    'override', "Check that method override is compatible with base class",
    'General')  # type: Final
RETURN = ErrorCode(
    'return', "Check that function always returns a value", 'General')  # type: Final
RETURN_VALUE = ErrorCode(
    'return-value', "Check that return value is compatible with signature",
    'General')  # type: Final
ASSIGNMENT = ErrorCode(
    'assignment', "Check that assigned value is compatible with target", 'General')  # type: Final
TYPE_ARG = ErrorCode(
    'type-arg', "Check that generic type arguments are present", 'General')  # type: Final
TYPE_VAR = ErrorCode(
    'type-var', "Check that type variable values are valid", 'General')  # type: Final
UNION_ATTR = ErrorCode(
    'union-attr', "Check that attribute exists in each item of a union", 'General')  # type: Final
INDEX = ErrorCode(
    'index', "Check indexing operations", 'General')  # type: Final
OPERATOR = ErrorCode(
    'operator', "Check that operator is valid for operands", 'General')  # type: Final
LIST_ITEM = ErrorCode(
    'list-item', "Check list items in [item, ...]", 'General')  # type: Final
DICT_ITEM = ErrorCode(
    'dict-item', "Check dict items in {key: value, ...}", 'General')  # type: Final
TYPEDDICT_ITEM = ErrorCode(
    'typeddict-item', "Check items when constructing TypedDict", 'General')  # type: Final
HAS_TYPE = ErrorCode(
    'has-type', "Check that type of reference can be determined", 'General')  # type: Final
IMPORT = ErrorCode(
    'import', "Require that imported module can be found or has stubs", 'General')  # type: Final
NO_REDEF = ErrorCode(
    'no-redef', "Check that each name is defined once", 'General')  # type: Final
FUNC_RETURNS_VALUE = ErrorCode(
    'func-returns-value', "Check that called function returns a value in value context",
    'General')  # type: Final
ABSTRACT = ErrorCode(
    'abstract', "Prevent instantiation of classes with abstract attributes",
    'General')  # type: Final
VALID_NEWTYPE = ErrorCode(
    'valid-newtype', "Check that argument 2 to NewType is valid", 'General')  # type: Final

NO_UNTYPED_DEF = ErrorCode(
    'no-untyped-def', "Check that every function has an annotation", 'General')  # type: Final
NO_UNTYPED_CALL = ErrorCode(
    'no-untyped-call',
    "Disallow calling functions without type annotations from annotated functions",
    'General')  # type: Final
REDUNDANT_CAST = ErrorCode(
    'redundant-cast', "Check that cast changes type of expression", 'General')  # type: Final
COMPARISON_OVERLAP = ErrorCode(
    'comparison-overlap',
    "Check that types in comparisons have overlap", 'General')  # type: Final
NO_ANY_UNIMPORTED = ErrorCode(
    'no-any-unimported', 'Reject "Any" types from unfollowed imports', 'General')  # type: Final

SYNTAX = ErrorCode(
    'syntax', "Report syntax errors", 'General')  # type: Final

MISC = ErrorCode(
    'misc', "Miscenallenous other checks", 'General')  # type: Final
