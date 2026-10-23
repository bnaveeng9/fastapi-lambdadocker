import asyncio
import json
import unittest
from unittest.mock import patch

from fastapi.responses import StreamingResponse
from fastapi.testclient import TestClient
from httpx2 import Response as HttpResponse

from fastapi_lambdadocker import app, handler, stream


def http_api_event(path: str) -> dict[str, object]:
    return {
        "version": "2.0",
        "routeKey": f"GET {path}",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "example.com", "x-forwarded-proto": "https"},
        "requestContext": {
            "accountId": "123456789012",
            "apiId": "testapi",
            "domainName": "testapi.execute-api.us-east-1.amazonaws.com",
            "domainPrefix": "testapi",
            "http": {
                "method": "GET",
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "test",
            },
            "requestId": "test-request",
            "routeKey": f"GET {path}",
            "stage": "$default",
            "time": "17/Oct/2026:00:00:00 +0000",
            "timeEpoch": 1792195200000,
        },
        "body": None,
        "isBase64Encoded": False,
    }


class ApiRouteTests(unittest.TestCase):
    def test_root_returns_health_status(self) -> None:
        response = handler(http_api_event("/"), None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["body"], '{"status":"ok"}')

    def test_health_route_returns_health_status(self) -> None:
        response = handler(http_api_event("/health"), None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(response["body"], '{"status":"ok"}')

    def test_story_path_returns_json_greeting(self) -> None:
        response = handler(http_api_event("/story/stream/home"), None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(
            response["body"], '{"message":"Hello from fastapi-lambdadocker!"}'
        )
        self.assertTrue(
            response["headers"]["content-type"].startswith("application/json")
        )

    def test_existing_routes_remain_available(self) -> None:
        home_response = handler(http_api_event("/home"), None)
        numbers_response = handler(http_api_event("/numbers"), None)

        self.assertEqual(home_response["statusCode"], 200)
        self.assertEqual(
            home_response["body"], '{"message":"Hello from fastapi-lambdadocker!"}'
        )
        self.assertEqual(numbers_response["statusCode"], 200)
        self.assertEqual(
            numbers_response["body"],
            "".join(f"{i}\n" for i in range(1, 2000)),
        )
        self.assertEqual(
            numbers_response["headers"]["content-type"],
            "text/plain; charset=utf-8",
        )

    def test_stream_route_yields_incremental_plain_text_chunks(self) -> None:
        response = asyncio.run(stream())

        self.assertIsInstance(response, StreamingResponse)
        self.assertTrue(response.media_type.startswith("text/plain"))

        async def collect_chunks() -> list[str]:
            return [chunk async for chunk in response.body_iterator]

        self.assertEqual(
            asyncio.run(collect_chunks()),
            ["chunk 1\n", "chunk 2\n", "chunk 3\n"],
        )

    def test_otp_route_returns_gmail_messages(self) -> None:
        messages = [{"id": "message-1", "snippet": "OTP", "content": "123456"}]
        with patch("fastapi_lambdadocker.gmailmessagesjson", return_value=messages):
            response = handler(http_api_event("/otp"), None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(
            response["body"],
            '[{"id":"message-1","snippet":"OTP","content":"123456"}]',
        )

    def test_otp_route_returns_service_unavailable_without_oauth_config(self) -> None:
        with patch(
            "fastapi_lambdadocker.gmailmessagesjson",
            side_effect=RuntimeError("Set GOOGLE_REFRESH_TOKEN to authorize Gmail."),
        ):
            response = handler(http_api_event("/otp"), None)

        self.assertEqual(response["statusCode"], 503)
        self.assertEqual(
            response["body"],
            '{"detail":"Set GOOGLE_REFRESH_TOKEN to authorize Gmail."}',
        )

    def test_mcp_endpoint_exposes_otp_tool(self) -> None:
        with TestClient(app) as client:
            initialize_response = client.post(
                "/mcp",
                headers={
                    "accept": "application/json, text/event-stream",
                    "content-type": "application/json",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "test-client", "version": "1.0"},
                    },
                },
            )
            headers = {
                "accept": "application/json, text/event-stream",
                "content-type": "application/json",
                "mcp-protocol-version": "2025-03-26",
            }
            client.post(
                "/mcp",
                headers=headers,
                json={"jsonrpc": "2.0", "method": "notifications/initialized"},
            )
            tools_response = client.post(
                "/mcp",
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                },
            )
            messages = [
                {"id": "message-1", "snippet": "OTP", "content": "123456"}
            ]
            with patch(
                "fastapi_lambdadocker.gmailmessagesjson",
                return_value=messages,
            ):
                tool_response = client.post(
                    "/mcp",
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 3,
                        "method": "tools/call",
                        "params": {
                            "name": "get_otp_messages",
                            "arguments": {},
                        },
                    },
                )

        self.assertEqual(initialize_response.status_code, 200)
        self.assertEqual(
            self._mcp_message(initialize_response)["result"]["serverInfo"]["name"],
            "fastapi-lambdadocker",
        )
        self.assertNotIn("mcp-session-id", initialize_response.headers)
        self.assertEqual(tools_response.status_code, 200)
        self.assertIn(
            "get_otp_messages",
            [
                tool["name"]
                for tool in self._mcp_message(tools_response)["result"]["tools"]
            ],
        )
        self.assertEqual(tool_response.status_code, 200)
        self.assertIn(
            "message-1",
            self._mcp_message(tool_response)["result"]["content"][0]["text"],
        )
        self.assertIn(
            "123456",
            self._mcp_message(tool_response)["result"]["content"][0]["text"],
        )

    @staticmethod
    def _mcp_message(response: HttpResponse) -> dict[str, object]:
        data_line = next(
            line.removeprefix("data: ")
            for line in response.text.splitlines()
            if line.startswith("data: ")
        )
        return json.loads(data_line)


if __name__ == "__main__":
    unittest.main()
