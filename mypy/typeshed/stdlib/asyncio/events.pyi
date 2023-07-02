import ssl
import sys
from _typeshed import FileDescriptorLike, ReadableBuffer, StrPath, Unused, WriteableBuffer
from abc import ABCMeta, abstractmethod
from collections.abc import Callable, Coroutine, Generator, Sequence
from contextvars import Context
from socket import AddressFamily, SocketKind, _Address, _RetAddress, socket
from typing import IO, Any, Protocol, TypeVar, overload
from typing_extensions import Literal, Self, TypeAlias

from . import _AwaitableLike, _CoroutineLike
from .base_events import Server
from .futures import Future
from .protocols import BaseProtocol
from .tasks import Task
from .transports import BaseTransport, DatagramTransport, ReadTransport, SubprocessTransport, Transport, WriteTransport
from .unix_events import AbstractChildWatcher

if sys.version_info >= (3, 8):
    __all__ = (
        "AbstractEventLoopPolicy",
        "AbstractEventLoop",
        "AbstractServer",
        "Handle",
        "TimerHandle",
        "get_event_loop_policy",
        "set_event_loop_policy",
        "get_event_loop",
        "set_event_loop",
        "new_event_loop",
        "get_child_watcher",
        "set_child_watcher",
        "_set_running_loop",
        "get_running_loop",
        "_get_running_loop",
    )

else:
    __all__ = (
        "AbstractEventLoopPolicy",
        "AbstractEventLoop",
        "AbstractServer",
        "Handle",
        "TimerHandle",
        "SendfileNotAvailableError",
        "get_event_loop_policy",
        "set_event_loop_policy",
        "get_event_loop",
        "set_event_loop",
        "new_event_loop",
        "get_child_watcher",
        "set_child_watcher",
        "_set_running_loop",
        "get_running_loop",
        "_get_running_loop",
    )

_T = TypeVar("_T")
_ProtocolT = TypeVar("_ProtocolT", bound=BaseProtocol)
_Context: TypeAlias = dict[str, Any]
_ExceptionHandler: TypeAlias = Callable[[AbstractEventLoop, _Context], object]
_ProtocolFactory: TypeAlias = Callable[[], BaseProtocol]
_SSLContext: TypeAlias = bool | None | ssl.SSLContext

class _TaskFactory(Protocol):
    def __call__(
        self, __loop: AbstractEventLoop, __factory: Coroutine[Any, Any, _T] | Generator[Any, None, _T]
    ) -> Future[_T]: ...

class Handle:
    _cancelled: bool
    _args: Sequence[Any]
    def __init__(
        self, callback: Callable[..., object], args: Sequence[Any], loop: AbstractEventLoop, context: Context | None = None
    ) -> None: ...
    def cancel(self) -> None: ...
    def _run(self) -> None: ...
    def cancelled(self) -> bool: ...

class TimerHandle(Handle):
    def __init__(
        self,
        when: float,
        callback: Callable[..., object],
        args: Sequence[Any],
        loop: AbstractEventLoop,
        context: Context | None = None,
    ) -> None: ...
    def when(self) -> float: ...
    def __lt__(self, other: TimerHandle) -> bool: ...
    def __le__(self, other: TimerHandle) -> bool: ...
    def __gt__(self, other: TimerHandle) -> bool: ...
    def __ge__(self, other: TimerHandle) -> bool: ...
    def __eq__(self, other: object) -> bool: ...

class AbstractServer:
    @abstractmethod
    def close(self) -> None: ...
    async def __aenter__(self) -> Self: ...
    async def __aexit__(self, *exc: Unused) -> None: ...
    @abstractmethod
    def get_loop(self) -> AbstractEventLoop: ...
    @abstractmethod
    def is_serving(self) -> bool: ...
    @abstractmethod
    async def start_serving(self) -> None: ...
    @abstractmethod
    async def serve_forever(self) -> None: ...
    @abstractmethod
    async def wait_closed(self) -> None: ...

class AbstractEventLoop:
    slow_callback_duration: float
    @abstractmethod
    def run_forever(self) -> None: ...
    @abstractmethod
    def run_until_complete(self, future: _AwaitableLike[_T]) -> _T: ...
    @abstractmethod
    def stop(self) -> None: ...
    @abstractmethod
    def is_running(self) -> bool: ...
    @abstractmethod
    def is_closed(self) -> bool: ...
    @abstractmethod
    def close(self) -> None: ...
    @abstractmethod
    async def shutdown_asyncgens(self) -> None: ...
    # Methods scheduling callbacks.  All these return Handles.
    if sys.version_info >= (3, 9):  # "context" added in 3.9.10/3.10.2
        @abstractmethod
        def call_soon(self, callback: Callable[..., object], *args: Any, context: Context | None = None) -> Handle: ...
        @abstractmethod
        def call_later(
            self, delay: float, callback: Callable[..., object], *args: Any, context: Context | None = None
        ) -> TimerHandle: ...
        @abstractmethod
        def call_at(
            self, when: float, callback: Callable[..., object], *args: Any, context: Context | None = None
        ) -> TimerHandle: ...
    else:
        @abstractmethod
        def call_soon(self, callback: Callable[..., object], *args: Any) -> Handle: ...
        @abstractmethod
        def call_later(self, delay: float, callback: Callable[..., object], *args: Any) -> TimerHandle: ...
        @abstractmethod
        def call_at(self, when: float, callback: Callable[..., object], *args: Any) -> TimerHandle: ...

    @abstractmethod
    def time(self) -> float: ...
    # Future methods
    @abstractmethod
    def create_future(self) -> Future[Any]: ...
    # Tasks methods
    if sys.version_info >= (3, 11):
        @abstractmethod
        def create_task(
            self, coro: _CoroutineLike[_T], *, name: str | None = None, context: Context | None = None
        ) -> Task[_T]: ...
    elif sys.version_info >= (3, 8):
        @abstractmethod
        def create_task(self, coro: _CoroutineLike[_T], *, name: str | None = None) -> Task[_T]: ...
    else:
        @abstractmethod
        def create_task(self, coro: _CoroutineLike[_T]) -> Task[_T]: ...

    @abstractmethod
    def set_task_factory(self, factory: _TaskFactory | None) -> None: ...
    @abstractmethod
    def get_task_factory(self) -> _TaskFactory | None: ...
    # Methods for interacting with threads
    if sys.version_info >= (3, 9):  # "context" added in 3.9.10/3.10.2
        @abstractmethod
        def call_soon_threadsafe(self, callback: Callable[..., object], *args: Any, context: Context | None = None) -> Handle: ...
    else:
        @abstractmethod
        def call_soon_threadsafe(self, callback: Callable[..., object], *args: Any) -> Handle: ...

    @abstractmethod
    def run_in_executor(self, executor: Any, func: Callable[..., _T], *args: Any) -> Future[_T]: ...
    @abstractmethod
    def set_default_executor(self, executor: Any) -> None: ...
    # Network I/O methods returning Futures.
    @abstractmethod
    async def getaddrinfo(
        self,
        host: bytes | str | None,
        port: bytes | str | int | None,
        *,
        family: int = 0,
        type: int = 0,
        proto: int = 0,
        flags: int = 0,
    ) -> list[tuple[AddressFamily, SocketKind, int, str, tuple[str, int] | tuple[str, int, int, int]]]: ...
    @abstractmethod
    async def getnameinfo(self, sockaddr: tuple[str, int] | tuple[str, int, int, int], flags: int = 0) -> tuple[str, str]: ...
    if sys.version_info >= (3, 11):
        @overload
        @abstractmethod
        async def create_connection(
            self,
            protocol_factory: Callable[[], _ProtocolT],
            host: str = ...,
            port: int = ...,
            *,
            ssl: _SSLContext = None,
            family: int = 0,
            proto: int = 0,
            flags: int = 0,
            sock: None = None,
            local_addr: tuple[str, int] | None = None,
            server_hostname: str | None = None,
            ssl_handshake_timeout: float | None = None,
            ssl_shutdown_timeout: float | None = None,
            happy_eyeballs_delay: float | None = None,
            interleave: int | None = None,
        ) -> tuple[Transport, _ProtocolT]: ...
        @overload
        @abstractmethod
        async def create_connection(
            self,
            protocol_factory: Callable[[], _ProtocolT],
            host: None = None,
            port: None = None,
            *,
            ssl: _SSLContext = None,
            family: int = 0,
            proto: int = 0,
            flags: int = 0,
            sock: socket,
            local_addr: None = None,
            server_hostname: str | None = None,
            ssl_handshake_timeout: float | None = None,
            ssl_shutdown_timeout: float | None = None,
            happy_eyeballs_delay: float | None = None,
            interleave: int | None = None,
        ) -> tuple[Transport, _ProtocolT]: ...
    elif sys.version_info >= (3, 8):
        @overload
        @abstractmethod
        async def create_connection(
            self,
            protocol_factory: Callable[[], _ProtocolT],
            host: str = ...,
            port: int = ...,
            *,
            ssl: _SSLContext = None,
            family: int = 0,
            proto: int = 0,
            flags: int = 0,
            sock: None = None,
            local_addr: tuple[str, int] | None = None,
            server_hostname: str | None = None,
            ssl_handshake_timeout: float | None = None,
            happy_eyeballs_delay: float | None = None,
            interleave: int | None = None,
        ) -> tuple[Transport, _ProtocolT]: ...
        @overload
        @abstractmethod
        async def create_connection(
            self,
            protocol_factory: Callable[[], _ProtocolT],
            host: None = None,
            port: None = None,
            *,
            ssl: _SSLContext = None,
            family: int = 0,
            proto: int = 0,
            flags: int = 0,
            sock: socket,
            local_addr: None = None,
            server_hostname: str | None = None,
            ssl_handshake_timeout: float | None = None,
            happy_eyeballs_delay: float | None = None,
            interleave: int | None = None,
        ) -> tuple[Transport, _ProtocolT]: ...
    else:
        @overload
        @abstractmethod
        async def create_connection(
            self,
            protocol_factory: Callable[[], _ProtocolT],
            host: str = ...,
            port: int = ...,
            *,
            ssl: _SSLContext = None,
            family: int = 0,
            proto: int = 0,
            flags: int = 0,
            sock: None = None,
            local_addr: tuple[str, int] | None = None,
            server_hostname: str | None = None,
            ssl_handshake_timeout: float | None = None,
        ) -> tuple[Transport, _ProtocolT]: ...
        @overload
        @abstractmethod
        async def create_connection(
            self,
            protocol_factory: Callable[[], _ProtocolT],
            host: None = None,
            port: None = None,
            *,
            ssl: _SSLContext = None,
            family: int = 0,
            proto: int = 0,
            flags: int = 0,
            sock: socket,
            local_addr: None = None,
            server_hostname: str | None = None,
            ssl_handshake_timeout: float | None = None,
        ) -> tuple[Transport, _ProtocolT]: ...
    if sys.version_info >= (3, 11):
        @overload
        @abstractmethod
        async def create_server(
            self,
            protocol_factory: _ProtocolFactory,
            host: str | Sequence[str] | None = None,
            port: int = ...,
            *,
            family: int = ...,
            flags: int = ...,
            sock: None = None,
            backlog: int = 100,
            ssl: _SSLContext = None,
            reuse_address: bool | None = None,
            reuse_port: bool | None = None,
            ssl_handshake_timeout: float | None = None,
            ssl_shutdown_timeout: float | None = None,
            start_serving: bool = True,
        ) -> Server: ...
        @overload
        @abstractmethod
        async def create_server(
            self,
            protocol_factory: _ProtocolFactory,
            host: None = None,
            port: None = None,
            *,
            family: int = ...,
            flags: int = ...,
            sock: socket = ...,
            backlog: int = 100,
            ssl: _SSLContext = None,
            reuse_address: bool | None = None,
            reuse_port: bool | None = None,
            ssl_handshake_timeout: float | None = None,
            ssl_shutdown_timeout: float | None = None,
            start_serving: bool = True,
        ) -> Server: ...
        @abstractmethod
        async def start_tls(
            self,
            transport: WriteTransport,
            protocol: BaseProtocol,
            sslcontext: ssl.SSLContext,
            *,
            server_side: bool = False,
            server_hostname: str | None = None,
            ssl_handshake_timeout: float | None = None,
            ssl_shutdown_timeout: float | None = None,
        ) -> Transport: ...
        async def create_unix_server(
            self,
            protocol_factory: _ProtocolFactory,
            path: StrPath | None = None,
            *,
            sock: socket | None = None,
            backlog: int = 100,
            ssl: _SSLContext = None,
            ssl_handshake_timeout: float | None = None,
            ssl_shutdown_timeout: float | None = None,
            start_serving: bool = True,
        ) -> Server: ...
    else:
        @overload
        @abstractmethod
        async def create_server(
            self,
            protocol_factory: _ProtocolFactory,
            host: str | Sequence[str] | None = None,
            port: int = ...,
            *,
            family: int = ...,
            flags: int = ...,
            sock: None = None,
            backlog: int = 100,
            ssl: _SSLContext = None,
            reuse_address: bool | None = None,
            reuse_port: bool | None = None,
            ssl_handshake_timeout: float | None = None,
            start_serving: bool = True,
        ) -> Server: ...
        @overload
        @abstractmethod
        async def create_server(
            self,
            protocol_factory: _ProtocolFactory,
            host: None = None,
            port: None = None,
            *,
            family: int = ...,
            flags: int = ...,
            sock: socket = ...,
            backlog: int = 100,
            ssl: _SSLContext = None,
            reuse_address: bool | None = None,
            reuse_port: bool | None = None,
            ssl_handshake_timeout: float | None = None,
            start_serving: bool = True,
        ) -> Server: ...
        @abstractmethod
        async def start_tls(
            self,
            transport: BaseTransport,
            protocol: BaseProtocol,
            sslcontext: ssl.SSLContext,
            *,
            server_side: bool = False,
            server_hostname: str | None = None,
            ssl_handshake_timeout: float | None = None,
        ) -> Transport: ...
        async def create_unix_server(
            self,
            protocol_factory: _ProtocolFactory,
            path: StrPath | None = None,
            *,
            sock: socket | None = None,
            backlog: int = 100,
            ssl: _SSLContext = None,
            ssl_handshake_timeout: float | None = None,
            start_serving: bool = True,
        ) -> Server: ...
    if sys.version_info >= (3, 11):
        async def connect_accepted_socket(
            self,
            protocol_factory: Callable[[], _ProtocolT],
            sock: socket,
            *,
            ssl: _SSLContext = None,
            ssl_handshake_timeout: float | None = None,
            ssl_shutdown_timeout: float | None = None,
        ) -> tuple[Transport, _ProtocolT]: ...
    elif sys.version_info >= (3, 10):
        async def connect_accepted_socket(
            self,
            protocol_factory: Callable[[], _ProtocolT],
            sock: socket,
            *,
            ssl: _SSLContext = None,
            ssl_handshake_timeout: float | None = None,
        ) -> tuple[Transport, _ProtocolT]: ...
    if sys.version_info >= (3, 11):
        async def create_unix_connection(
            self,
            protocol_factory: Callable[[], _ProtocolT],
            path: str | None = None,
            *,
            ssl: _SSLContext = None,
            sock: socket | None = None,
            server_hostname: str | None = None,
            ssl_handshake_timeout: float | None = None,
            ssl_shutdown_timeout: float | None = None,
        ) -> tuple[Transport, _ProtocolT]: ...
    else:
        async def create_unix_connection(
            self,
            protocol_factory: Callable[[], _ProtocolT],
            path: str | None = None,
            *,
            ssl: _SSLContext = None,
            sock: socket | None = None,
            server_hostname: str | None = None,
            ssl_handshake_timeout: float | None = None,
        ) -> tuple[Transport, _ProtocolT]: ...

    @abstractmethod
    async def sock_sendfile(
        self, sock: socket, file: IO[bytes], offset: int = 0, count: int | None = None, *, fallback: bool | None = None
    ) -> int: ...
    @abstractmethod
    async def sendfile(
        self, transport: WriteTransport, file: IO[bytes], offset: int = 0, count: int | None = None, *, fallback: bool = True
    ) -> int: ...
    @abstractmethod
    async def create_datagram_endpoint(
        self,
        protocol_factory: Callable[[], _ProtocolT],
        local_addr: tuple[str, int] | str | None = None,
        remote_addr: tuple[str, int] | str | None = None,
        *,
        family: int = 0,
        proto: int = 0,
        flags: int = 0,
        reuse_address: bool | None = None,
        reuse_port: bool | None = None,
        allow_broadcast: bool | None = None,
        sock: socket | None = None,
    ) -> tuple[DatagramTransport, _ProtocolT]: ...
    # Pipes and subprocesses.
    @abstractmethod
    async def connect_read_pipe(
        self, protocol_factory: Callable[[], _ProtocolT], pipe: Any
    ) -> tuple[ReadTransport, _ProtocolT]: ...
    @abstractmethod
    async def connect_write_pipe(
        self, protocol_factory: Callable[[], _ProtocolT], pipe: Any
    ) -> tuple[WriteTransport, _ProtocolT]: ...
    @abstractmethod
    async def subprocess_shell(
        self,
        protocol_factory: Callable[[], _ProtocolT],
        cmd: bytes | str,
        *,
        stdin: int | IO[Any] | None = -1,
        stdout: int | IO[Any] | None = -1,
        stderr: int | IO[Any] | None = -1,
        universal_newlines: Literal[False] = False,
        shell: Literal[True] = True,
        bufsize: Literal[0] = 0,
        encoding: None = None,
        errors: None = None,
        text: Literal[False, None] = ...,
        **kwargs: Any,
    ) -> tuple[SubprocessTransport, _ProtocolT]: ...
    @abstractmethod
    async def subprocess_exec(
        self,
        protocol_factory: Callable[[], _ProtocolT],
        program: Any,
        *args: Any,
        stdin: int | IO[Any] | None = -1,
        stdout: int | IO[Any] | None = -1,
        stderr: int | IO[Any] | None = -1,
        universal_newlines: Literal[False] = False,
        shell: Literal[False] = False,
        bufsize: Literal[0] = 0,
        encoding: None = None,
        errors: None = None,
        **kwargs: Any,
    ) -> tuple[SubprocessTransport, _ProtocolT]: ...
    @abstractmethod
    def add_reader(self, fd: FileDescriptorLike, callback: Callable[..., Any], *args: Any) -> None: ...
    @abstractmethod
    def remove_reader(self, fd: FileDescriptorLike) -> bool: ...
    @abstractmethod
    def add_writer(self, fd: FileDescriptorLike, callback: Callable[..., Any], *args: Any) -> None: ...
    @abstractmethod
    def remove_writer(self, fd: FileDescriptorLike) -> bool: ...
    # Completion based I/O methods returning Futures prior to 3.7
    @abstractmethod
    async def sock_recv(self, sock: socket, nbytes: int) -> bytes: ...
    @abstractmethod
    async def sock_recv_into(self, sock: socket, buf: WriteableBuffer) -> int: ...
    @abstractmethod
    async def sock_sendall(self, sock: socket, data: ReadableBuffer) -> None: ...
    @abstractmethod
    async def sock_connect(self, sock: socket, address: _Address) -> None: ...
    @abstractmethod
    async def sock_accept(self, sock: socket) -> tuple[socket, _RetAddress]: ...
    if sys.version_info >= (3, 11):
        @abstractmethod
        async def sock_recvfrom(self, sock: socket, bufsize: int) -> tuple[bytes, _RetAddress]: ...
        @abstractmethod
        async def sock_recvfrom_into(self, sock: socket, buf: WriteableBuffer, nbytes: int = 0) -> tuple[int, _RetAddress]: ...
        @abstractmethod
        async def sock_sendto(self, sock: socket, data: ReadableBuffer, address: _Address) -> int: ...
    # Signal handling.
    @abstractmethod
    def add_signal_handler(self, sig: int, callback: Callable[..., object], *args: Any) -> None: ...
    @abstractmethod
    def remove_signal_handler(self, sig: int) -> bool: ...
    # Error handlers.
    @abstractmethod
    def set_exception_handler(self, handler: _ExceptionHandler | None) -> None: ...
    @abstractmethod
    def get_exception_handler(self) -> _ExceptionHandler | None: ...
    @abstractmethod
    def default_exception_handler(self, context: _Context) -> None: ...
    @abstractmethod
    def call_exception_handler(self, context: _Context) -> None: ...
    # Debug flag management.
    @abstractmethod
    def get_debug(self) -> bool: ...
    @abstractmethod
    def set_debug(self, enabled: bool) -> None: ...
    if sys.version_info >= (3, 9):
        @abstractmethod
        async def shutdown_default_executor(self) -> None: ...

class AbstractEventLoopPolicy:
    @abstractmethod
    def get_event_loop(self) -> AbstractEventLoop: ...
    @abstractmethod
    def set_event_loop(self, loop: AbstractEventLoop | None) -> None: ...
    @abstractmethod
    def new_event_loop(self) -> AbstractEventLoop: ...
    # Child processes handling (Unix only).
    @abstractmethod
    def get_child_watcher(self) -> AbstractChildWatcher: ...
    @abstractmethod
    def set_child_watcher(self, watcher: AbstractChildWatcher) -> None: ...

class BaseDefaultEventLoopPolicy(AbstractEventLoopPolicy, metaclass=ABCMeta):
    def get_event_loop(self) -> AbstractEventLoop: ...
    def set_event_loop(self, loop: AbstractEventLoop | None) -> None: ...
    def new_event_loop(self) -> AbstractEventLoop: ...

def get_event_loop_policy() -> AbstractEventLoopPolicy: ...
def set_event_loop_policy(policy: AbstractEventLoopPolicy | None) -> None: ...
def get_event_loop() -> AbstractEventLoop: ...
def set_event_loop(loop: AbstractEventLoop | None) -> None: ...
def new_event_loop() -> AbstractEventLoop: ...
def get_child_watcher() -> AbstractChildWatcher: ...
def set_child_watcher(watcher: AbstractChildWatcher) -> None: ...
def _set_running_loop(__loop: AbstractEventLoop | None) -> None: ...
def _get_running_loop() -> AbstractEventLoop: ...
def get_running_loop() -> AbstractEventLoop: ...

if sys.version_info < (3, 8):
    class SendfileNotAvailableError(RuntimeError): ...
