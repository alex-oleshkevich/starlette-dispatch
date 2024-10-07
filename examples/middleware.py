from starlette.authentication import SimpleUser
from starlette.types import ASGIApp, Receive, Scope, Send


class ProvideUser:
    def __init__(self, app: ASGIApp, user: SimpleUser) -> None:
        self.app = app
        self.user = user

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        scope["user"] = self.user
        await self.app(scope, receive, send)
