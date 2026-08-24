"""Fábrica da aplicação FastAPI."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from deep_research.errors import ApplicationError
from deep_research.routes import router


def create_app() -> FastAPI:
    application = FastAPI(
        title="API de pesquisa documental e qualidade de dados",
        description=(
            "Pesquisa adaptativa com triagem, esclarecimento, verificação de "
            "suficiência e refinamento em documentos, além de auditoria automática "
            "e explicável da qualidade de arquivos CSV."
        ),
        version="5.0.0",
    )
    application.include_router(router)

    @application.exception_handler(ApplicationError)
    async def handle_application_error(
        request: Request,
        error: ApplicationError,
    ) -> JSONResponse:
        del request
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": error.detail},
        )

    return application


app = create_app()
