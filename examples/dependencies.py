import contextlib
import time
import typing

from starlette.authentication import SimpleUser
from starlette.requests import Request

from starlette_dispatch import (
    DependencyResolver,
    DependencySpec,
    FactoryResolver,
    RequestResolver,
    VariableResolver,
)
from starlette_dispatch.injections import DependencyScope, ResolveContext

# provides user from request.user attribute
CurrentUser = typing.Annotated[SimpleUser, RequestResolver(lambda r: r.user)]

# provides current time using factory dependency
CurrentTime = typing.Annotated[float, FactoryResolver(lambda: time.time())]

# computes current time once and caches it
CachedCurrentTime = typing.Annotated[float, FactoryResolver(lambda: time.time(), scope=DependencyScope.SINGLETON)]

# provides a static value from a variable
Variable = typing.Annotated[str, VariableResolver("value")]

ParentValue = typing.Annotated[str, VariableResolver("parent")]


def child_value(parent_value: ParentValue) -> str:
    return "child: " + parent_value


ChildValue = typing.Annotated[str, FactoryResolver(child_value)]


async def async_value() -> str:
    return "async value"


AsyncValue = typing.Annotated[str, FactoryResolver(async_value)]


async def complex_factory(request: Request, spec: DependencySpec) -> str:
    return f"{request.url.path}, param: {spec.param_name}, type: {spec.param_type}"


ComplexValue = typing.Annotated[str, FactoryResolver(complex_factory)]


class CustomResolver(DependencyResolver):
    async def resolve(self, context: ResolveContext, spec: DependencySpec) -> typing.Any:
        return f"resolved from {spec.param_name}"


CustomResolverValue = typing.Annotated[str, CustomResolver()]


@contextlib.contextmanager
def enter_factory() -> typing.Generator[str, None, None]:
    yield "enter"


@contextlib.asynccontextmanager
async def aenter_factory() -> typing.AsyncGenerator[str, None]:
    yield "aenter"
