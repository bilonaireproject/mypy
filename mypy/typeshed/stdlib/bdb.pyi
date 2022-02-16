from types import CodeType, FrameType, TracebackType
from typing import IO, Any, Callable, Iterable, Mapping, SupportsInt, Type, TypeVar

_T = TypeVar("_T")
_TraceDispatch = Callable[[FrameType, str, Any], Any]  # TODO: Recursive type
_ExcInfo = tuple[Type[BaseException], BaseException, FrameType]

GENERATOR_AND_COROUTINE_FLAGS: int

class BdbQuit(Exception): ...

class Bdb:

    skip: set[str] | None
    breaks: dict[str, list[int]]
    fncache: dict[str, str]
    frame_returning: FrameType | None
    botframe: FrameType | None
    quitting: bool
    stopframe: FrameType | None
    returnframe: FrameType | None
    stoplineno: int
    def __init__(self, skip: Iterable[str] | None = ...) -> None: ...
    def canonic(self, filename: str) -> str: ...
    def reset(self) -> None: ...
    def trace_dispatch(self, frame: FrameType, event: str, arg: Any) -> _TraceDispatch: ...
    def dispatch_line(self, frame: FrameType) -> _TraceDispatch: ...
    def dispatch_call(self, frame: FrameType, arg: None) -> _TraceDispatch: ...
    def dispatch_return(self, frame: FrameType, arg: Any) -> _TraceDispatch: ...
    def dispatch_exception(self, frame: FrameType, arg: _ExcInfo) -> _TraceDispatch: ...
    def is_skipped_module(self, module_name: str) -> bool: ...
    def stop_here(self, frame: FrameType) -> bool: ...
    def break_here(self, frame: FrameType) -> bool: ...
    def do_clear(self, arg: Any) -> bool | None: ...
    def break_anywhere(self, frame: FrameType) -> bool: ...
    def user_call(self, frame: FrameType, argument_list: None) -> None: ...
    def user_line(self, frame: FrameType) -> None: ...
    def user_return(self, frame: FrameType, return_value: Any) -> None: ...
    def user_exception(self, frame: FrameType, exc_info: _ExcInfo) -> None: ...
    def set_until(self, frame: FrameType, lineno: int | None = ...) -> None: ...
    def set_step(self) -> None: ...
    def set_next(self, frame: FrameType) -> None: ...
    def set_return(self, frame: FrameType) -> None: ...
    def set_trace(self, frame: FrameType | None = ...) -> None: ...
    def set_continue(self) -> None: ...
    def set_quit(self) -> None: ...
    def set_break(
        self, filename: str, lineno: int, temporary: bool = ..., cond: str | None = ..., funcname: str | None = ...
    ) -> None: ...
    def clear_break(self, filename: str, lineno: int) -> None: ...
    def clear_bpbynumber(self, arg: SupportsInt) -> None: ...
    def clear_all_file_breaks(self, filename: str) -> None: ...
    def clear_all_breaks(self) -> None: ...
    def get_bpbynumber(self, arg: SupportsInt) -> Breakpoint: ...
    def get_break(self, filename: str, lineno: int) -> bool: ...
    def get_breaks(self, filename: str, lineno: int) -> list[Breakpoint]: ...
    def get_file_breaks(self, filename: str) -> list[Breakpoint]: ...
    def get_all_breaks(self) -> list[Breakpoint]: ...
    def get_stack(self, f: FrameType | None, t: TracebackType | None) -> tuple[list[tuple[FrameType, int]], int]: ...
    def format_stack_entry(self, frame_lineno: int, lprefix: str = ...) -> str: ...
    def run(self, cmd: str | CodeType, globals: dict[str, Any] | None = ..., locals: Mapping[str, Any] | None = ...) -> None: ...
    def runeval(self, expr: str, globals: dict[str, Any] | None = ..., locals: Mapping[str, Any] | None = ...) -> None: ...
    def runctx(self, cmd: str | CodeType, globals: dict[str, Any] | None, locals: Mapping[str, Any] | None) -> None: ...
    def runcall(self, __func: Callable[..., _T], *args: Any, **kwds: Any) -> _T | None: ...

class Breakpoint:

    next: int
    bplist: dict[tuple[str, int], list[Breakpoint]]
    bpbynumber: list[Breakpoint | None]

    funcname: str | None
    func_first_executable_line: int | None
    file: str
    line: int
    temporary: bool
    cond: str | None
    enabled: bool
    ignore: int
    hits: int
    number: int
    def __init__(
        self, file: str, line: int, temporary: bool = ..., cond: str | None = ..., funcname: str | None = ...
    ) -> None: ...
    def deleteMe(self) -> None: ...
    def enable(self) -> None: ...
    def disable(self) -> None: ...
    def bpprint(self, out: IO[str] | None = ...) -> None: ...
    def bpformat(self) -> str: ...
    def __str__(self) -> str: ...

def checkfuncname(b: Breakpoint, frame: FrameType) -> bool: ...
def effective(file: str, line: int, frame: FrameType) -> tuple[Breakpoint, bool] | tuple[None, None]: ...
def set_trace() -> None: ...
