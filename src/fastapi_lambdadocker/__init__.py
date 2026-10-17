from fastapi import FastAPI
from fastapi.responses import Response
from mangum import Mangum

app = FastAPI(title="fastapi-lambdadocker")


@app.get("/health")
@app.get("/")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/home")
@app.get("/story/stream/home")
async def root() -> dict[str, str]:
    return {"message": "Hello from fastapi-lambdadocker!"}


@app.get("/numbers", response_class=Response)
async def numbers() -> Response:
    data = "".join(f"{i}\n" for i in range(1, 2000))
    return Response(content=data, media_type="text/plain")


def main() -> None:
    import uvicorn

    uvicorn.run("fastapi_lambdadocker:app", host="localhost", port=8000)


handler = Mangum(app)
