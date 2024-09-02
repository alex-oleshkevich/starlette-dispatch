from pathlib import Path

from starception import install_error_handler
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.templating import Jinja2Templates

this_dir = Path(__file__).parent
templates = Jinja2Templates(this_dir / "templates")


def index_view(request: Request) -> Response:
    return templates.TemplateResponse("index.html", {"request": request})


install_error_handler()
app = Starlette(
    debug=True,
    routes=[
        Route("/", index_view),
    ],
)
