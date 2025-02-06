from starlette.routing import Routefrom examples.dependencies import Variable

# Starlette Dispatch

Routing extensions and dependency injection library for Starlette.

![PyPI](https://img.shields.io/pypi/v/starlette_dispatch)
![GitHub](https://img.shields.io/github/license/alex-oleshkevich/starlette_dispatch)
![Libraries.io dependency status for latest release](https://img.shields.io/librariesio/release/pypi/starlette_dispatch)
![PyPI - Downloads](https://img.shields.io/pypi/dm/starlette_dispatch)
![GitHub Release Date](https://img.shields.io/github/release-date/alex-oleshkevich/starlette_dispatch)

## Installation

Install `starlette_dispatch` using PIP:

```bash
pip install starlette_dispatch
```

## Features

- __Route groups.__ Group routes by common path prefix and common middleware.
- __Route method decorators.__ Convenient decorators for common HTTP methods.
- __Dependency injection.__ Route handlers can request dependencies by adding a parameter with the dependency type hint.
- __Backward compatible__ with Starlette. You can use it with your existing Starlette application.
- __No performance overhead.__ Dependency injection takes exact the same time as if you would write the handler
  manually.
- __Fully typed.__ Starlette Dispatch is fully typed and supports type hints.
- __Async support.__ Starlette Dispatch supports async handlers and async dependencies.

And the most important -- it does not erase route handler signature. You can compose it with any other decorators.

## Quick start

Starlette Dispatch does not require any changes to your existing Starlette application.
You can use it with your existing Starlette application.

Here is a simple snippet that demonstrates dependency injection and route group usage:

```python
import typing

from starlette.applications import Starlette
from starlette.authentication import SimpleUser
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from starlette_dispatch import RouteGroup, RequestDependency

admin_middleware = [
    Middleware(AuthenticationMiddleware, backend=...)
]
admin_routes = RouteGroup('/admin', middleware=admin_middleware)

CurrentUser = typing.Annotated[SimpleUser, RequestDependency(lambda r: r.user)]


async def index_view(request: Request, user: CurrentUser) -> JSONResponse:
    """This is your landing page."""
    return JSONResponse({'message': f'Hello, {user}!'})


@admin_routes.get('/')
async def admin_index_view(request: Request) -> JSONResponse:
    """This is your admin landing page."""
    return JSONResponse({'message': 'Hello, admin!'})


app = Starlette(
    routes=[
        Route('/', index_view),  # regular Starlette route
        *admin_routes,
    ]
)
```

## Route groups

A route group is a way to group routes by common path prefix and common middleware.
Instead of writing the same prefix for each route, you can define a group and add routes to it
using convenient decorators.

> Route groups support all common HTTP methods and add some extra helpers like `get_or_post`.

```python
from starlette.requests import Request
from starlette.responses import JSONResponse

from starlette_dispatch import RouteGroup

group = RouteGroup('/group')


@group.get('/')
def my_view(request: Request) -> JSONResponse:
    return JSONResponse({'message': 'Hello, world!'})


@group.get_or_post('/')
def form_view(request: Request) -> JSONResponse:
    return JSONResponse({'message': 'Hello, world!'})
```

### Multiple routes on a single handler

You can call route decorators multiple times on a single handler.
This way you can share the same handler for multiple routes without creating a new handler.

```python
from starlette.requests import Request
from starlette.responses import JSONResponse

from starlette_dispatch import RouteGroup, FromPath

group = RouteGroup('/group')


@group.get('/new')
@group.get('/edit/{id}')
def create_view(request: Request, id: FromPath[int | None]) -> JSONResponse:
    ...
```

### Route injections

Each route handler can request a dependency by adding a parameter with the dependency type hint.
The dependency will be properly resolved and injected into the handler on handler call.
See more about dependency injection below.

> For each injection Starlette Dispatch creates a resolver function.
> This means, it does not add a noticeable overhead to your application and takes exact the same time as if you would
> write
> the handler manually.

```python
import typing
from starlette.requests import Request
from starlette.responses import JSONResponse

from starlette_dispatch import RouteGroup, VariableResolver


class User: ...


user = User()
CurrentUser = typing.Annotated[str, VariableResolver(user)]

group = RouteGroup('/')


@group.get('/')
def index_view(request: Request, user: CurrentUser) -> JSONResponse:
    return JSONResponse({'message': f'Hello, {user}!'})
```

### Route middleware

Each route can have its own middleware.
> If route group has middleware, it will be merged with route middleware. Route middleware has a higher priority.

```python
import typing

from starlette.requests import Request
from starlette.responses import JSONResponse

from starlette_dispatch import RouteGroup, VariableResolver


class User: ...


user = User()
CurrentUser = typing.Annotated[str, VariableResolver(user)]

group = RouteGroup('/')


@group.get('/')
def my_view(request: Request, user: CurrentUser) -> JSONResponse:
    return JSONResponse({'message': f'Hello, {user}!'})
```

## Dependency injection

In a nutshell, the dependency is a type, annotated with a value or a factory function that resolves to the value.
The factory function is called dependency resolver.

### Variable dependency

Variable dependency is a resolver that returns a simple value.

```python
import typing

from starlette_dispatch import RouteGroup, VariableResolver

Value = typing.Annotated[str, VariableResolver('hello')]

group = RouteGroup('/')


@group.get('/')
def my_view(value: Value) -> None:
    assert value == 'hello'
```

### Factory dependency

Factory dependency is a resolver that creates a value on each call. The result can be cached.
The factory can have dependencies and can be async.

```python
import typing

from starlette_dispatch import FactoryDependency, RouteGroup


def make_dependency():
    return 'hello'


async def async_dependency():
    return 'hello'


Value = typing.Annotated[str, FactoryDependency(make_dependency)]
AsyncValue = typing.Annotated[str, FactoryDependency(async_dependency)]
CachedValue = typing.Annotated[str, FactoryDependency(make_dependency, cached=True)]

group = RouteGroup('/')


@group.get('/')
def my_view(value: Value, async_value: AsyncValue, cached_value: CachedValue) -> None:
    assert value == 'hello'
    assert async_value == 'hello'
    assert cached_value == 'hello'
```

#### Factory function dependencies

The factory function itself can have dependencies. They are defined in the same way as regular dependencies.

```python
import typing

from starlette_dispatch import FactoryDependency, RouteGroup


def parent_dependency():
    return 'hello'


ParentValue = typing.Annotated[str, FactoryDependency(parent_dependency)]


def make_dependency(parent: ParentValue):
    return parent + ' world'


Value = typing.Annotated[str, FactoryDependency(make_dependency)]

group = RouteGroup('/')


@group.get('/')
def my_view(value: Value) -> None:
    assert value == 'hello world'
```

#### Predefined dependencies

There are several predefined dependencies: `starlette.requests.Request`,
`starlette_dispatch.injections.DependencySpec`.

`Request` is a Starlette request object and `DependencySpec` is a special object that contains meta information about
the dependency. `DependencySpec` object is very useful in complex cases.

```python
from starlette.requests import Request

from starlette_dispatch import DependencySpec


def make_dependency(request: Request, spec: DependencySpec):
    assert request  # Starlette request object
    assert spec.param_name  # name of the parameter
    assert spec.param_type  # type of the parameter
    assert spec.optional  # is the parameter optional
    assert spec.default  # default value of the parameter
    assert spec.annotation  # type annotation of the parameter
```

### Request resolver

If your dependency available in the request object, instead of creating a factory function,
you can use a `RequestDependency` resolver. It takes a function that accepts `Request` and `DependencySpec` (optionally)
objects.

```python
import typing
from starlette_dispatch import RequestDependency

# example dependency that resolves to a value from query parameter
Value = typing.Annotated[str, RequestDependency(lambda request, spec,: request.query_params['value'])]
NoSpecValue = typing.Annotated[str, RequestDependency(lambda request: request.query_params['value'])]
```

### Custom resolver

You are not limited to predefined resolvers. You can create your own resolver by subclassing `DependencyResolver`
and implementing the `resolve` method.

```python
from starlette.requests import Request

from starlette_dispatch import DependencyResolver, DependencySpec, ResolveContext


class MyResolver(DependencyResolver):
    async def resolve(self, context: ResolveContext, spec: DependencySpec):
        """Use request and spec objects to create a value."""
        return 'my dependency value'
```

## Dependencies with decorators

Almost any view decorator can work with Starlette Dispatch if it accepts this signature:
`async def view(request) -> Response`.
However, this has some requirements:
1. it should return an async function of `async def view(request, **kwargs)`
2. it should call `functools.wraps` on the inner view, otherwise the view will lose its dependencies
3. it should pass `**kwargs` to the inner view, as Starlette Dispatch passes dependencies via kwargs.

Full listing:
```python
import functools
from starlette.requests import Request
from starlette_dispatch import RouteGroup
from starlette.responses import Response, RedirectResponse


def login_required(fn):
    @functools.wraps(fn)
    async def view(request, **kwargs):
        if not request.user.is_authenticated:
            return RedirectResponse('/')
        return await fn(request, **kwargs)

    return view


group = RouteGroup()


@group.get('/')
@login_required
async def view(request: Request) -> Response: ...
```

## Contrib and support

### Simple dependency definition

Instead of using resolver classes, you can use these shortcuts to define dependencies.

```python
import typing

SimpleValueDependency = typing.Annotated[str, 'simple_value']
LambdaDependency = typing.Annotated[str, lambda: 'some value']
RequestOnlyLambdaDependency = typing.Annotated[str, lambda request: request.query_params['value']]
RequestAndSpecLambdaDependency = typing.Annotated[str, lambda request, spec: ...]
```

### `FromPath` - inject path parameter as a dependency

```python
from starlette_dispatch import FromPath, RouteGroup

group = RouteGroup('/')


@group.get('/{value}')
def my_view(value: FromPath[str]) -> None:
    assert value is not None
```

If path value does not exist in `Request.path_parameters` then it will fail with error.
However, you can mark dependency as optional and then it will be `None` if path value does not exist.

```python
from starlette_dispatch import FromPath, RouteGroup

group = RouteGroup('/')


def my_view(value: FromPath[str] | None) -> None:
    assert value is None
```
