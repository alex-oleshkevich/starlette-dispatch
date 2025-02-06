import typing

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.testclient import TestClient

from starlette_dispatch.contrib.dependencies import FromPath, PathParamValue
from starlette_dispatch.injections import DependencyError
from starlette_dispatch.route_group import RouteGroup


class TestPathParamValue:
    def test_param_value(self, route_group: RouteGroup) -> None:
        @route_group.get("/test/{injection}")
        async def view(request: Request, injection: FromPath[str]) -> Response:
            return PlainTextResponse(injection)

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.get("/test/injected")
            assert response.status_code == 200
            assert response.text == "injected"

    def test_param_value_casts(self, route_group: RouteGroup) -> None:
        @route_group.get("/test/{injection}")
        async def view(request: Request, injection: FromPath[int]) -> Response:
            return PlainTextResponse(type(injection).__name__)

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.get("/test/1")
            assert response.status_code == 200
            assert response.text == "int"

    def test_custom_name(self, route_group: RouteGroup) -> None:
        @route_group.get("/test/{key}")
        async def view(request: Request, injection: typing.Annotated[str, PathParamValue("key")]) -> Response:
            return PlainTextResponse(injection)

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.get("/test/1")
            assert response.status_code == 200
            assert response.text == "1"

    def test_optional(self, route_group: RouteGroup) -> None:
        @route_group.get("/test")
        async def view(request: Request, injection: FromPath[int] | None) -> Response:
            return PlainTextResponse(type(injection).__name__)

        app = Starlette(routes=route_group)
        with TestClient(app) as client:
            response = client.get("/test")
            assert response.status_code == 200
            assert response.text == "NoneType"

    def test_optional_and_no_value(self, route_group: RouteGroup) -> None:
        @route_group.get("/test")
        async def view(request: Request, injection: FromPath[int]) -> Response:
            return PlainTextResponse(type(injection).__name__)

        with pytest.raises(DependencyError, match="has None value"):
            app = Starlette(routes=route_group)
            with TestClient(app) as client:
                response = client.get("/test")
                assert response.status_code == 200
                assert response.text == "NoneType"
