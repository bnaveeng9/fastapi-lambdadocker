import unittest

from fastapi_lambdadocker import handler


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


if __name__ == "__main__":
    unittest.main()
