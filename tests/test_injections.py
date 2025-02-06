import contextlib
import dataclasses
import time
import typing

import pytest
from starlette.requests import HTTPConnection, Request

from starlette_dispatch.injections import (
    create_dependency_specs,
    DependencyError,
    DependencyNotFoundError,
    DependencyRequiresValueError,
    DependencyScope,
    DependencySpec,
    FactoryDependency,
    RequestDependency,
    resolve_dependencies,
    ResolveContext,
    VariableResolver,
)


def resolver_one() -> int:
    return 42


def resolver_two() -> str:
    return "level2"


_IntDependency = typing.Annotated[int, FactoryDependency(resolver_one)]
_L2Dependency = typing.Annotated[int, FactoryDependency(resolver_two)]


async def test_create_dependency_resolvers() -> None:
    def view(dep: _IntDependency, dep2: _L2Dependency) -> str:
        return f"{dep} - {dep2}"

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as dependencies:
        assert dependencies == {"dep": 42, "dep2": "level2"}


async def test_async_dependencies() -> None:
    async def factory() -> str:
        return "ok"

    AsyncFactory = typing.Annotated[str, FactoryDependency(factory)]

    def view(dep: AsyncFactory) -> str:
        return dep

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as dependencies:
        assert dependencies == {"dep": "ok"}


async def test_async_subdependencies() -> None:
    async def parent_factory() -> str:
        return "ok"

    ParentFactory = typing.Annotated[str, FactoryDependency(parent_factory)]

    async def factory(parent: ParentFactory) -> str:
        return f"ok-{parent}"

    AsyncFactory = typing.Annotated[str, FactoryDependency(factory)]

    def view(dep: AsyncFactory) -> str:
        return dep

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as dependencies:
        assert dependencies == {"dep": "ok-ok"}


async def test_cached_dependencies() -> None:
    async def factory() -> float:
        return time.time()

    AsyncFactory = typing.Annotated[float, FactoryDependency(factory, scope=DependencyScope.SINGLETON)]

    def view(dep: AsyncFactory) -> float:
        return dep

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as dependencies:
        async with resolve_dependencies(request, resolvers) as dependencies2:
            assert dependencies == dependencies2


async def test_cached_subdependencies() -> None:
    async def parent_factory() -> float:
        return time.time()

    ParentFactory = typing.Annotated[float, FactoryDependency(parent_factory, scope=DependencyScope.SINGLETON)]

    async def factory(parent: ParentFactory) -> float:
        return parent

    AsyncFactory = typing.Annotated[float, FactoryDependency(factory)]

    def view(dep: AsyncFactory) -> float:
        return dep

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as dependencies:
        async with resolve_dependencies(request, resolvers) as dependencies2:
            assert dependencies == dependencies2


async def test_with_subdependencies() -> None:
    user_data = {"username": "admin", "id": "1"}

    def user_provider() -> dict[str, str]:
        return user_data

    UserProvider = typing.Annotated[dict[str, str], FactoryDependency(user_provider)]

    def username_resolver(user: UserProvider) -> str:
        return user["username"]

    UserName = typing.Annotated[str, FactoryDependency(username_resolver)]

    def view(user: UserProvider, username: UserName) -> int:
        return 0

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as dependencies:
        assert dependencies == {"user": user_data, "username": "admin"}


async def test_raises_for_invalid_deps() -> None:
    class NotDep: ...

    def view(dep: NotDep) -> None: ...

    with pytest.raises(DependencyNotFoundError) as ex:
        resolvers = create_dependency_specs(view)
        request = Request({"type": "http"})
        async with resolve_dependencies(request, resolvers):
            pass
    assert str(ex.value) == 'Cannot inject parameter "dep": no resolver registered for type "NotDep".'


async def test_calls_fallback_factories() -> None:
    @dataclasses.dataclass
    class NotDep:
        value: str

    def view(dep: NotDep) -> None: ...

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    static = {NotDep: NotDep("fallback")}
    async with resolve_dependencies(request, resolvers, static) as dependencies:
        assert dependencies == {"dep": NotDep("fallback")}


async def test_mixes_annotated_and_prepared_deps() -> None:
    @dataclasses.dataclass
    class NotDep:
        value: str

    def view(dep: NotDep, dep2: _IntDependency) -> None: ...

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    static = {NotDep: NotDep("fallback")}
    async with resolve_dependencies(request, resolvers, static) as dependencies:
        assert dependencies == {"dep": NotDep("fallback"), "dep2": 42}


async def test_injects_dependency_spec() -> None:
    def view(spec: DependencySpec) -> str:
        return ""

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as dependencies:
        assert isinstance(dependencies["spec"], DependencySpec)
        assert dependencies["spec"].param_name == "spec"


async def test_injects_dependency_spec_in_subdependencies() -> None:
    def requirement(spec: DependencySpec) -> DependencySpec:
        return spec

    Requirement = typing.Annotated[DependencySpec, FactoryDependency(requirement)]

    def view(req: Requirement) -> None: ...

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as dependencies:
        assert isinstance(dependencies["req"], DependencySpec)
        assert dependencies["req"].param_name == "spec"


async def test_non_optional_dependency_raises_for_none() -> None:
    def requirement() -> str | None:
        return None

    Requirement = typing.Annotated[str, FactoryDependency(requirement)]

    def view(req: Requirement) -> None: ...

    resolvers = create_dependency_specs(view)
    with pytest.raises(DependencyRequiresValueError):
        request = Request({"type": "http"})
        async with resolve_dependencies(request, resolvers):
            pass


async def test_optional_dependency_not_raises_for_none() -> None:
    def requirement() -> str | None:
        return None

    Requirement = typing.Annotated[str, FactoryDependency(requirement)]

    def view(req: Requirement | None) -> None: ...

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as dependencies:
        assert dependencies == {"req": None}


async def test_optional_dependency_annotation() -> None:
    Requirement = typing.Annotated[str | None, None]

    def view(req: Requirement) -> None: ...

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as dependencies:
        assert dependencies == {"req": None}


async def test_optional_dependency_unsupported_union_annotation() -> None:
    Requirement = typing.Annotated[str | int, 1]

    def view(req: Requirement) -> None: ...

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as dependencies:
        assert dependencies == {"req": 1}


async def test_injects_unions() -> None:
    async def factory() -> float:
        return 0.0

    AsyncFactory = typing.Annotated[float, FactoryDependency(factory, scope=DependencyScope.SINGLETON)]

    def view(dep: AsyncFactory | int) -> float:
        return dep

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as dependencies:
        assert dependencies == {"dep": 0.0}


async def test_without_factory() -> None:
    def view(dep: typing.Annotated[None, "str"]) -> str | None:
        return dep

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as dependencies:
        assert dependencies == {"dep": "str"}


async def test_sync_generator_dependency() -> None:
    def parent_gen() -> typing.Generator[str, None, None]:
        yield "parent"

    def gen(parent: typing.Annotated[str, parent_gen]) -> typing.Generator[str, None, None]:
        yield parent + " value"

    def view(dep: typing.Annotated[str, gen]) -> str:
        return dep

    with pytest.raises(DependencyError, match="not supported"):
        resolvers = create_dependency_specs(view)
        request = Request({"type": "http"})
        async with resolve_dependencies(request, resolvers):
            pass


async def test_async_generator_dependency() -> None:
    async def parent_gen() -> typing.AsyncGenerator[str, None]:
        yield "parent"

    async def gen(parent: typing.Annotated[str, parent_gen]) -> typing.AsyncGenerator[str, None]:
        yield parent + " value"

    def view(dep: typing.Annotated[str, gen]) -> str | None:
        return dep

    with pytest.raises(DependencyError, match="not supported"):
        resolvers = create_dependency_specs(view)
        request = Request({"type": "http"})
        async with resolve_dependencies(request, resolvers):
            pass


async def test_sync_context_manager_dependency() -> None:
    @contextlib.contextmanager
    def parent_gen() -> typing.Generator[str, None, None]:
        yield "parent"

    @contextlib.contextmanager
    def gen(parent: typing.Annotated[str, parent_gen]) -> typing.Generator[str, None, None]:
        yield parent + " value"

    def view(dep: typing.Annotated[str, gen]) -> str | None:
        return dep

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as depdenencies:
        assert depdenencies == {"dep": "parent value"}


async def test_async_context_manager_dependency() -> None:
    @contextlib.asynccontextmanager
    async def parent_gen() -> typing.AsyncGenerator[str, None]:
        yield "parent"

    @contextlib.asynccontextmanager
    async def gen(parent: typing.Annotated[str, parent_gen]) -> typing.AsyncGenerator[str, None]:
        yield parent + " value"

    def view(dep: typing.Annotated[str, gen]) -> str | None:
        return dep

    resolvers = create_dependency_specs(view)
    request = Request({"type": "http"})
    async with resolve_dependencies(request, resolvers) as depdenencies:
        assert depdenencies == {"dep": "parent value"}


class TestFactoryResolver:
    async def test_sync_factory(self) -> None:
        def factory() -> str:
            return "abc"

        resolver = FactoryDependency(factory)
        spec = DependencySpec(
            resolver=resolver,
            optional=False,
            param_type=str,
            default=None,
            param_name="dep",
            annotation=str,
            resolver_options=[],
        )
        context = ResolveContext(
            connection=HTTPConnection({"type": "http"}),
            sync_stack=contextlib.ExitStack(),
            async_stack=contextlib.AsyncExitStack(),
            static_dependencies={},
        )
        value = await resolver.resolve(context, spec)
        assert value == "abc"

    async def test_async_factory(self) -> None:
        async def factory() -> str:
            return "abc"

        resolver = FactoryDependency(factory)
        spec = DependencySpec(
            resolver=resolver,
            optional=False,
            param_type=str,
            default=None,
            param_name="dep",
            annotation=str,
            resolver_options=[],
        )
        context = ResolveContext(
            connection=HTTPConnection({"type": "http"}),
            sync_stack=contextlib.ExitStack(),
            async_stack=contextlib.AsyncExitStack(),
            static_dependencies={},
        )
        value = await resolver.resolve(context, spec)
        assert value == "abc"

    async def test_cached_dependency(self) -> None:
        def factory() -> float:
            return time.time()

        resolver = FactoryDependency(factory, scope=DependencyScope.SINGLETON)
        spec = DependencySpec(
            resolver=resolver,
            optional=False,
            param_type=str,
            default=None,
            param_name="dep",
            annotation=str,
            resolver_options=[],
        )

        context = ResolveContext(
            connection=HTTPConnection({"type": "http"}),
            sync_stack=contextlib.ExitStack(),
            async_stack=contextlib.AsyncExitStack(),
            static_dependencies={},
        )
        value = await resolver.resolve(context, spec)
        value2 = await resolver.resolve(context, spec)
        assert value == value2

    async def test_cached_dependency_failure(self) -> None:
        def factory() -> float:
            return time.time()

        resolver = FactoryDependency(factory, scope=DependencyScope.TRANSIENT)
        spec = DependencySpec(
            resolver=resolver,
            optional=False,
            param_type=str,
            default=None,
            param_name="dep",
            annotation=str,
            resolver_options=[],
        )

        context = ResolveContext(
            connection=HTTPConnection({"type": "http"}),
            sync_stack=contextlib.ExitStack(),
            async_stack=contextlib.AsyncExitStack(),
            static_dependencies={},
        )
        value = await resolver.resolve(context, spec)
        value2 = await resolver.resolve(context, spec)
        assert value != value2

    async def test_transient_dependency(self) -> None:
        def factory() -> float:
            return time.time()

        resolver = FactoryDependency(factory, scope=DependencyScope.TRANSIENT)
        spec = DependencySpec(
            resolver=resolver,
            optional=False,
            param_type=str,
            default=None,
            param_name="dep",
            annotation=str,
            resolver_options=[],
        )

        context = ResolveContext(
            connection=HTTPConnection({"type": "http"}),
            sync_stack=contextlib.ExitStack(),
            async_stack=contextlib.AsyncExitStack(),
            static_dependencies={},
        )
        value = await resolver.resolve(context, spec)
        value2 = await resolver.resolve(context, spec)
        assert value != value2

    async def test_request_dependency(self) -> None:
        def factory() -> float:
            return time.time()

        resolver = FactoryDependency(factory, scope=DependencyScope.REQUEST)
        spec = DependencySpec(
            resolver=resolver,
            optional=False,
            param_type=str,
            default=None,
            param_name="dep",
            annotation=str,
            resolver_options=[],
        )

        context = ResolveContext(
            connection=HTTPConnection({"type": "http"}),
            sync_stack=contextlib.ExitStack(),
            async_stack=contextlib.AsyncExitStack(),
            static_dependencies={},
        )
        value = await resolver.resolve(context, spec)
        value2 = await resolver.resolve(context, spec)
        assert value == value2

        context = ResolveContext(
            connection=HTTPConnection({"type": "http"}),
            sync_stack=contextlib.ExitStack(),
            async_stack=contextlib.AsyncExitStack(),
            static_dependencies={},
        )
        value3 = await resolver.resolve(context, spec)
        assert value != value3
        assert value2 != value3


class TestVariableResolver:
    async def test_variable_resolver(self) -> None:
        resolver = VariableResolver("abc")
        spec = DependencySpec(
            resolver=resolver,
            optional=False,
            param_type=str,
            default=None,
            param_name="dep",
            annotation=str,
            resolver_options=[],
        )
        context = ResolveContext(
            connection=HTTPConnection({"type": "http"}),
            sync_stack=contextlib.ExitStack(),
            async_stack=contextlib.AsyncExitStack(),
            static_dependencies={},
        )
        value = await resolver.resolve(context, spec)
        assert value == "abc"


class TestRequestDependency:
    async def test_variable_resolver(self) -> None:
        resolver = RequestDependency(lambda r, d: r.state.dep)
        spec = DependencySpec(
            resolver=resolver,
            optional=False,
            param_type=str,
            default=None,
            param_name="dep",
            annotation=str,
            resolver_options=[],
        )
        context = ResolveContext(
            connection=HTTPConnection({"type": "http", "state": {"dep": "abc"}}),
            sync_stack=contextlib.ExitStack(),
            async_stack=contextlib.AsyncExitStack(),
            static_dependencies={},
        )
        value = await resolver.resolve(context, spec)
        assert value == "abc"

    async def test_request_only(self) -> None:
        resolver = RequestDependency(lambda r: r.state.dep)
        spec = DependencySpec(
            resolver=resolver,
            optional=False,
            param_type=str,
            default=None,
            param_name="dep",
            annotation=str,
            resolver_options=[],
        )
        context = ResolveContext(
            connection=HTTPConnection({"type": "http", "state": {"dep": "abc"}}),
            sync_stack=contextlib.ExitStack(),
            async_stack=contextlib.AsyncExitStack(),
            static_dependencies={},
        )
        value = await resolver.resolve(context, spec)
        assert value == "abc"


class TestGuessResolverType:
    async def test_variable_dependency(self) -> None:
        Requirement = typing.Annotated[str, "value"]

        def view(req: Requirement) -> None: ...

        resolvers = create_dependency_specs(view)
        request = Request({"type": "http"})
        async with resolve_dependencies(request, resolvers) as dependencies:
            assert dependencies == {"req": "value"}

    async def test_zero_lambda_dependency(self) -> None:
        Requirement = typing.Annotated[str, lambda: "value"]

        def view(req: Requirement) -> None: ...

        resolvers = create_dependency_specs(view)
        request = Request({"type": "http"})
        async with resolve_dependencies(request, resolvers) as dependencies:
            assert dependencies == {"req": "value"}

    async def test_one_lambda_dependency(self) -> None:
        Requirement = typing.Annotated[str, lambda r: r.__class__.__name__]

        def view(req: Requirement) -> None: ...

        resolvers = create_dependency_specs(view)
        request = Request({"type": "http"})
        async with resolve_dependencies(request, resolvers) as dependencies:
            assert dependencies == {"req": "Request"}

    async def test_two_lambda_dependency(self) -> None:
        Requirement = typing.Annotated[str, lambda r, s: r.__class__.__name__ + s.__class__.__name__]

        def view(req: Requirement) -> None: ...

        resolvers = create_dependency_specs(view)
        request = Request({"type": "http"})
        async with resolve_dependencies(request, resolvers) as dependencies:
            assert dependencies == {"req": "RequestDependencySpec"}

    async def test_three_lambda_dependency(self) -> None:
        Requirement = typing.Annotated[str, lambda r, s, c: None]

        def view(req: Requirement) -> None: ...

        with pytest.raises(DependencyError, match="should accept only zero, one, or two parameters"):
            resolvers = create_dependency_specs(view)
            request = Request({"type": "http"})
            async with resolve_dependencies(request, resolvers):
                pass

    async def test_function(self) -> None:
        def factory() -> str:
            return "value"

        Requirement = typing.Annotated[str, factory]

        def view(req: Requirement) -> None: ...

        resolvers = create_dependency_specs(view)
        request = Request({"type": "http"})
        async with resolve_dependencies(request, resolvers) as dependencies:
            assert dependencies == {"req": "value"}
