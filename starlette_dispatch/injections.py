from __future__ import annotations

import abc
import contextlib
import dataclasses
import enum
import inspect
import types
import typing

from starlette.requests import HTTPConnection


@dataclasses.dataclass
class ResolveContext:
    connection: HTTPConnection
    sync_stack: contextlib.ExitStack
    async_stack: contextlib.AsyncExitStack
    static_dependencies: dict[typing.Any, typing.Any]


class DependencyError(Exception): ...


class DependencyNotFoundError(Exception): ...


class DependencyRequiresValueError(Exception): ...


class DependencyResolver(abc.ABC):  # pragma: no cover
    @abc.abstractmethod
    async def resolve(self, context: ResolveContext, spec: DependencySpec) -> typing.Any: ...


class DependencyScope(enum.StrEnum):
    TRANSIENT = "transient"
    SINGLETON = "singleton"
    REQUEST = "request"


class FactoryDependency(DependencyResolver):
    """Dependency resolver that resolves dependencies from factories."""

    def __init__(
        self, resolver: typing.Callable[..., typing.Any], *, scope: DependencyScope = DependencyScope.TRANSIENT
    ) -> None:
        self._scope = scope
        self._resolver = resolver
        self._dependencies = create_dependency_specs(resolver)
        self._is_async = inspect.iscoroutinefunction(resolver)
        self._value: typing.Any = None

    async def resolve(self, context: ResolveContext, spec: DependencySpec) -> typing.Any:
        if self._scope == DependencyScope.SINGLETON and self._value is not None:
            return self._value

        if self._scope == DependencyScope.REQUEST:
            if value := self._get_dependency_from_request(context.connection, spec):
                return value

        dependencies = await _solve_dependencies(context, self._dependencies)
        value = await self._resolve_function(dependencies)
        if isinstance(value, contextlib.AbstractContextManager):
            value = context.sync_stack.enter_context(value)
        elif isinstance(value, contextlib.AbstractAsyncContextManager):
            value = await context.async_stack.enter_async_context(value)
        else:
            value = value

        if self._scope == DependencyScope.REQUEST:
            self._set_dependency_in_request(context.connection, spec, value)

        if self._scope == DependencyScope.SINGLETON:
            self._value = value

        return value

    async def _resolve_function(self, dependencies: dict[str, typing.Any]) -> typing.Any:
        return await self._resolver(**dependencies) if self._is_async else self._resolver(**dependencies)

    def _get_dependency_from_request(self, request: HTTPConnection, spec: DependencySpec) -> typing.Any:
        try:
            stash = request.state.dispatch_dependencies
            return stash.get(f"{id(self._resolver)}_{spec.param_name}")
        except (KeyError, AttributeError):
            return None

    def _set_dependency_in_request(self, request: HTTPConnection, spec: DependencySpec, value: typing.Any) -> None:
        stash = {}
        with contextlib.suppress(KeyError, AttributeError):
            stash = request.state.dispatch_dependencies
        stash.update({f"{id(self._resolver)}_{spec.param_name}": value})
        request.state.dispatch_dependencies = stash


class NoDependencyResolver(DependencyResolver):
    """Resolver that raises an error when a dependency is not found."""

    async def resolve(self, context: ResolveContext, spec: DependencySpec) -> typing.Any:
        if spec.param_type == DependencySpec:
            return spec

        if spec.param_type in context.static_dependencies:
            return context.static_dependencies[spec.param_type]

        message = (
            f'Cannot inject parameter "{spec.param_name}": '
            f'no resolver registered for type "{spec.param_type.__name__}".'
        )
        raise DependencyNotFoundError(message)


class VariableResolver(DependencyResolver):
    """Simple resolver that returns the same value for all dependencies."""

    def __init__(self, value: typing.Any) -> None:
        self._value = value

    async def resolve(self, context: ResolveContext, spec: DependencySpec) -> typing.Any:
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

    async def resolve(self, context: ResolveContext, spec: DependencySpec) -> typing.Any:
        conn: HTTPConnection = context.connection
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

    async def resolve(self, context: ResolveContext) -> typing.Any:
        return await self.resolver.resolve(context, self)


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
        case (defined_param_type, *options, fn) if inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn):
            raise DependencyError(
                "Generators are not supported as dependency factories. "
                "Use context managers or async context managers instead."
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
            resolver = VariableResolver(value)
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


def create_dependency_specs(fn: typing.Callable[..., typing.Any]) -> list[DependencySpec]:
    signature = inspect.signature(fn, eval_str=True)
    return [create_dependency_from_parameter(parameter) for parameter in signature.parameters.values()]


async def _solve_dependencies(context: ResolveContext, resolvers: list[DependencySpec]) -> dict[str, typing.Any]:
    dependencies: dict[str, typing.Any] = {}
    for spec in resolvers:
        dependency = await spec.resolve(context)
        if dependency is None and not spec.optional:
            message = f'Dependency "{spec.param_name}" has None value but it is not optional.'
            raise DependencyRequiresValueError(message)
        dependencies[spec.param_name] = dependency

    return dependencies


@contextlib.asynccontextmanager
async def resolve_dependencies(
    connection: HTTPConnection,
    resolvers: list[DependencySpec],
    static_dependencies: dict[typing.Any, typing.Any] | None = None,
) -> typing.AsyncGenerator[dict[str, typing.Any], None]:
    context = ResolveContext(
        connection=connection,
        sync_stack=contextlib.ExitStack(),
        async_stack=contextlib.AsyncExitStack(),
        static_dependencies=static_dependencies or {},
    )
    with context.sync_stack:
        async with context.async_stack:
            yield await _solve_dependencies(context, resolvers)
