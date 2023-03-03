from typing import Generic, TypeVar, Callable, Any, Mapping

_T = TypeVar("_T")

class _SingleDispatchCallable(Generic[_T]):
    registry: Mapping[Any, Callable[..., _T]]
    def dispatch(self, cls: Any) -> Callable[..., _T]: ...
    # @fun.register(complex)
    # def _(arg, verbose=False): ...
    @overload
    def register(self, cls: type[Any], func: None = ...) -> Callable[[Callable[..., _T]], Callable[..., _T]]: ...
    # @fun.register
    # def _(arg: int, verbose=False):
    @overload
    def register(self, cls: Callable[..., _T], func: None = ...) -> Callable[..., _T]: ...
    # fun.register(int, lambda x: x)
    @overload
    def register(self, cls: type[Any], func: Callable[..., _T]) -> Callable[..., _T]: ...
    def _clear_cache(self) -> None: ...
    def __call__(__self, *args: Any, **kwargs: Any) -> _T: ...

def singledispatch(func: Callable[..., _T]) -> _SingleDispatchCallable[_T]: ...

def total_ordering(cls: type[_T]) -> type[_T]: ...

class cached_property(Generic[_T]):
    func: Callable[[Any], _T]
    attrname: str | None
    def __init__(self, func: Callable[[Any], _T]) -> None: ...
    @overload
    def __get__(self, instance: None, owner: type[Any] | None = ...) -> cached_property[_T]: ...
    @overload
    def __get__(self, instance: object, owner: type[Any] | None = ...) -> _T: ...
    def __set_name__(self, owner: type[Any], name: str) -> None: ...
    def __class_getitem__(cls, item: Any) -> Any: ...
