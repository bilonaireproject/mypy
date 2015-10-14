# Stubs for yaml (Python 2)
#
# NOTE: This dynamically typed stub was automatically generated by stubgen.

from typing import Any
#from yaml.error import *
#from yaml.tokens import *
#from yaml.events import *
#from yaml.nodes import *
from yaml.loader import *
#from yaml.dumper import *
# TODO: stubs for cyaml?
# from cyaml import *

__with_libyaml__ = ... # type: Any

def scan(stream, Loader=...): ...
def parse(stream, Loader=...): ...
def compose(stream, Loader=...): ...
def compose_all(stream, Loader=...): ...
def load(stream, Loader=...): ...
def load_all(stream, Loader=...): ...
def safe_load(stream): ...
def safe_load_all(stream): ...
def emit(events, stream=None, Dumper=..., canonical=None, indent=None, width=None, allow_unicode=None, line_break=None): ...
def serialize_all(nodes, stream=None, Dumper=..., canonical=None, indent=None, width=None, allow_unicode=None, line_break=None, encoding='', explicit_start=None, explicit_end=None, version=None, tags=None): ...
def serialize(node, stream=None, Dumper=..., **kwds): ...
def dump_all(documents, stream=None, Dumper=..., default_style=None, default_flow_style=None, canonical=None, indent=None, width=None, allow_unicode=None, line_break=None, encoding='', explicit_start=None, explicit_end=None, version=None, tags=None): ...
def dump(data, stream=None, Dumper=..., **kwds): ...
def safe_dump_all(documents, stream=None, **kwds): ...
def safe_dump(data, stream=None, **kwds): ...
def add_implicit_resolver(tag, regexp, first=None, Loader=..., Dumper=...): ...
def add_path_resolver(tag, path, kind=None, Loader=..., Dumper=...): ...
def add_constructor(tag, constructor, Loader=...): ...
def add_multi_constructor(tag_prefix, multi_constructor, Loader=...): ...
def add_representer(data_type, representer, Dumper=...): ...
def add_multi_representer(data_type, multi_representer, Dumper=...): ...

class YAMLObjectMetaclass(type):
    def __init__(cls, name, bases, kwds): ...

class YAMLObject:
    __metaclass__ = ... # type: Any
    yaml_loader = ... # type: Any
    yaml_dumper = ... # type: Any
    yaml_tag = ... # type: Any
    yaml_flow_style = ... # type: Any
    @classmethod
    def from_yaml(cls, loader, node): ...
    @classmethod
    def to_yaml(cls, dumper, data): ...
