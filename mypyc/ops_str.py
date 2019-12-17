from typing import List, Callable

from mypyc.ops import (
    object_rprimitive, str_rprimitive, bool_rprimitive, ERR_MAGIC, ERR_NEVER, EmitterInterface,
    RType, int_rprimitive
)
from mypyc.ops_primitive import func_op, binary_op, simple_emit, name_ref_op, method_op


name_ref_op('builtins.str',
            result_type=object_rprimitive,
            error_kind=ERR_NEVER,
            emit=simple_emit('{dest} = (PyObject *)&PyUnicode_Type;'),
            is_borrowed=True)

func_op(name='builtins.str',
        arg_types=[object_rprimitive],
        result_type=str_rprimitive,
        error_kind=ERR_MAGIC,
        emit=simple_emit('{dest} = PyObject_Str({args[0]});'))

binary_op(op='+',
          arg_types=[str_rprimitive, str_rprimitive],
          result_type=str_rprimitive,
          error_kind=ERR_MAGIC,
          emit=simple_emit('{dest} = PyUnicode_Concat({args[0]}, {args[1]});'))

method_op(
    name='join',
    arg_types=[str_rprimitive, object_rprimitive],
    result_type=str_rprimitive,
    error_kind=ERR_MAGIC,
    emit=simple_emit('{dest} = PyUnicode_Join({args[0]}, {args[1]});'))

str_split_types = [str_rprimitive, str_rprimitive]  # type: List[RType]
str_split_formats = ["NULL, -1", "{args[1]}, -1"]  # type: List[str]

for i in range(2):
    method_op(
        name='split',
        arg_types=str_split_types[0:i+1],
        result_type=object_rprimitive,
        error_kind=ERR_MAGIC,
        emit=simple_emit('{dest} = PyUnicode_Split({args[0]}, ' +
                         '{});'.format(str_split_formats[i])))


def emit_str_split(emitter: EmitterInterface, args: List[str], dest: str) -> None:
    temp = emitter.temp_name()
    emitter.emit_declaration('Py_ssize_t %s;' % temp)
    emitter.emit_lines(
        '%s = CPyTagged_ShortAsSsize_t(%s);' % (temp, args[2]),
        '%s = PyUnicode_Split(%s, %s, %s);' % (dest, args[0], args[1], temp))


method_op(
    name='split',
    arg_types=[str_rprimitive, str_rprimitive, int_rprimitive],
    result_type=object_rprimitive,
    error_kind=ERR_MAGIC,
    emit=emit_str_split)

# PyUnicodeAppend makes an effort to reuse the LHS when the refcount
# is 1. This is super dodgy but oh well, the interpreter does it.
binary_op(op='+=',
          arg_types=[str_rprimitive, str_rprimitive],
          steals=[True, False],
          result_type=str_rprimitive,
          error_kind=ERR_MAGIC,
          emit=simple_emit('{dest} = {args[0]}; PyUnicode_Append(&{dest}, {args[1]});'))


def emit_str_compare(comparison: str) -> Callable[[EmitterInterface, List[str], str], None]:
    def emit(emitter: EmitterInterface, args: List[str], dest: str) -> None:
        temp = emitter.temp_name()
        emitter.emit_declaration('int %s;' % temp)
        emitter.emit_lines(
            '%s = PyUnicode_Compare(%s, %s);' % (temp, args[0], args[1]),
            'if (%s == -1 && PyErr_Occurred())' % temp,
            '    %s = 2;' % dest,
            'else',
            '    %s = (%s %s);' % (dest, temp, comparison))

    return emit


binary_op(op='==',
          arg_types=[str_rprimitive, str_rprimitive],
          result_type=bool_rprimitive,
          error_kind=ERR_MAGIC,
          emit=emit_str_compare('== 0'))

binary_op(op='!=',
          arg_types=[str_rprimitive, str_rprimitive],
          result_type=bool_rprimitive,
          error_kind=ERR_MAGIC,
          emit=emit_str_compare('!= 0'))
