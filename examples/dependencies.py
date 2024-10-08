import time
import typing

from starlette.authentication import SimpleUser
from starlette.requests import Request

from starlette_dispatch import (
    DependencyResolver,
    DependencySpec,
    FactoryDependency,
    RequestDependency,
    VariableDependency,
)

# provides user from request.user attribute
CurrentUser = typing.Annotated[SimpleUser, RequestDependency(lambda r: r.user)]

# provides current time using factory dependency
CurrentTime = typing.Annotated[float, FactoryDependency(lambda: time.time())]

# computes current time once and caches it
CachedCurrentTime = typing.Annotated[float, FactoryDependency(lambda: time.time(), cached=True)]

# provides a static value from a variable
Variable = typing.Annotated[str, VariableDependency("value")]

ParentValue = typing.Annotated[str, VariableDependency("parent")]


def child_value(parent_value: ParentValue) -> str:
    return "child: " + parent_value


ChildValue = typing.Annotated[str, FactoryDependency(child_value)]


async def async_value() -> str:
    return "async value"


AsyncValue = typing.Annotated[str, FactoryDependency(async_value)]


async def complex_factory(request: Request, spec: DependencySpec) -> str:
    return f"{request.url.path}, param: {spec.param_name}, type: {spec.param_type}"


ComplexValue = typing.Annotated[str, FactoryDependency(complex_factory)]


class CustomResolver(DependencyResolver):
    async def resolve(self, spec: DependencySpec, predefined_deps: dict[str, typing.Any]) -> typing.Any:
        return f"resolved from {spec.param_name}"


CustomResolverValue = typing.Annotated[str, CustomResolver()]
