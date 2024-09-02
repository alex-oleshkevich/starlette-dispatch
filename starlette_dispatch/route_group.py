import functools
import typing

from starlette.middleware import Middleware
from starlette.requests import HTTPConnection, Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route, WebSocketRoute
from starlette.websockets import WebSocket

from starlette_dispatch.injections import create_dependency_specs, resolve_dependencies

ViewCallable = typing.Callable[[Request], typing.Awaitable[Response]]
WebSocketViewCallable = typing.Callable[[WebSocket], typing.Awaitable[None]]
HttpMethod = str

_PS = typing.ParamSpec("_PS")
_RT = typing.TypeVar("_RT")


def unwrap_callable(
    fn: typing.Callable[..., typing.Awaitable[Response]],
) -> typing.Callable[..., typing.Awaitable[Response]]:
    return fn if not hasattr(fn, "__wrapped__") else unwrap_callable(fn.__wrapped__)


def unwrap_websocket_callable(
    fn: typing.Callable[..., typing.Awaitable[None]],
) -> typing.Callable[..., typing.Awaitable[None]]:
    callback = fn if not hasattr(fn, "__wrapped__") else unwrap_callable(fn.__wrapped__)
    return typing.cast(typing.Callable[..., typing.Awaitable[None]], callback)


class RouteGroup(typing.Sequence[BaseRoute]):
    def __init__(self, prefix: str | None = None) -> None:
        self.prefix = prefix or ""
        self.routes: list[BaseRoute] = []

    def add(
        self,
        path: str,
        *,
        methods: list[HttpMethod] | None = None,
        name: str | None = None,
        middleware: typing.Sequence[Middleware] | None = None,
    ) -> typing.Callable[[typing.Callable[..., typing.Awaitable[Response]]], ViewCallable]:
        path = self.prefix.removesuffix("/") + path if self.prefix else path

        def decorator(view_callable: typing.Callable[..., typing.Awaitable[Response]]) -> ViewCallable:
            unwrapped_view_callable: typing.Callable[..., typing.Awaitable[Response]] = unwrap_callable(view_callable)
            resolvers = create_dependency_specs(unwrapped_view_callable)

            @functools.wraps(unwrapped_view_callable)
            async def endpoint(request: Request) -> Response:
                dependencies = await resolve_dependencies(
                    resolvers,
                    prepared_resolvers={
                        Request: request,
                        HTTPConnection: request,
                    },
                )
                return await unwrapped_view_callable(**dependencies)

            self.routes.append(Route(path, endpoint, name=name, methods=methods, middleware=middleware))
            return endpoint

        return decorator

    def get(
        self, path: str, *, name: str | None = None, middleware: typing.Sequence[Middleware] | None = None
    ) -> typing.Callable[[typing.Callable[..., typing.Awaitable[Response]]], ViewCallable]:
        return self.add(path, methods=["GET"], name=name, middleware=middleware)

    def post(
        self, path: str, *, name: str | None = None, middleware: typing.Sequence[Middleware] | None = None
    ) -> typing.Callable[[ViewCallable], ViewCallable]:
        return self.add(path, methods=["POST"], name=name, middleware=middleware)

    def get_or_post(
        self, path: str, *, name: str | None = None, middleware: typing.Sequence[Middleware] | None = None
    ) -> typing.Callable[[ViewCallable], ViewCallable]:
        return self.add(path, methods=["GET", "POST"], name=name, middleware=middleware)

    def put(
        self, path: str, *, name: str | None = None, middleware: typing.Sequence[Middleware] | None = None
    ) -> typing.Callable[[ViewCallable], ViewCallable]:
        return self.add(path, methods=["PUT"], name=name, middleware=middleware)

    def patch(
        self, path: str, *, name: str | None = None, middleware: typing.Sequence[Middleware] | None = None
    ) -> typing.Callable[[ViewCallable], ViewCallable]:
        return self.add(path, methods=["PATCH"], name=name, middleware=middleware)

    def delete(
        self, path: str, *, name: str | None = None, middleware: typing.Sequence[Middleware] | None = None
    ) -> typing.Callable[[ViewCallable], ViewCallable]:
        return self.add(path, methods=["DELETE"], name=name, middleware=middleware)

    def websocket(
        self, path: str, *, name: str | None = None, middleware: typing.Sequence[Middleware] | None = None
    ) -> typing.Callable[[typing.Callable[_PS, typing.Awaitable[None]]], WebSocketViewCallable]:
        path = self.prefix.removesuffix("/") + path if self.prefix else path

        def decorator(view_callable: typing.Callable[_PS, typing.Awaitable[None]]) -> WebSocketViewCallable:
            unwrapped_view_callable = unwrap_websocket_callable(view_callable)
            resolvers = create_dependency_specs(unwrapped_view_callable)

            @functools.wraps(unwrapped_view_callable)
            async def endpoint(websocket: WebSocket) -> None:
                dependencies = await resolve_dependencies(
                    resolvers,
                    prepared_resolvers={
                        WebSocket: websocket,
                        HTTPConnection: websocket,
                    },
                )
                await unwrapped_view_callable(**dependencies)

            self.routes.append(WebSocketRoute(path, endpoint, name=name, middleware=middleware))
            return endpoint

        return decorator

    def __iter__(self) -> typing.Iterator[BaseRoute]:
        return iter(self.routes)

    def __len__(self) -> int:
        return len(self.routes)

    def __repr__(self) -> str:
        routes_count = len(self.routes)
        noun = "route" if routes_count == 1 else "routes"
        return f"<{self.__class__.__name__}: {routes_count} {noun}>"

    @typing.overload
    def __getitem__(self, index: int) -> BaseRoute:  # pragma: no cover
        ...

    @typing.overload
    def __getitem__(self, index: slice) -> typing.Sequence[BaseRoute]:  # pragma: no cover
        ...

    def __getitem__(self, index: int | slice) -> BaseRoute | typing.Sequence[BaseRoute]:
        return self.routes[index]
