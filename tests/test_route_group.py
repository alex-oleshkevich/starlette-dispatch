import functools
import typing

from starlette.applications import Starlette
from starlette.authentication import requires
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Mount, Route
from starlette.testclient import TestClient
from starlette.types import ASGIApp, Receive, Scope, Send
from starlette.websockets import WebSocket

from starlette_dispatch.contrib.dependencies import PathParamValue
from starlette_dispatch.injections import FactoryDependency
from starlette_dispatch.route_group import AsyncViewCallable, RouteGroup


class _ExampleMiddleware:
    def __init__(self, app: ASGIApp, value: str = "set") -> None:
        self.app = app
        self.value = value

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope.setdefault("state", {})
        scope["state"].setdefault("value", "")
        scope["state"]["value"] = scope["state"]["value"] + self.value
        await self.app(scope, receive, send)


def test_repr(route_group: RouteGroup) -> None:
    @route_group.get("/test")
    async def view(request: Request) -> Response:
        return PlainTextResponse("ok")

    assert repr(route_group) == "<RouteGroup: 1 route>"


def test_common_middleware() -> None:
    route_group = RouteGroup(middleware=[Middleware(_ExampleMiddleware)])

    @route_group.get("/")
    async def view(request: Request) -> Response:
        return PlainTextResponse(request.state.value)

    app = Starlette(routes=route_group)
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.text == "set"


def test_common_middleware_with_route_middleware() -> None:
    route_group = RouteGroup(middleware=[Middleware(_ExampleMiddleware)])

    @route_group.get("/", middleware=[Middleware(_ExampleMiddleware, value="route")])
    async def view(request: Request) -> Response:
        return PlainTextResponse(request.state.value)

    app = Starlette(routes=route_group)
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.text == "setroute"


def test_getattr(route_group: RouteGroup) -> None:
    @route_group.get("/test")
    @route_group.get("/test/2")
    async def view(request: Request) -> Response:
        return PlainTextResponse("ok")

    route = route_group[0]
    assert isinstance(route, Route)
    assert route.path == "/test/2"

    route = route_group[1]
    assert isinstance(route, Route)
    assert route.path == "/test"

    routes = route_group[:2]
    assert len(routes) == 2


def test_iter(route_group: RouteGroup) -> None:
    @route_group.get("/test/{injection}")
    async def view(request: Request) -> Response:
        return PlainTextResponse("ok")

    assert len(route_group) == 1


_Injection = typing.Annotated[str, PathParamValue(param_name="injection")]


def test_injections(route_group: RouteGroup) -> None:
    @route_group.get("/test/{injection}")
    async def view(request: Request, injection: _Injection) -> Response:
        return PlainTextResponse(injection)

    app = Starlette(routes=route_group)
    with TestClient(app) as client:
        response = client.get("/test/injected")
        assert response.status_code == 200
        assert response.text == "injected"


def test_injections_with_decorator(route_group: RouteGroup) -> None:
    def view_decorator(fn: AsyncViewCallable) -> AsyncViewCallable:
        @functools.wraps(fn)
        async def inner_view(request: Request, **dependencies: typing.Any) -> Response:
            request.state.value = "fromdecorator"
            return await fn(request, **dependencies)

        return inner_view

    @route_group.get("/test/{injection}")
    @view_decorator
    async def view(request: Request, injection: _Injection) -> Response:
        return PlainTextResponse(injection + request.state.value)

    app = Starlette(routes=route_group)
    with TestClient(app) as client:
        response = client.get("/test/injected")
        assert response.status_code == 200
        assert response.text == "injectedfromdecorator"


def test_injections_with_multiple_routes_on_same_view(route_group: RouteGroup) -> None:
    @route_group.get("/test/{injection}")
    @route_group.get("/test/2/{injection}")
    async def view(request: Request, injection: _Injection) -> Response:
        return PlainTextResponse(injection)

    app = Starlette(routes=route_group)
    with TestClient(app) as client:
        assert client.get("/test/injected").text == "injected"
        assert client.get("/test/2/injected").text == "injected"


def test_returns_view_callable(route_group: RouteGroup) -> None:
    async def view(request: Request, injection: _Injection) -> Response:
        return PlainTextResponse(injection)

    wrapped_view = route_group.add("/test/{injection}")(view)

    @route_group.get("/{injection}")
    async def dispatch_view(request: Request) -> Response:
        response = await wrapped_view(request)
        return PlainTextResponse(str(response.body))

    app = Starlette(routes=route_group)
    with TestClient(app) as client:
        response = client.get("/woof")
        assert response.status_code == 200
        assert response.text == "b'woof'"


def test_route_dependency_injects_request(route_group: RouteGroup) -> None:
    def dependency(request: Request) -> str:
        return request.url.path

    RequestDep = typing.Annotated[str, FactoryDependency(dependency)]

    @route_group.get("/")
    async def view(dep: RequestDep) -> Response:
        return PlainTextResponse(dep)

    app = Starlette(routes=route_group)
    with TestClient(app) as client:
        response = client.get("/")
        assert response.status_code == 200
        assert response.text == "/"


def test_websocket_dependency_injects_websocket(route_group: RouteGroup) -> None:
    def dependency(websocket: WebSocket) -> str:
        return websocket.url.path

    RequestDep = typing.Annotated[str, FactoryDependency(dependency)]

    @route_group.websocket("/test")
    async def view(websocket: WebSocket, dep: RequestDep) -> None:
        await websocket.accept()
        await websocket.send_text(dep)
        await websocket.close()

    app = Starlette(routes=route_group)
    with TestClient(app) as client:
        with client.websocket_connect("/test") as session:
            assert session.receive_text() == "/test"


def test_norequest_handler(route_group: RouteGroup) -> None:
    @route_group.get("/test")
    async def view() -> Response:
        return PlainTextResponse("ok")

    app = Starlette(routes=route_group)
    with TestClient(app) as client:
        response = client.get("/test")
        assert response.status_code == 200
        assert response.text == "ok"

    assert client.post("/test").status_code == 405


def test_handler_with_decorator(route_group: RouteGroup) -> None:
    @requires("admin")
    @route_group.get("/test")
    async def view(request: Request) -> Response:
        return PlainTextResponse("ok")

    app = Starlette(routes=route_group)
    with TestClient(app) as client:
        response = client.get("/test")
        assert response.status_code == 200
        assert response.text == "ok"

    assert client.post("/test").status_code == 405


def test_async_handler(route_group: RouteGroup) -> None:
    @route_group.get("/test")
    async def view(request: Request) -> Response:
        return PlainTextResponse("ok")

    app = Starlette(routes=route_group)
    with TestClient(app) as client:
        response = client.get("/test")
        assert response.status_code == 200
        assert response.text == "ok"

    assert client.post("/test").status_code == 405


def test_sync_handler(route_group: RouteGroup) -> None:
    @route_group.get("/test")
    def view(request: Request) -> Response:
        return PlainTextResponse("ok")

    app = Starlette(routes=route_group)
    with TestClient(app) as client:
        response = client.get("/test")
        assert response.status_code == 200
        assert response.text == "ok"

    assert client.post("/test").status_code == 405


def test_children() -> None:
    child_group = RouteGroup()

    @child_group.get("/test")
    def view(request: Request) -> Response:
        return PlainTextResponse("ok")

    app = Starlette(routes=RouteGroup(children=[child_group]))
    with TestClient(app) as client:
        response = client.get("/test")
        assert response.status_code == 200
        assert response.text == "ok"

    assert client.post("/test").status_code == 405


def test_children_with_route() -> None:
    def view(request: Request) -> Response:
        return PlainTextResponse("ok")

    app = Starlette(
        routes=RouteGroup(
            children=[
                Mount(path="/", routes=[Route("/test", view)]),
            ]
        ),
    )
    with TestClient(app) as client:
        response = client.get("/test")
        assert response.status_code == 200
        assert response.text == "ok"

    assert client.post("/test").status_code == 405


class TestGet:
    def test_base(self, route_group: RouteGroup) -> None:
        @route_group.get("/test")
        async def view(request: Request) -> Response:
            return PlainTextResponse("ok")

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert response.text == "ok"

        assert client.post("/test").status_code == 405

    def test_named(self, route_group: RouteGroup) -> None:
        @route_group.get("/test", name="test")
        async def view(request: Request) -> Response:
            return PlainTextResponse(str(request.url_for("test")))

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.get("/test")
            assert response.text == "http://testserver/test"

    def test_middleware(self, route_group: RouteGroup) -> None:
        @route_group.get("/test", name="test", middleware=[Middleware(_ExampleMiddleware)])
        async def view(request: Request) -> Response:
            return PlainTextResponse(request.scope["state"]["value"])

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.get("/test")
            assert response.text == "set"


class TestGetOrPost:
    def test_base(self, route_group: RouteGroup) -> None:
        @route_group.get_or_post("/test")
        async def view(request: Request) -> Response:
            return PlainTextResponse("ok")

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert response.text == "ok"

            response = client.post("/test")
            assert response.status_code == 200
            assert response.text == "ok"

        assert client.put("/test").status_code == 405

    def test_named(self, route_group: RouteGroup) -> None:
        @route_group.get_or_post("/test", name="test")
        async def view(request: Request) -> Response:
            return PlainTextResponse(str(request.url_for("test")))

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.post("/test")
            assert response.text == "http://testserver/test"

    def test_middleware(self, route_group: RouteGroup) -> None:
        @route_group.get_or_post("/test", name="test", middleware=[Middleware(_ExampleMiddleware)])
        async def view(request: Request) -> Response:
            return PlainTextResponse(request.scope["state"]["value"])

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.post("/test")
            assert response.text == "set"


class TestPost:
    def test_base(self, route_group: RouteGroup) -> None:
        @route_group.post("/test")
        async def view(request: Request) -> Response:
            return PlainTextResponse("ok")

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.post("/test")
            assert response.status_code == 200
            assert response.text == "ok"

        assert client.get("/test").status_code == 405

    def test_named(self, route_group: RouteGroup) -> None:
        @route_group.post("/test", name="test")
        async def view(request: Request) -> Response:
            return PlainTextResponse(str(request.url_for("test")))

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.post("/test")
            assert response.text == "http://testserver/test"

    def test_middleware(self, route_group: RouteGroup) -> None:
        @route_group.post("/test", name="test", middleware=[Middleware(_ExampleMiddleware)])
        async def view(request: Request) -> Response:
            return PlainTextResponse(request.scope["state"]["value"])

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.post("/test")
            assert response.text == "set"


class TestPut:
    def test_base(self, route_group: RouteGroup) -> None:
        @route_group.put("/test")
        async def view(request: Request) -> Response:
            return PlainTextResponse("ok")

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.put("/test")
            assert response.status_code == 200
            assert response.text == "ok"

        assert client.get("/test").status_code == 405

    def test_named(self, route_group: RouteGroup) -> None:
        @route_group.put("/test", name="test")
        async def view(request: Request) -> Response:
            return PlainTextResponse(str(request.url_for("test")))

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.put("/test")
            assert response.text == "http://testserver/test"

    def test_middleware(self, route_group: RouteGroup) -> None:
        @route_group.put("/test", name="test", middleware=[Middleware(_ExampleMiddleware)])
        async def view(request: Request) -> Response:
            return PlainTextResponse(request.scope["state"]["value"])

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.put("/test")
            assert response.text == "set"


class TestPatch:
    def test_base(self, route_group: RouteGroup) -> None:
        @route_group.patch("/test")
        async def view(request: Request) -> Response:
            return PlainTextResponse("ok")

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.patch("/test")
            assert response.status_code == 200
            assert response.text == "ok"

        assert client.get("/test").status_code == 405

    def test_named(self, route_group: RouteGroup) -> None:
        @route_group.patch("/test", name="test")
        async def view(request: Request) -> Response:
            return PlainTextResponse(str(request.url_for("test")))

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.patch("/test")
            assert response.text == "http://testserver/test"

    def test_middleware(self, route_group: RouteGroup) -> None:
        @route_group.patch("/test", name="test", middleware=[Middleware(_ExampleMiddleware)])
        async def view(request: Request) -> Response:
            return PlainTextResponse(request.scope["state"]["value"])

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.patch("/test")
            assert response.text == "set"


class TestDelete:
    def test_base(self, route_group: RouteGroup) -> None:
        @route_group.delete("/test")
        async def view(request: Request) -> Response:
            return PlainTextResponse("ok")

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.delete("/test")
            assert response.status_code == 200
            assert response.text == "ok"

        assert client.get("/test").status_code == 405

    def test_named(self, route_group: RouteGroup) -> None:
        @route_group.delete("/test", name="test")
        async def view(request: Request) -> Response:
            return PlainTextResponse(str(request.url_for("test")))

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.delete("/test")
            assert response.text == "http://testserver/test"

    def test_middleware(self, route_group: RouteGroup) -> None:
        @route_group.delete("/test", name="test", middleware=[Middleware(_ExampleMiddleware)])
        async def view(request: Request) -> Response:
            return PlainTextResponse(request.scope["state"]["value"])

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.delete("/test")
            assert response.text == "set"


class TestWebSocket:
    def test_base(self, route_group: RouteGroup) -> None:
        @route_group.websocket("/test")
        async def view(websocket: WebSocket) -> None:
            await websocket.accept()
            await websocket.send_text("Hello, websocket!")
            await websocket.close()

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            with client.websocket_connect("/test") as session:
                assert session.receive_text() == "Hello, websocket!"

    def test_named_route(self, route_group: RouteGroup) -> None:
        @route_group.websocket("/test", name="test")
        async def view(websocket: WebSocket) -> None:
            await websocket.accept()
            await websocket.send_text(str(websocket.url_for("test")))
            await websocket.close()

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            with client.websocket_connect("/test") as session:
                assert session.receive_text() == "ws://testserver/test"

    def test_middleware(self, route_group: RouteGroup) -> None:
        @route_group.websocket("/test", name="test", middleware=[Middleware(_ExampleMiddleware)])
        async def view(websocket: WebSocket) -> None:
            await websocket.accept()
            await websocket.send_text(websocket.scope["state"]["value"])
            await websocket.close()

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            with client.websocket_connect("/test") as session:
                assert session.receive_text() == "set"
