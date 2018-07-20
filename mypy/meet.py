from collections import OrderedDict
from typing import List, Optional, Tuple

from mypy.join import is_similar_callables, combine_similar_callables, join_type_list
from mypy.types import (
    Type, AnyType, TypeVisitor, UnboundType, NoneTyp, TypeVarType, Instance, CallableType,
    TupleType, TypedDictType, ErasedType, UnionType, PartialType, DeletedType,
    UninhabitedType, TypeType, TypeOfAny, Overloaded, FunctionLike,
)
from mypy.subtypes import (
    is_equivalent, is_subtype, is_protocol_implementation, is_callable_compatible,
)
from mypy.erasetype import erase_type
from mypy.maptype import map_instance_to_supertype

from mypy import experiments

# TODO Describe this module.


def meet_types(s: Type, t: Type) -> Type:
    """Return the greatest lower bound of two types."""
    if isinstance(s, ErasedType):
        return s
    if isinstance(s, AnyType):
        return t
    if isinstance(s, UnionType) and not isinstance(t, UnionType):
        s, t = t, s
    return t.accept(TypeMeetVisitor(s))


def narrow_declared_type(declared: Type, narrowed: Type) -> Type:
    """Return the declared type narrowed down to another type."""
    if declared == narrowed:
        return declared
    if isinstance(declared, UnionType):
        return UnionType.make_simplified_union([narrow_declared_type(x, narrowed)
                                                for x in declared.relevant_items()])
    elif not is_overlapping_types(declared, narrowed):
        if experiments.STRICT_OPTIONAL:
            return UninhabitedType()
        else:
            return NoneTyp()
    elif isinstance(narrowed, UnionType):
        return UnionType.make_simplified_union([narrow_declared_type(declared, x)
                                                for x in narrowed.relevant_items()])
    elif isinstance(narrowed, AnyType):
        return narrowed
    elif isinstance(declared, (Instance, TupleType)):
        return meet_types(declared, narrowed)
    elif isinstance(declared, TypeType) and isinstance(narrowed, TypeType):
        return TypeType.make_normalized(narrow_declared_type(declared.item, narrowed.item))
    return narrowed


def get_possible_variants(typ: Type) -> List[Type]:
    """This function takes any "Union-like" type and returns a list of the available "options".

    Specifically, there are currently exactly three different types that can have
    "variants" or are "union-like":

    - Unions
    - TypeVars with value restrictions
    - Overloads

    This function will return a list of each "option" present in those types.

    If this function receives any other type, we return a list containing just that
    original type. (E.g. pretend the type was contained within a singleton union).

    The only exception is regular TypeVars: we return a list containing that TypeVar's
    upper bound.

    This function is useful primarily when checking to see if two types are overlapping:
    the algorithm to check if two unions are overlapping is fundamentally the same as
    the algorithm for checking if two overloads are overlapping.

    Normalizing both kinds of types in the same way lets us reuse the same algorithm
    for both.
    """
    if isinstance(typ, TypeVarType):
        if len(typ.values) > 0:
            return typ.values
        else:
            return [typ.upper_bound]
    elif isinstance(typ, UnionType):
        return typ.relevant_items()
    elif isinstance(typ, Overloaded):
        # Note: doing 'return typ.items()' makes mypy
        # infer a too-specific return type of List[CallableType]
        out = []  # type: List[Type]
        out.extend(typ.items())
        return out
    else:
        return [typ]


def is_overlapping_types(left: Type, right: Type, ignore_promotions: bool = False) -> bool:
    """Can a value of type 'left' also be of type 'right' or vice-versa?"""

    def _is_overlapping_types(left: Type, right: Type) -> bool:
        '''Encode the kind of overlapping check to perform.

        This function mostly exists so we don't have to repeat keyword arguments everywhere.'''
        return is_overlapping_types(left, right, ignore_promotions=ignore_promotions)

    # We should never encounter these types, but if we do, we handle
    # them in the same way we handle 'Any'.
    illegal_types = (UnboundType, PartialType, ErasedType, DeletedType)
    if isinstance(left, illegal_types) or isinstance(right, illegal_types):
        # TODO: Replace this with an 'assert False' once we are confident we
        # never accidentally generate these types.
        return True

    # 'Any' may or may not be overlapping with the other type
    if isinstance(left, AnyType) or isinstance(right, AnyType):
        return True

    # We check for complete overlaps first as a general-purpose failsafe.
    # If this check fails, we start checking to see if there exists a
    # *partial* overlap between types.

    if (is_subtype(left, right, ignore_promotions=ignore_promotions)
            or is_subtype(right, left, ignore_promotions=ignore_promotions)):
        return True

    # See the docstring for 'get_possible_variants' for more info on what the
    # following lines are doing.
    #
    # Note that we use 'left_possible' and 'right_possible' in two different
    # locations: immediately after to handle TypeVars, and near the end of
    # 'is_overlapping_types' to handle types like Unions or Overloads.

    left_possible = get_possible_variants(left)
    right_possible = get_possible_variants(right)

    # We start by checking TypeVars first: this is because in some of the checks
    # below, it's convenient to just return early in certain cases.
    #
    # If we were to defer checking TypeVars to down below, that would end up
    # causing issues since the TypeVars would never have the opportunity to
    # try binding to the relevant types.
    if isinstance(left, TypeVarType) or isinstance(right, TypeVarType):
        for l in left_possible:
            for r in right_possible:
                if _is_overlapping_types(l, r):
                    return True
        return False

    # Now that we've finished handling TypeVars, we're free to end early
    # if one one of the types is None and we're running in strict-optional
    # mode. (We must perform this check after the TypeVar checks because
    # a TypeVar could be bound to None, for example.)
    if experiments.STRICT_OPTIONAL:
        if isinstance(left, NoneTyp) != isinstance(right, NoneTyp):
            return False

    # Next, we handle single-variant types that may be inherently partially overlapping:
    #
    # - TypedDicts
    # - Tuples
    #
    # If we cannot identify a partial overlap and end early, we degrade these two types
    # into their 'Instance' fallbacks.

    if isinstance(left, TypedDictType) and isinstance(right, TypedDictType):
        return are_typed_dicts_overlapping(left, right, ignore_promotions=ignore_promotions)
    elif isinstance(left, TypedDictType):
        left = left.fallback
    elif isinstance(right, TypedDictType):
        right = right.fallback

    if is_tuple(left) and is_tuple(right):
        return are_tuples_overlapping(left, right, ignore_promotions=ignore_promotions)
    elif isinstance(left, TupleType):
        left = left.fallback
    elif isinstance(right, TupleType):
        right = right.fallback

    # Next, we handle single-variant types that cannot be inherently partially overlapping,
    # but do require custom logic to inspect.

    if isinstance(left, TypeType) and isinstance(right, TypeType):
        return _is_overlapping_types(left.item, right.item)
    elif isinstance(left, TypeType) or isinstance(right, TypeType):
        # TODO: Can Callable[[...], T] and Type[T] be partially overlapping?
        return False

    if isinstance(left, CallableType) and isinstance(right, CallableType):
        return is_callable_compatible(left, right,
                                      is_compat=_is_overlapping_types,
                                      ignore_pos_arg_names=True,
                                      allow_partial_overlap=True)
    elif isinstance(left, CallableType):
        left = left.fallback
    elif isinstance(right, CallableType):
        right = right.fallback

    # Next, we check if left and right are instances

    if isinstance(left, Instance) and isinstance(right, Instance):
        if left.type.is_protocol and is_protocol_implementation(right, left):
            return True
        if right.type.is_protocol and is_protocol_implementation(left, right):
            return True

        # Two unrelated types cannot be partially overlapping: they're disjoint.
        # We don't need to handle promotions because they've already been handled
        # by the calls to `is_subtype(...)` up above (and promotable types never
        # have any generic arguments we need to recurse on).
        if left.type.has_base(right.type.fullname()):
            left = map_instance_to_supertype(left, right.type)
        elif right.type.has_base(left.type.fullname()):
            right = map_instance_to_supertype(right, left.type)
        else:
            return False

        if len(left.args) == len(right.args):
            for left_arg, right_arg in zip(left.args, right.args):
                if _is_overlapping_types(left_arg, right_arg):
                    return True

        return False

    # We handle all remaining types here: in particular, types like
    # UnionType, Overloaded, NoneTyp, and UninhabitedType.
    #
    # We deliberately skip comparing two singleton variant types to avoid
    # infinitely recursing.

    if len(left_possible) >= 1 or len(right_possible) >= 1:
        for a in left_possible:
            for b in right_possible:
                if _is_overlapping_types(a, b):
                    return True

    # We ought to have handled every case by now: we conclude the
    # two types are not overlapping, either completely or partially.

    return False


def is_overlapping_erased_types(left: Type, right: Type, *,
                                ignore_promotions: bool = False) -> bool:
    """The same as 'is_overlapping_erased_types', except the types are erased first."""
    return is_overlapping_types(erase_type(left), erase_type(right),
                                ignore_promotions=ignore_promotions)


def are_typed_dicts_overlapping(left: TypedDictType, right: TypedDictType, *,
                                ignore_promotions: bool = False) -> bool:
    """Returns 'true' if left and right are overlapping TypeDictTypes."""
    # All required keys in left are present and overlapping with something in right
    for key in left.required_keys:
        if key not in right.items:
            return False
        if not is_overlapping_types(left.items[key], right.items[key],
                                    ignore_promotions=ignore_promotions):
            return False

    # Repeat check in the other direction
    for key in right.required_keys:
        if key not in left.items:
            return False
        if not is_overlapping_types(left.items[key], right.items[key],
                                    ignore_promotions=ignore_promotions):
            return False

    # The presence of any additional optional keys does not affect whether the two
    # TypedDicts are partially overlapping: the dicts would be overlapping if the
    # keys happened to be missing.
    return True


def are_tuples_overlapping(left: Type, right: Type, *,
                           ignore_promotions: bool = False) -> bool:
    """Returns true if left and right are overlapping tuples.

    Precondition: is_tuple(left) and is_tuple(right) are both true."""
    left = adjust_tuple(left, right) or left
    right = adjust_tuple(right, left) or right
    assert isinstance(left, TupleType)
    assert isinstance(right, TupleType)
    if len(left.items) != len(right.items):
        return False
    return all(is_overlapping_types(l, r, ignore_promotions=ignore_promotions)
               for l, r in zip(left.items, right.items))


def adjust_tuple(left: Type, r: Type) -> Optional[TupleType]:
    """Find out if `left` is a Tuple[A, ...], and adjust its length to `right`"""
    if isinstance(left, Instance) and left.type.fullname() == 'builtins.tuple':
        n = r.length() if isinstance(r, TupleType) else 1
        return TupleType([left.args[0]] * n, left)
    return None


def is_tuple(typ: Type) -> bool:
    return (isinstance(typ, TupleType)
            or (isinstance(typ, Instance) and typ.type.fullname() == 'builtins.tuple'))


class TypeMeetVisitor(TypeVisitor[Type]):
    def __init__(self, s: Type) -> None:
        self.s = s

    def visit_unbound_type(self, t: UnboundType) -> Type:
        if isinstance(self.s, NoneTyp):
            if experiments.STRICT_OPTIONAL:
                return AnyType(TypeOfAny.special_form)
            else:
                return self.s
        elif isinstance(self.s, UninhabitedType):
            return self.s
        else:
            return AnyType(TypeOfAny.special_form)

    def visit_any(self, t: AnyType) -> Type:
        return self.s

    def visit_union_type(self, t: UnionType) -> Type:
        if isinstance(self.s, UnionType):
            meets = []  # type: List[Type]
            for x in t.items:
                for y in self.s.items:
                    meets.append(meet_types(x, y))
        else:
            meets = [meet_types(x, self.s)
                     for x in t.items]
        return UnionType.make_simplified_union(meets)

    def visit_none_type(self, t: NoneTyp) -> Type:
        if experiments.STRICT_OPTIONAL:
            if isinstance(self.s, NoneTyp) or (isinstance(self.s, Instance) and
                                               self.s.type.fullname() == 'builtins.object'):
                return t
            else:
                return UninhabitedType()
        else:
            return t

    def visit_uninhabited_type(self, t: UninhabitedType) -> Type:
        return t

    def visit_deleted_type(self, t: DeletedType) -> Type:
        if isinstance(self.s, NoneTyp):
            if experiments.STRICT_OPTIONAL:
                return t
            else:
                return self.s
        elif isinstance(self.s, UninhabitedType):
            return self.s
        else:
            return t

    def visit_erased_type(self, t: ErasedType) -> Type:
        return self.s

    def visit_type_var(self, t: TypeVarType) -> Type:
        if isinstance(self.s, TypeVarType) and self.s.id == t.id:
            return self.s
        else:
            return self.default(self.s)

    def visit_instance(self, t: Instance) -> Type:
        if isinstance(self.s, Instance):
            si = self.s
            if t.type == si.type:
                if is_subtype(t, self.s) or is_subtype(self.s, t):
                    # Combine type arguments. We could have used join below
                    # equivalently.
                    args = []  # type: List[Type]
                    for i in range(len(t.args)):
                        args.append(self.meet(t.args[i], si.args[i]))
                    return Instance(t.type, args)
                else:
                    if experiments.STRICT_OPTIONAL:
                        return UninhabitedType()
                    else:
                        return NoneTyp()
            else:
                if is_subtype(t, self.s):
                    return t
                elif is_subtype(self.s, t):
                    # See also above comment.
                    return self.s
                else:
                    if experiments.STRICT_OPTIONAL:
                        return UninhabitedType()
                    else:
                        return NoneTyp()
        elif isinstance(self.s, TypeType):
            return meet_types(t, self.s)
        elif isinstance(self.s, TupleType):
            return meet_types(t, self.s)
        else:
            return self.default(self.s)

    def visit_callable_type(self, t: CallableType) -> Type:
        if isinstance(self.s, CallableType) and is_similar_callables(t, self.s):
            if is_equivalent(t, self.s):
                return combine_similar_callables(t, self.s)
            result = meet_similar_callables(t, self.s)
            if isinstance(result.ret_type, UninhabitedType):
                # Return a plain None or <uninhabited> instead of a weird function.
                return self.default(self.s)
            return result
        else:
            return self.default(self.s)

    def visit_overloaded(self, t: Overloaded) -> Type:
        # TODO: Implement a better algorithm that covers at least the same cases
        # as TypeJoinVisitor.visit_overloaded().
        s = self.s
        if isinstance(s, FunctionLike):
            if s.items() == t.items():
                return Overloaded(t.items())
            elif is_subtype(s, t):
                return s
            elif is_subtype(t, s):
                return t
            else:
                return meet_types(t.fallback, s.fallback)
        return meet_types(t.fallback, s)

    def visit_tuple_type(self, t: TupleType) -> Type:
        if isinstance(self.s, TupleType) and self.s.length() == t.length():
            items = []  # type: List[Type]
            for i in range(t.length()):
                items.append(self.meet(t.items[i], self.s.items[i]))
            # TODO: What if the fallbacks are different?
            return TupleType(items, t.fallback)
        # meet(Tuple[t1, t2, <...>], Tuple[s, ...]) == Tuple[meet(t1, s), meet(t2, s), <...>].
        elif (isinstance(self.s, Instance) and
              self.s.type.fullname() == 'builtins.tuple' and self.s.args):
            return t.copy_modified(items=[meet_types(it, self.s.args[0]) for it in t.items])
        elif (isinstance(self.s, Instance) and t.fallback.type == self.s.type):
            # Uh oh, a broken named tuple type (https://github.com/python/mypy/issues/3016).
            # Do something reasonable until that bug is fixed.
            return t
        else:
            return self.default(self.s)

    def visit_typeddict_type(self, t: TypedDictType) -> Type:
        if isinstance(self.s, TypedDictType):
            for (name, l, r) in self.s.zip(t):
                if (not is_equivalent(l, r) or
                        (name in t.required_keys) != (name in self.s.required_keys)):
                    return self.default(self.s)
            item_list = []  # type: List[Tuple[str, Type]]
            for (item_name, s_item_type, t_item_type) in self.s.zipall(t):
                if s_item_type is not None:
                    item_list.append((item_name, s_item_type))
                else:
                    # at least one of s_item_type and t_item_type is not None
                    assert t_item_type is not None
                    item_list.append((item_name, t_item_type))
            items = OrderedDict(item_list)
            mapping_value_type = join_type_list(list(items.values()))
            fallback = self.s.create_anonymous_fallback(value_type=mapping_value_type)
            required_keys = t.required_keys | self.s.required_keys
            return TypedDictType(items, required_keys, fallback)
        else:
            return self.default(self.s)

    def visit_partial_type(self, t: PartialType) -> Type:
        # We can't determine the meet of partial types. We should never get here.
        assert False, 'Internal error'

    def visit_type_type(self, t: TypeType) -> Type:
        if isinstance(self.s, TypeType):
            typ = self.meet(t.item, self.s.item)
            if not isinstance(typ, NoneTyp):
                typ = TypeType.make_normalized(typ, line=t.line)
            return typ
        elif isinstance(self.s, Instance) and self.s.type.fullname() == 'builtins.type':
            return t
        else:
            return self.default(self.s)

    def meet(self, s: Type, t: Type) -> Type:
        return meet_types(s, t)

    def default(self, typ: Type) -> Type:
        if isinstance(typ, UnboundType):
            return AnyType(TypeOfAny.special_form)
        else:
            if experiments.STRICT_OPTIONAL:
                return UninhabitedType()
            else:
                return NoneTyp()


def meet_similar_callables(t: CallableType, s: CallableType) -> CallableType:
    from mypy.join import join_types
    arg_types = []  # type: List[Type]
    for i in range(len(t.arg_types)):
        arg_types.append(join_types(t.arg_types[i], s.arg_types[i]))
    # TODO in combine_similar_callables also applies here (names and kinds)
    # The fallback type can be either 'function' or 'type'. The result should have 'function' as
    # fallback only if both operands have it as 'function'.
    if t.fallback.type.fullname() != 'builtins.function':
        fallback = t.fallback
    else:
        fallback = s.fallback
    return t.copy_modified(arg_types=arg_types,
                           ret_type=meet_types(t.ret_type, s.ret_type),
                           fallback=fallback,
                           name=None)
