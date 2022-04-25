from _typeshed import Self
from typing import IO, Any, Text

def split(s: str | None, comments: bool = ..., posix: bool = ...) -> list[str]: ...

class shlex:
    def __init__(self, instream: IO[Any] | Text = ..., infile: IO[Any] = ..., posix: bool = ...) -> None: ...
    def __iter__(self: Self) -> Self: ...
    def next(self) -> str: ...
    def get_token(self) -> str | None: ...
    def push_token(self, _str: str) -> None: ...
    def read_token(self) -> str: ...
    def sourcehook(self, filename: str) -> None: ...
    def push_source(self, stream: IO[Any], filename: str = ...) -> None: ...
    def pop_source(self) -> IO[Any]: ...
    def error_leader(self, file: str = ..., line: int = ...) -> str: ...
    commenters: str
    wordchars: str
    whitespace: str
    escape: str
    quotes: str
    escapedquotes: str
    whitespace_split: bool
    infile: IO[Any]
    source: str | None
    debug: int
    lineno: int
    token: Any
    eof: str | None
