"""Integer primitive ops.

These mostly operate on (usually) unboxed integers that use a tagged pointer
representation (CPyTagged).

See also the documentation for mypyc.rtypes.int_rprimitive.
"""

from mypyc.ir.ops import ERR_NEVER, ERR_MAGIC
from mypyc.ir.rtypes import (
    int_rprimitive, bool_rprimitive, float_rprimitive, object_rprimitive, short_int_rprimitive,
    str_rprimitive, RType
)
from mypyc.primitives.registry import (
    name_ref_op, binary_op, custom_op, simple_emit, call_emit, name_emit,
    c_unary_op, CFunctionDescription, c_function_op
)

# These int constructors produce object_rprimitives that then need to be unboxed
# I guess unboxing ourselves would save a check and branch though?

# Get the type object for 'builtins.int'.
# For ordinary calls to int() we use a name_ref to the type
name_ref_op('builtins.int',
            result_type=object_rprimitive,
            error_kind=ERR_NEVER,
            emit=name_emit('&PyLong_Type', target_type='PyObject *'),
            is_borrowed=True)

# Convert from a float to int. We could do a bit better directly.
c_function_op(
    name='builtins.int',
    arg_types=[float_rprimitive],
    return_type=object_rprimitive,
    c_function_name='CPyLong_FromFloat',
    error_kind=ERR_MAGIC)

# int(string)
c_function_op(
    name='builtins.int',
    arg_types=[str_rprimitive],
    return_type=object_rprimitive,
    c_function_name='CPyLong_FromStr',
    error_kind=ERR_MAGIC)

# int(string, base)
c_function_op(
    name='builtins.int',
    arg_types=[str_rprimitive, int_rprimitive],
    return_type=object_rprimitive,
    c_function_name='CPyLong_FromStrWithBase',
    error_kind=ERR_MAGIC)

# str(n) on ints
c_function_op(
    name='builtins.str',
    arg_types=[int_rprimitive],
    return_type=str_rprimitive,
    c_function_name='CPyTagged_Str',
    error_kind=ERR_MAGIC,
    var_arg_type=None,
    steals=False,
    priority=2)

# We need a specialization for str on bools also since the int one is wrong...
c_function_op(
    name='builtins.str',
    arg_types=[bool_rprimitive],
    return_type=str_rprimitive,
    c_function_name='CPyBool_Str',
    error_kind=ERR_MAGIC,
    var_arg_type=None,
    steals=False,
    priority=3)


def int_binary_op(op: str, c_func_name: str,
                  result_type: RType = int_rprimitive,
                  error_kind: int = ERR_NEVER) -> None:
    binary_op(op=op,
              arg_types=[int_rprimitive, int_rprimitive],
              result_type=result_type,
              error_kind=error_kind,
              format_str='{dest} = {args[0]} %s {args[1]} :: int' % op,
              emit=call_emit(c_func_name))


def int_compare_op(op: str, c_func_name: str) -> None:
    int_binary_op(op, c_func_name, bool_rprimitive)
    # Generate a straight compare if we know both sides are short
    binary_op(op=op,
              arg_types=[short_int_rprimitive, short_int_rprimitive],
              result_type=bool_rprimitive,
              error_kind=ERR_NEVER,
              format_str='{dest} = {args[0]} %s {args[1]} :: short_int' % op,
              emit=simple_emit(
                  '{dest} = (Py_ssize_t){args[0]} %s (Py_ssize_t){args[1]};' % op),
              priority=2)


# Binary, unary and augmented assignment operations that operate on CPyTagged ints.

int_binary_op('+', 'CPyTagged_Add')
int_binary_op('-', 'CPyTagged_Subtract')
int_binary_op('*', 'CPyTagged_Multiply')
# Divide and remainder we honestly propagate errors from because they
# can raise ZeroDivisionError
int_binary_op('//', 'CPyTagged_FloorDivide', error_kind=ERR_MAGIC)
int_binary_op('%', 'CPyTagged_Remainder', error_kind=ERR_MAGIC)

# This should work because assignment operators are parsed differently
# and the code in irbuild that handles it does the assignment
# regardless of whether or not the operator works in place anyway.
int_binary_op('+=', 'CPyTagged_Add')
int_binary_op('-=', 'CPyTagged_Subtract')
int_binary_op('*=', 'CPyTagged_Multiply')
int_binary_op('//=', 'CPyTagged_FloorDivide', error_kind=ERR_MAGIC)
int_binary_op('%=', 'CPyTagged_Remainder', error_kind=ERR_MAGIC)

int_compare_op('==', 'CPyTagged_IsEq')
int_compare_op('!=', 'CPyTagged_IsNe')
int_compare_op('<', 'CPyTagged_IsLt')
int_compare_op('<=', 'CPyTagged_IsLe')
int_compare_op('>', 'CPyTagged_IsGt')
int_compare_op('>=', 'CPyTagged_IsGe')

# Add short integers and assume that it doesn't overflow or underflow.
# Assume that the operands are not big integers.
unsafe_short_add = custom_op(
    arg_types=[int_rprimitive, int_rprimitive],
    result_type=short_int_rprimitive,
    error_kind=ERR_NEVER,
    format_str='{dest} = {args[0]} + {args[1]} :: short_int',
    emit=simple_emit('{dest} = {args[0]} + {args[1]};'))


def int_unary_op(name: str, c_function_name: str) -> CFunctionDescription:
    return c_unary_op(name=name,
                      arg_type=int_rprimitive,
                      return_type=int_rprimitive,
                      c_function_name=c_function_name,
                      error_kind=ERR_NEVER)


int_neg_op = int_unary_op('-', 'CPyTagged_Negate')
