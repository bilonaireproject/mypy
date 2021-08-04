import sys
from typing import IO, Optional, Union

def b64encode(s: bytes, altchars: Optional[bytes] = ...) -> bytes: ...
def b64decode(s: Union[str, bytes], altchars: Optional[bytes] = ..., validate: bool = ...) -> bytes: ...
def standard_b64encode(s: bytes) -> bytes: ...
def standard_b64decode(s: Union[str, bytes]) -> bytes: ...
def urlsafe_b64encode(s: bytes) -> bytes: ...
def urlsafe_b64decode(s: Union[str, bytes]) -> bytes: ...
def b32encode(s: bytes) -> bytes: ...
def b32decode(s: Union[str, bytes], casefold: bool = ..., map01: Optional[bytes] = ...) -> bytes: ...
def b16encode(s: bytes) -> bytes: ...
def b16decode(s: Union[str, bytes], casefold: bool = ...) -> bytes: ...

if sys.version_info >= (3, 10):
    def b32hexencode(s: bytes) -> bytes: ...
    def b32hexdecode(s: Union[str, bytes], casefold: bool = ...) -> bytes: ...

def a85encode(b: bytes, *, foldspaces: bool = ..., wrapcol: int = ..., pad: bool = ..., adobe: bool = ...) -> bytes: ...
def a85decode(
    b: Union[str, bytes], *, foldspaces: bool = ..., adobe: bool = ..., ignorechars: Union[str, bytes] = ...
) -> bytes: ...
def b85encode(b: bytes, pad: bool = ...) -> bytes: ...
def b85decode(b: Union[str, bytes]) -> bytes: ...
def decode(input: IO[bytes], output: IO[bytes]) -> None: ...
def encode(input: IO[bytes], output: IO[bytes]) -> None: ...
def encodebytes(s: bytes) -> bytes: ...
def decodebytes(s: bytes) -> bytes: ...

if sys.version_info < (3, 9):
    def encodestring(s: bytes) -> bytes: ...
    def decodestring(s: bytes) -> bytes: ...
