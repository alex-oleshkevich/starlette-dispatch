from __future__ import annotations

import functools
import inspect
import typing

from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.requests import HTTPConnection, Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route, WebSocketRoute
from starlette.websockets import WebSocket

from starlette_dispatch.injections import create_dependency_specs, resolve_dependencies

AsyncViewCallable = typing.Callable[..., typing.Awaitable[Response]]
SyncViewCallable = typing.Callable[..., Response]
AnyViewCallable = AsyncViewCallable | SyncViewCallable
WebSocketViewCallable = typing.Callable[[WebSocket], typing.Awaitable[None]]
HttpMethod = str

_PS = typing.ParamSpec("_PS")
_RT = typing.TypeVar("_RT")


def unwrap_callable(fn: AnyViewCallable) -> AnyViewCallable:
    return fn if not hasattr(fn, "__wrapped__") else unwrap_callable(fn.__wrapped__)


def unwrap_websocket_callable(
    fn: typing.Callable[..., typing.Awaitable[None]],
) -> typing.Callable[..., typing.Awaitable[None]]:
    callback = fn if not hasattr(fn, "__wrapped__") else unwrap_callable(fn.__wrapped__)
    return typing.cast(typing.Callable[..., typing.Awaitable[None]], callback)


class RouteGroup(typing.Sequence[BaseRoute]):
    def __init__(
        self,
        prefix: str | None = None,
        middleware: typing.Sequence[Middleware] | None = None,
        children: typing.Sequence[RouteGroup | BaseRoute] | None = None,
    ) -> None:
        self.prefix = prefix or ""
        self.routes: list[BaseRoute] = []
        self._common_middleware = list(middleware or [])

        for child in children or []:
            if isinstance(child, RouteGroup):
                self.routes.extend(child)
            else:
                self.routes.append(child)

    def add(
        self,
        path: str,
        *,
        methods: list[HttpMethod] | None = None,
        name: str | None = None,
        middleware: typing.Sequence[Middleware] | None = None,
    ) -> typing.Callable[[AnyViewCallable], AsyncViewCallable]:
        path = self.prefix.removesuffix("/") + path if self.prefix else path

        def decorator(view_callable: AnyViewCallable) -> AsyncViewCallable:
            # find the original view callable in order to parse the dependencies
            actual_view_callable = unwrap_callable(view_callable)
            resolvers = create_dependency_specs(actual_view_callable)

            async def endpoint(request: Request) -> Response:
                static_dependencies = {Request: request, HTTPConnection: request}
                async with resolve_dependencies(request, resolvers, static_dependencies) as dependencies:
                    if inspect.iscoroutinefunction(view_callable):
                        return await typing.cast(AsyncViewCallable, view_callable)(**dependencies)
                    return await run_in_threadpool(typing.cast(SyncViewCallable, view_callable), **dependencies)

            all_middleware = self._common_middleware + list(middleware or [])
            self.routes.append(Route(path, endpoint, name=name, methods=methods, middleware=all_middleware))
            return endpoint

        return decorator

    def get(
        self, path: str, *, name: str | None = None, middleware: typing.Sequence[Middleware] | None = None
    ) -> typing.Callable[[AnyViewCallable], AnyViewCallable]:
        return self.add(path, methods=["GET"], name=name, middleware=middleware)

    def post(
        self, path: str, *, name: str | None = None, middleware: typing.Sequence[Middleware] | None = None
    ) -> typing.Callable[[AnyViewCallable], AnyViewCallable]:
        return self.add(path, methods=["POST"], name=name, middleware=middleware)

    def get_or_post(
        self, path: str, *, name: str | None = None, middleware: typing.Sequence[Middleware] | None = None
    ) -> typing.Callable[[AnyViewCallable], AnyViewCallable]:
        return self.add(path, methods=["GET", "POST"], name=name, middleware=middleware)

    def put(
        self, path: str, *, name: str | None = None, middleware: typing.Sequence[Middleware] | None = None
    ) -> typing.Callable[[AnyViewCallable], AnyViewCallable]:
        return self.add(path, methods=["PUT"], name=name, middleware=middleware)

    def patch(
        self, path: str, *, name: str | None = None, middleware: typing.Sequence[Middleware] | None = None
    ) -> typing.Callable[[AnyViewCallable], AnyViewCallable]:
        return self.add(path, methods=["PATCH"], name=name, middleware=middleware)

    def delete(
        self, path: str, *, name: str | None = None, middleware: typing.Sequence[Middleware] | None = None
    ) -> typing.Callable[[AnyViewCallable], AnyViewCallable]:
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
                static_dependencies = {WebSocket: websocket, HTTPConnection: websocket}
                async with resolve_dependencies(websocket, resolvers, static_dependencies) as dependencies:
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
