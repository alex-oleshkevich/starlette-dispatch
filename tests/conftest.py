import pytest

from starlette_dispatch.route_group import RouteGroup


@pytest.fixture
def route_group() -> RouteGroup:
    return RouteGroup()
