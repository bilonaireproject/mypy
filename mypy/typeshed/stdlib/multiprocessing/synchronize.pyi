import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from multiprocessing.context import BaseContext
from types import TracebackType
from typing_extensions import TypeAlias

__all__ = ["Lock", "RLock", "Semaphore", "BoundedSemaphore", "Condition", "Event"]

_LockLike: TypeAlias = Lock | RLock

class Barrier(threading.Barrier):
    def __init__(
        self, parties: int, action: Callable[[], object] | None = None, timeout: float | None = None, *ctx: BaseContext
    ) -> None: ...

class BoundedSemaphore(Semaphore):
    def __init__(self, value: int = 1, *, ctx: BaseContext) -> None: ...

class Condition(AbstractContextManager[bool]):
    def __init__(self, lock: _LockLike | None = None, *, ctx: BaseContext) -> None: ...
    def notify(self, n: int = 1) -> None: ...
    def notify_all(self) -> None: ...
    def wait(self, timeout: float | None = None) -> bool: ...
    def wait_for(self, predicate: Callable[[], bool], timeout: float | None = None) -> bool: ...
    def acquire(self, block: bool = ..., timeout: float | None = ...) -> bool: ...
    def release(self) -> None: ...
    def __exit__(
        self, __exc_type: type[BaseException] | None, __exc_val: BaseException | None, __exc_tb: TracebackType | None
    ) -> None: ...

class Event:
    def __init__(self, lock: _LockLike | None = ..., *, ctx: BaseContext) -> None: ...
    def is_set(self) -> bool: ...
    def set(self) -> None: ...
    def clear(self) -> None: ...
    def wait(self, timeout: float | None = None) -> bool: ...

class Lock(SemLock):
    def __init__(self, *, ctx: BaseContext) -> None: ...

class RLock(SemLock):
    def __init__(self, *, ctx: BaseContext) -> None: ...

class Semaphore(SemLock):
    def __init__(self, value: int = 1, *, ctx: BaseContext) -> None: ...

# Not part of public API
class SemLock(AbstractContextManager[bool]):
    def acquire(self, block: bool = ..., timeout: float | None = ...) -> bool: ...
    def release(self) -> None: ...
    def __exit__(
        self, __exc_type: type[BaseException] | None, __exc_val: BaseException | None, __exc_tb: TracebackType | None
    ) -> None: ...
