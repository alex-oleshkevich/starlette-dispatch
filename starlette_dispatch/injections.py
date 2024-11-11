from __future__ import annotations

import abc
import dataclasses
import inspect
import types
import typing

from starlette.requests import HTTPConnection

T = typing.TypeVar("T")
_PS = typing.ParamSpec("_PS")
_RT = typing.TypeVar("_RT")


class DependencyError(Exception): ...


class DependencyNotFoundError(Exception): ...


class DependencyRequiresValueError(Exception): ...


class DependencyResolver(abc.ABC):  # pragma: no cover
    @abc.abstractmethod
    async def resolve(self, spec: DependencySpec, overrides: dict[typing.Any, typing.Any]) -> typing.Any: ...


class FactoryDependency(DependencyResolver):
    """Dependency resolver that resolves dependencies from factories."""

    def __init__(self, resolver: typing.Callable[_PS, typing.Any], *, cached: bool = False) -> None:
        self._cached = cached
        self._resolver = resolver
        self._dependencies = create_dependency_specs(resolver)
        self._is_async = inspect.iscoroutinefunction(resolver)
        self._value: typing.Any = None

    async def resolve(self, spec: DependencySpec, overrides: dict[typing.Any, typing.Any]) -> typing.Any:
        overrides = {**overrides, DependencySpec: spec}
        dependencies = await resolve_dependencies(self._dependencies, overrides=overrides)

        if self._cached and self._value is not None:
            return self._value

        self._value = await self._resolver(**dependencies) if self._is_async else self._resolver(**dependencies)
        return self._value


class NoDependencyResolver(DependencyResolver):
    """Resolver that raises an error when a dependency is not found."""

    async def resolve(self, spec: DependencySpec, overrides: dict[typing.Any, typing.Any]) -> typing.Any:
        if spec.param_type in overrides:
            return overrides[spec.param_type]

        message = (
            f'Cannot inject parameter "{spec.param_name}": '
            f'no resolver registered for type "{spec.param_type.__name__}".'
        )
        raise DependencyNotFoundError(message)


class VariableDependency(DependencyResolver):
    """Simple resolver that returns the same value for all dependencies."""

    def __init__(self, value: typing.Any) -> None:
        self._value = value

    async def resolve(self, spec: DependencySpec, overrides: dict[typing.Any, typing.Any]) -> typing.Any:
        return self._value


class RequestDependency(DependencyResolver):
    """Helper resolver that uses request state to return dependency values.
    It accepts a callable that receives HTTPConnection (like Request or WebSocket) and returns a value.

    Note: this resolver should be used in request context only.
    """

    def __init__(
        self,
        fn: typing.Callable[[HTTPConnection, DependencySpec], typing.Any]
        | typing.Callable[[HTTPConnection], typing.Any],
    ) -> None:
        self._fn = fn
        self.takes_spec = False

        signature = inspect.signature(fn)
        if len(signature.parameters) == 2:
            self.takes_spec = True

    async def resolve(self, spec: DependencySpec, overrides: dict[typing.Any, typing.Any]) -> typing.Any:
        conn: HTTPConnection = overrides[HTTPConnection]
        if self.takes_spec:
            return self._fn(conn, spec)  # type: ignore[call-arg]
        return self._fn(conn)  # type: ignore[call-arg]


@dataclasses.dataclass(slots=True)
class DependencySpec:
    param_name: str
    param_type: type
    default: typing.Any
    optional: bool
    annotation: typing.Any
    resolver: DependencyResolver
    resolver_options: list[typing.Any]

    async def resolve(self, prepared_dependencies: dict[typing.Any, typing.Any]) -> typing.Any:
        return await self.resolver.resolve(self, prepared_dependencies)


def create_dependency_from_parameter(parameter: inspect.Parameter) -> DependencySpec:
    origin = typing.get_origin(parameter.annotation)
    is_optional = False
    annotation: type = parameter.annotation

    resolver: DependencyResolver = NoDependencyResolver()
    resolver_options: list[typing.Any] = []

    # if param is union then extract first non None argument from type
    if origin is typing.Union:
        is_optional = type(None) in typing.get_args(parameter.annotation)
        annotation = [arg for arg in typing.get_args(parameter.annotation) if arg is not None][0]
        origin = typing.get_origin(annotation)

    # resolve annotated dependencies like: typing.Annotated[T, func]
    param_type = annotation
    if origin is not typing.Annotated:
        # unannotated parameters are allowed, but they will raise an error during resolution
        # the NoDependencyResolver will try to look up the overridden type in the prepared dependencies
        return DependencySpec(
            optional=is_optional,
            param_type=param_type,
            default=parameter.default,
            param_name=parameter.name,
            resolver=NoDependencyResolver(),
            annotation=parameter.annotation,
            resolver_options=resolver_options,
        )

    match typing.get_args(annotation):
        case (defined_param_type, *options, DependencyResolver() as defined_resolver):
            param_type = defined_param_type
            resolver = defined_resolver
            resolver_options = options
        case (defined_param_type, *options, fn) if inspect.isfunction(fn) and fn.__name__ == "<lambda>":
            param_type = defined_param_type
            resolver_options = options
            signature = inspect.signature(fn)
            if len(signature.parameters) == 0:
                resolver = FactoryDependency(fn)
            elif len(signature.parameters) == 1:

                def callback(request: HTTPConnection, spec: DependencySpec) -> typing.Any:
                    return fn(request)

                resolver = RequestDependency(callback)
            elif len(signature.parameters) == 2:

                def callback(request: HTTPConnection, spec: DependencySpec) -> typing.Any:
                    return fn(request, spec)

                resolver = RequestDependency(callback)
            else:
                raise DependencyError(
                    "Lamda passed as dependency should accept only zero, one, or two parameters: "
                    "(lambda: ...), (lambda request: ...), or (lambda request, spec: ...)."
                )
        case (defined_param_type, *options, fn) if inspect.isfunction(fn):
            resolver_options = options
            param_type = defined_param_type
            resolver = FactoryDependency(fn)
        case (defined_param_type, *options, value):
            if isinstance(defined_param_type, types.UnionType):
                is_optional = types.NoneType in typing.get_args(defined_param_type)
                defined_param_type = [arg for arg in typing.get_args(defined_param_type) if arg is not None][0]

            resolver_options = options
            param_type = defined_param_type
            resolver = VariableDependency(value)
        case _:  # pragma: no cover, we never reach this line
            ...

    return DependencySpec(
        resolver=resolver,
        optional=is_optional,
        param_type=param_type,
        default=parameter.default,
        param_name=parameter.name,
        annotation=parameter.annotation,
        resolver_options=resolver_options,
    )


def create_dependency_specs(fn: typing.Callable[..., typing.Any]) -> typing.Mapping[str, DependencySpec]:
    signature = inspect.signature(fn, eval_str=True)
    return {parameter.name: create_dependency_from_parameter(parameter) for parameter in signature.parameters.values()}


async def resolve_dependencies(
    resolvers: typing.Mapping[str, DependencySpec],
    overrides: typing.Mapping[type, typing.Any],
) -> dict[str, typing.Any]:
    dependencies: dict[str, typing.Any] = {}
    for param_name, spec in resolvers.items():
        dependency = await spec.resolve(
            {
                **overrides,
                DependencySpec: spec,
            }
        )
        if dependency is None and not spec.optional:
            message = f'Dependency "{spec.param_name}" has None value but it is not optional.'
            raise DependencyRequiresValueError(message)
        dependencies[param_name] = dependency

    return dependencies
