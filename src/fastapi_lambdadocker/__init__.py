import asyncio
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from mangum import Mangum

app = FastAPI(title="fastapi-lambdadocker")


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello from fastapi-lambdadocker!"}


async def generate_story() -> AsyncIterator[str]:
    for value in range(1, 2000):
        yield f"{value}\n"
        await asyncio.sleep(0.05)


@app.get("/story/stream", response_class=StreamingResponse)
async def stream_story() -> StreamingResponse:
    return StreamingResponse(generate_story(), media_type="text/plain")


def main() -> None:
    import uvicorn

    uvicorn.run("fastapi_lambdadocker:app", host="localhost", port=8000)


handler = Mangum(app)
