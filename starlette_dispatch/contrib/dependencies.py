import typing

from starlette_dispatch.injections import DependencyError, DependencyResolver, DependencySpec, ResolveContext

T = typing.TypeVar("T")


class PathParamValue(DependencyResolver):
    def __init__(self, param_name: str = "") -> None:
        self.param_name = param_name

    async def resolve(self, context: ResolveContext, spec: DependencySpec) -> typing.Any:
        param_name = self.param_name or spec.param_name
        value = context.connection.path_params.get(param_name)
        if value is None:
            if not spec.optional:
                message = f'Dependency "{spec.param_name}" has None value but it is not optional.'
                raise DependencyError(message)
            return None
        return spec.param_type(value)


FromPath = typing.Annotated[T, PathParamValue()]
