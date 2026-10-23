import asyncio
from collections.abc import AsyncIterator
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from fastmcp import FastMCP
from mangum import Mangum
from fastapi_lambdadocker.gmailmessages import gmailmessagesjson


mcp = FastMCP("gmailotp-mcpserver")


@mcp.tool
def get_otp_messages() -> list[dict[str, str]]:
    """Return recent Gmail inbox messages."""
    return gmailmessagesjson()


mcp_app = mcp.http_app(path="/", stateless_http=True)
app = FastAPI(title="gmailotp-mcpserver", lifespan=mcp_app.lifespan)
app.mount("/mcp", mcp_app)


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


@app.get("/stream", response_class=StreamingResponse)
async def stream() -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        for i in range(1, 4000):
            if i > 2:
                await asyncio.sleep(0.01)
            yield f"chunk {i}\n"

    return StreamingResponse(generate(), media_type="text/plain")


@app.get("/otp")
def otpmessage() -> list[dict[str, str]]:
    try:
        return gmailmessagesjson()
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def main() -> None:
    import uvicorn
    uvicorn.run("fastapi_lambdadocker:app", host="localhost", port=8000)


handler = Mangum(app)
