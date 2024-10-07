import typing

from starlette.requests import HTTPConnection, Request
from starlette.websockets import WebSocket

from starlette_dispatch.injections import DependencyError, DependencyResolver, DependencySpec

T = typing.TypeVar("T")


class PathParamValue(DependencyResolver):
    def __init__(self, param_name: str = "") -> None:
        self.param_name = param_name

    async def resolve(self, spec: DependencySpec, prepared_dependencies: dict[typing.Any, typing.Any]) -> typing.Any:
        param_name = self.param_name or spec.param_name
        conn: HTTPConnection | None = prepared_dependencies.get(Request, prepared_dependencies.get(WebSocket))
        if not conn:
            raise DependencyError(f'Cannot extract path parameter "{param_name}": no HTTP connection found.')

        value = conn.path_params.get(param_name)
        if value is None:
            if not spec.optional:
                message = f'Dependency "{spec.param_name}" has None value but it is not optional.'
                raise DependencyError(message)
            return None
        return spec.param_type(value)


FromPath = typing.Annotated[T, PathParamValue()]
