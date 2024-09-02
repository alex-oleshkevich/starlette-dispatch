import dataclasses
import time
import typing

import pytest

from starlette_dispatch.injections import create_dependency_specs, Dependency, DependencyError, DependencyNotFoundError, \
    DependencyRequiresValueError, DependencySpec, resolve_dependencies


def resolver_one() -> int:
    return 42


def resolver_two() -> str:
    return 'level2'


_IntDependency = typing.Annotated[int, Dependency(resolver_one)]
_L2Dependency = typing.Annotated[int, Dependency(resolver_two)]


async def test_create_dependency_resolvers() -> None:
    def view(dep: _IntDependency, dep2: _L2Dependency) -> str:
        return f'{dep} - {dep2}'

    resolvers = create_dependency_specs(view)
    dependencies = await resolve_dependencies(resolvers, {})
    assert dependencies == {'dep': 42, 'dep2': 'level2'}


async def test_async_dependencies() -> None:
    async def factory() -> str:
        return 'ok'

    AsyncFactory = typing.Annotated[str, Dependency(factory)]

    def view(dep: AsyncFactory) -> str:
        return dep

    resolvers = create_dependency_specs(view)
    dependencies = await resolve_dependencies(resolvers, {})
    assert dependencies == {'dep': 'ok'}


async def test_async_subdependencies() -> None:
    async def parent_factory() -> str:
        return 'ok'

    ParentFactory = typing.Annotated[str, Dependency(parent_factory)]

    async def factory(parent: ParentFactory) -> str:
        return f'ok-{parent}'

    AsyncFactory = typing.Annotated[str, Dependency(factory)]

    def view(dep: AsyncFactory) -> str:
        return dep

    resolvers = create_dependency_specs(view)
    dependencies = await resolve_dependencies(resolvers, {})
    assert dependencies == {'dep': 'ok-ok'}


async def test_cached_dependencies() -> None:
    async def factory() -> float:
        return time.time()

    AsyncFactory = typing.Annotated[float, Dependency(factory, cached=True)]

    def view(dep: AsyncFactory) -> float:
        return dep

    resolvers = create_dependency_specs(view)
    dependencies = await resolve_dependencies(resolvers, {})
    dependencies2 = await resolve_dependencies(resolvers, {})
    assert dependencies == dependencies2


async def test_cached_subdependencies() -> None:
    async def parent_factory() -> float:
        return time.time()

    ParentFactory = typing.Annotated[float, Dependency(parent_factory, cached=True)]

    async def factory(parent: ParentFactory) -> float:
        return parent

    AsyncFactory = typing.Annotated[float, Dependency(factory)]

    def view(dep: AsyncFactory) -> float:
        return dep

    resolvers = create_dependency_specs(view)
    dependencies = await resolve_dependencies(resolvers, {})
    dependencies2 = await resolve_dependencies(resolvers, {})
    assert dependencies == dependencies2


async def test_with_subdependencies() -> None:
    user_data = {'username': 'admin', 'id': '1'}

    def user_provider() -> dict[str, str]:
        return user_data

    UserProvider = typing.Annotated[dict[str, str], Dependency(user_provider)]

    def username_resolver(user: UserProvider) -> str:
        return user['username']

    UserName = typing.Annotated[str, Dependency(username_resolver)]

    def view(user: UserProvider, username: UserName) -> int:
        return 0

    resolvers = create_dependency_specs(view)
    dependencies = await resolve_dependencies(resolvers, {})
    assert dependencies == {'user': user_data, 'username': 'admin'}


async def test_raises_for_invalid_deps() -> None:
    class NotDep: ...

    def view(dep: NotDep) -> None: ...

    with pytest.raises(DependencyNotFoundError) as ex:
        resolvers = create_dependency_specs(view)
        await resolve_dependencies(resolvers, {})
    assert str(ex.value) == 'Cannot inject parameter "dep": no resolver registered for type "NotDep".'


async def test_calls_fallback_factories() -> None:
    @dataclasses.dataclass
    class NotDep:
        value: str

    def view(dep: NotDep) -> None: ...

    resolvers = create_dependency_specs(view)
    dependencies = await resolve_dependencies(resolvers, {
        NotDep: NotDep('fallback'),
    })
    assert dependencies == {'dep': NotDep('fallback')}


async def test_mixes_annotated_and_prepared_deps() -> None:
    @dataclasses.dataclass
    class NotDep:
        value: str

    def view(dep: NotDep, dep2: _IntDependency) -> None: ...

    resolvers = create_dependency_specs(view)
    dependencies = await resolve_dependencies(resolvers, {
        NotDep: NotDep('fallback'),
    })
    assert dependencies == {'dep': NotDep('fallback'), 'dep2': 42}


async def test_injects_dependency_spec() -> None:
    def view(spec: DependencySpec) -> str:
        return ''

    resolvers = create_dependency_specs(view)
    dependencies = await resolve_dependencies(resolvers, {})
    assert isinstance(dependencies['spec'], DependencySpec)
    assert dependencies['spec'].param_name == 'spec'


async def test_injects_dependency_spec_in_subdependencies() -> None:
    def requirement(spec: DependencySpec) -> DependencySpec:
        return spec

    Requirement = typing.Annotated[DependencySpec, Dependency(requirement)]

    def view(req: Requirement) -> None: ...

    resolvers = create_dependency_specs(view)
    dependencies = await resolve_dependencies(resolvers, {})
    assert isinstance(dependencies['req'], DependencySpec)
    assert dependencies['req'].param_name == 'spec'


async def test_non_optional_dependency_raises_for_none() -> None:
    def requirement() -> str | None:
        return None

    Requirement = typing.Annotated[str, Dependency(requirement)]

    def view(req: Requirement) -> None: ...

    resolvers = create_dependency_specs(view)
    with pytest.raises(DependencyRequiresValueError):
        await resolve_dependencies(resolvers, {})


async def test_optional_dependency_not_raises_for_none() -> None:
    def requirement() -> str | None:
        return None

    Requirement = typing.Annotated[str, Dependency(requirement)]

    def view(req: Requirement | None) -> None: ...

    resolvers = create_dependency_specs(view)
    dependencies = await resolve_dependencies(resolvers, {})
    assert dependencies == {'req': None}


async def test_raises_for_unsupported_unions() -> None:
    async def factory() -> float:
        return time.time()

    AsyncFactory = typing.Annotated[float, Dependency(factory, cached=True)]

    def view(dep: AsyncFactory | int) -> float:
        return dep

    with pytest.raises(DependencyError, match='Only optional union types are supported'):
        resolvers = create_dependency_specs(view)
        await resolve_dependencies(resolvers, {})


async def test_raises_for_unsupported_annotation() -> None:
    def view(dep: typing.Annotated[float, "boom"]) -> float:
        return dep

    with pytest.raises(DependencyError, match='does not contain factory in annotation'):
        resolvers = create_dependency_specs(view)
        await resolve_dependencies(resolvers, {})


async def test_without_factory() -> None:
    def view(dep: typing.Annotated[None, 'str'] | None) -> str | None:
        return dep

    with pytest.raises(DependencyError, match='does not contain factory in annotation'):
        resolvers = create_dependency_specs(view)
        await resolve_dependencies(resolvers, {})
