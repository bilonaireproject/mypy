"""This file exists as a temporary measure, and will be removed when new
semantic analyzer is the default one.
"""
MYPY = False
if MYPY:
    from typing_extensions import Final

# Files to not run with new semantic analyzer.
new_semanal_blacklist = [
    'check-async-await.test',
    'check-callable.test',
    'check-classes.test',
    'check-custom-plugin.test',
    'check-dataclasses.test',
    'check-default-plugin.test',
    'check-enum.test',
    'check-expressions.test',
    'check-fastparse.test',
    'check-flags.test',
    'check-functions.test',
    'check-incomplete-fixture.test',
    'check-incremental.test',
    'check-inference-context.test',
    'check-isinstance.test',
    'check-literal.test',
    'check-modules.test',
    'check-multiple-inheritance.test',
    'check-newtype.test',
    'check-optional.test',
    'check-overloading.test',
    'check-protocols.test',
    'check-python2.test',
    'check-semanal-error.test',
    'check-serialize.test',
    'check-statements.test',
    'check-typevar-values.test',
    'check-unions.test',
    'check-unreachable-code.test',
    'check-varargs.test',
    'semanal-abstractclasses.test',
    'semanal-basic.test',
    'semanal-modules.test',
    'semanal-classes.test',
    'semanal-classvar.test',
    'semanal-errors.test',
    'semenal-literal.test',
    'semanal-namedtuple.test',
    'semanal-statements.test',
    'semanal-symtable.test',
    'semanal-typealiases.test',
    'semanal-typeinfo.test',
    'semanal-types.test'
]  # type: Final
