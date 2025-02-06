import functools
import typing
from pathlib import Path

from starception import install_error_handler
from starlette.applications import Starlette
from starlette.authentication import SimpleUser
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.templating import Jinja2Templates

from examples.dependencies import (
    aenter_factory,
    AsyncValue,
    CachedCurrentTime,
    ChildValue,
    ComplexValue,
    CurrentTime,
    CurrentUser,
    CustomResolverValue,
    enter_factory,
    Variable,
)
from examples.middleware import ProvideUser
from starlette_dispatch import FromPath, RouteGroup
from starlette_dispatch.route_group import AsyncViewCallable

this_dir = Path(__file__).parent
templates = Jinja2Templates(this_dir / "templates")

group = RouteGroup()
admin_group = RouteGroup(
    "/admin",
    middleware=[
        Middleware(ProvideUser, user=SimpleUser(username="admin")),
    ],
)


@group.get("/")
async def index_view(request: Request) -> Response:
    return templates.TemplateResponse("index.html", {"request": request})


@group.get("/request-dependency")
def request_dependency_view(user: CurrentUser) -> Response:
    return PlainTextResponse(f"Hello, {user.username}!")


@group.get("/factory-dependency")
def factory_dependency_view(time: CurrentTime, cached_time: CachedCurrentTime) -> Response:
    return JSONResponse(
        {
            "time": time,
            "cached_time": cached_time,
        }
    )


@group.get("/async-dependency")
def async_dependency_view(value: AsyncValue) -> Response:
    return PlainTextResponse(value)


@group.get("/factory-dependency-dependency")
def factory_dependency_dependency_view(value: ChildValue) -> Response:
    return PlainTextResponse(value)


@group.get("/complex-dependency")
def complex_dependency_view(value: ComplexValue) -> Response:
    return PlainTextResponse(value)


@group.get("/custom-resolver-dependency")
def custom_resolver_dependency_view(value: CustomResolverValue) -> Response:
    return PlainTextResponse(value)


@group.get("/variable-dependency")
def variable_dependency_view(value: Variable) -> Response:
    return PlainTextResponse(value)


@group.get("/path-dependency")
@group.get("/path-dependency/{value}")
def path_dependency_view(value: FromPath[str]) -> Response:
    return PlainTextResponse(value)


@group.get("/path-dependency-optional")
@group.get("/path-dependency-optional/{value}")
def optional_path_dependency_view(value: FromPath[str] | None) -> Response:
    return PlainTextResponse(str(value))


@group.get("/multi-one")
@group.get("/multi-two")
def multiple_routes_view() -> Response:
    return PlainTextResponse(multiple_routes_view.__name__)


@group.get("/zero-lambda-dep")
def zero_lambda_dep_view(value: typing.Annotated[str, lambda: "value"]) -> Response:
    return PlainTextResponse(value)


@group.get("/one-lambda-dep")
def one_lambda_dep_view(value: typing.Annotated[str, lambda r: r.__class__.__name__]) -> Response:
    return PlainTextResponse(value)


@group.get("/two-lambda-dep")
def two_lambda_dep_view(
    value: typing.Annotated[str, lambda r, s: r.__class__.__name__ + s.__class__.__name__],
) -> Response:
    return PlainTextResponse(value)


@group.get("/value-dep")
def value_dep_view(value: typing.Annotated[str, "value"]) -> Response:
    return PlainTextResponse(value)


def view_decorator(fn: AsyncViewCallable) -> AsyncViewCallable:
    @functools.wraps(fn)
    async def inner_view(request: Request, **dependencies: typing.Any) -> Response:
        request.state.decoratorvalue = "fromdecorator"
        return await fn(request, **dependencies)

    return inner_view


@group.get("/decorator")
@view_decorator
async def with_decorator_view(request: Request, value: typing.Annotated[str, "value"]) -> Response:
    return PlainTextResponse(value + " " + request.state.decoratorvalue)


@group.get("/cm")
async def context_manager_view(
    sync: typing.Annotated[str, enter_factory], asyncf: typing.Annotated[str, aenter_factory]
) -> Response:
    return JSONResponse(
        {
            "sync": sync,
            "async": asyncf,
        }
    )


@admin_group.get("/")
def admin_view(user: CurrentUser) -> Response:
    return PlainTextResponse(f"Hello, {user.username}!")


install_error_handler()
app = Starlette(
    debug=True,
    routes=RouteGroup(
        children=[
            group,
            admin_group,
        ]
    ),
    middleware=[
        Middleware(ProvideUser, user=SimpleUser(username="test")),
    ],
)
