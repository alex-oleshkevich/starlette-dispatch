from pathlib import Path

from starception import install_error_handler
from starlette.applications import Starlette
from starlette.authentication import SimpleUser
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, Response
from starlette.templating import Jinja2Templates

from examples.dependencies import (
    AsyncValue,
    CachedCurrentTime,
    ChildValue,
    ComplexValue,
    CurrentTime,
    CurrentUser,
    CustomResolverValue,
    Variable,
)
from examples.middleware import ProvideUser
from starlette_dispatch import FromPath, RouteGroup

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
