import base64
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi_lambdadocker.gmailmessages import (
    SCOPES,
    _authorize_user,
    gmailmessagesjson,
    listgmailmessages,
)


class GmailMessageTests(unittest.TestCase):
    @patch("fastapi_lambdadocker.gmailmessages.build")
    @patch("fastapi_lambdadocker.gmailmessages._authorize_user")
    def test_gmailmessagesjson_returns_content_for_only_five_messages(
        self, authorize: MagicMock, build_service: MagicMock
    ) -> None:
        messages = [{"id": f"message-{index}"} for index in range(7)]
        message_service = MagicMock()
        message_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": messages
        }
        message_service.users.return_value.messages.return_value.get.return_value.execute.side_effect = [
            {
                "snippet": f"Snippet {index}",
                "payload": {
                    "mimeType": "text/plain",
                    "body": {
                        "data": base64.urlsafe_b64encode(
                            f"Body {index}".encode()
                        ).decode()
                    },
                },
            }
            for index in range(5)
        ]
        build_service.return_value = message_service

        result = gmailmessagesjson()

        self.assertEqual(
            result,
            [
                {
                    "id": f"message-{index}",
                    "snippet": f"Snippet {index}",
                    "content": f"Body {index}",
                }
                for index in range(5)
            ],
        )
        message_service.users.return_value.messages.return_value.list.assert_called_once_with(
            userId="me", labelIds=["INBOX"], maxResults=5
        )
        self.assertEqual(
            message_service.users.return_value.messages.return_value.get.call_count,
            5,
        )
        message_service.users.return_value.messages.return_value.get.assert_any_call(
            userId="me", id="message-0", format="full"
        )
        authorize.assert_called_once_with()

    def test_gmailmessagesjson_returns_empty_list_when_inbox_is_empty(self) -> None:
        message_service = MagicMock()
        message_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {}

        with (
            patch("fastapi_lambdadocker.gmailmessages.build", return_value=message_service),
            patch("fastapi_lambdadocker.gmailmessages._authorize_user"),
        ):
            self.assertEqual(gmailmessagesjson(), [])
        message_service.users.return_value.messages.return_value.get.assert_not_called()

    @patch.dict(
        os.environ,
        {"GOOGLE_CLIENT_ID": "test-client-id", "GOOGLE_CLIENT_SECRET": "test-secret"},
        clear=True,
    )
    @patch("fastapi_lambdadocker.gmailmessages.load_dotenv")
    @patch("fastapi_lambdadocker.gmailmessages.webbrowser.open")
    @patch("fastapi_lambdadocker.gmailmessages.HTTPServer")
    @patch("fastapi_lambdadocker.gmailmessages.InstalledAppFlow.from_client_config")
    @patch("fastapi_lambdadocker.gmailmessages.build")
    def test_uses_environment_credentials_and_fetches_messages(
        self,
        build_service: MagicMock,
        create_flow: MagicMock,
        http_server: MagicMock,
        open_browser: MagicMock,
        load_environment: MagicMock,
    ) -> None:
        credentials = MagicMock()
        credentials.to_json.return_value = "serialized-oauth-token"
        flow = create_flow.return_value
        flow.authorization_url.return_value = (
            "https://accounts.google.com/authorize",
            "state",
        )
        flow.credentials = credentials
        server_context = http_server.return_value
        server = server_context.__enter__.return_value

        def receive_callback() -> None:
            handler_type = http_server.call_args.args[1]
            handler = object.__new__(handler_type)
            handler.path = "/oauth2callback?code=auth-code&state=state"
            handler.send_response = MagicMock()
            handler.send_header = MagicMock()
            handler.end_headers = MagicMock()
            handler.wfile = MagicMock()
            handler_type.do_GET(handler)

        server.handle_request.side_effect = receive_callback

        message_service = MagicMock()
        message_service.users.return_value.messages.return_value.list.return_value.execute.return_value = {
            "messages": [{"id": "message-1"}]
        }
        message_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
            "snippet": "Test message"
        }
        build_service.return_value = message_service

        with tempfile.TemporaryDirectory() as working_directory:
            previous_directory = os.getcwd()
            try:
                os.chdir(working_directory)
                with (
                    patch(
                        "fastapi_lambdadocker.gmailmessages._token_path",
                        return_value=Path(working_directory, "gmail-user-token.json"),
                    ),
                    contextlib.redirect_stdout(io.StringIO()) as output,
                ):
                    listgmailmessages()
            finally:
                os.chdir(previous_directory)

            self.assertFalse(Path(working_directory, "token.json").exists())
            self.assertEqual(
                Path(working_directory, "gmail-user-token.json").read_text(
                    encoding="utf-8"
                ),
                "serialized-oauth-token",
            )

        client_config, scopes = create_flow.call_args.args
        self.assertEqual(client_config["web"]["client_id"], "test-client-id")
        self.assertEqual(client_config["web"]["client_secret"], "test-secret")
        self.assertEqual(
            client_config["web"]["redirect_uris"],
            ["http://localhost:3000/oauth2callback"],
        )
        self.assertEqual(scopes, SCOPES)
        self.assertEqual(flow.redirect_uri, "http://localhost:3000/oauth2callback")
        flow.authorization_url.assert_called_once_with(
            access_type="offline", prompt="consent"
        )
        open_browser.assert_called_once_with(
            "https://accounts.google.com/authorize", new=1, autoraise=True
        )
        flow.fetch_token.assert_called_once_with(
            authorization_response=(
                "https://localhost:3000/oauth2callback?code=auth-code&state=state"
            )
        )
        load_environment.assert_called_once()
        build_service.assert_called_once_with("gmail", "v1", credentials=credentials)
        self.assertIn("Test message", output.getvalue())

    @patch.dict(
        os.environ,
        {"GOOGLE_CLIENT_ID": "test-client-id", "GOOGLE_CLIENT_SECRET": "test-secret"},
        clear=True,
    )
    @patch("fastapi_lambdadocker.gmailmessages.load_dotenv")
    @patch("fastapi_lambdadocker.gmailmessages.InstalledAppFlow.from_client_config")
    @patch("fastapi_lambdadocker.gmailmessages.Credentials.from_authorized_user_file")
    def test_valid_saved_token_skips_oauth_consent(
        self,
        load_credentials: MagicMock,
        create_flow: MagicMock,
        load_environment: MagicMock,
    ) -> None:
        saved_credentials = MagicMock()
        saved_credentials.valid = True
        load_credentials.return_value = saved_credentials

        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory, "gmail-user-token.json")
            token_path.write_text("saved-token", encoding="utf-8")
            with patch(
                "fastapi_lambdadocker.gmailmessages._token_path",
                return_value=token_path,
            ):
                result = _authorize_user()

        self.assertIs(result, saved_credentials)
        load_credentials.assert_called_once_with(str(token_path), SCOPES)
        create_flow.assert_not_called()

    @patch.dict(
        os.environ,
        {"GOOGLE_CLIENT_ID": "test-client-id", "GOOGLE_CLIENT_SECRET": "test-secret"},
        clear=True,
    )
    @patch("fastapi_lambdadocker.gmailmessages.load_dotenv")
    @patch("fastapi_lambdadocker.gmailmessages.Credentials.from_authorized_user_file")
    @patch("fastapi_lambdadocker.gmailmessages.Request")
    def test_expired_saved_token_refreshes_and_is_saved(
        self,
        create_request: MagicMock,
        load_credentials: MagicMock,
        load_environment: MagicMock,
    ) -> None:
        saved_credentials = MagicMock()
        saved_credentials.valid = False
        saved_credentials.expired = True
        saved_credentials.refresh_token = "refresh-token"
        saved_credentials.to_json.return_value = "refreshed-token"
        load_credentials.return_value = saved_credentials

        with tempfile.TemporaryDirectory() as directory:
            token_path = Path(directory, "gmail-user-token.json")
            token_path.write_text("old-token", encoding="utf-8")
            with patch(
                "fastapi_lambdadocker.gmailmessages._token_path",
                return_value=token_path,
            ):
                result = _authorize_user()

            self.assertEqual(
                token_path.read_text(encoding="utf-8"), "refreshed-token"
            )
            self.assertTrue(token_path.exists())

        self.assertIs(result, saved_credentials)
        saved_credentials.refresh.assert_called_once_with(create_request.return_value)

    @patch.dict(
        os.environ,
        {
            "GOOGLE_CLIENT_ID": "test-client-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
            "GOOGLE_REFRESH_TOKEN": "test-refresh-token",
            "GOOGLE_OAUTH_INTERACTIVE": "false",
        },
        clear=True,
    )
    @patch("fastapi_lambdadocker.gmailmessages.load_dotenv")
    @patch("fastapi_lambdadocker.gmailmessages._save_credentials")
    @patch("fastapi_lambdadocker.gmailmessages.Request")
    @patch("fastapi_lambdadocker.gmailmessages.Credentials")
    @patch("fastapi_lambdadocker.gmailmessages.InstalledAppFlow.from_client_config")
    @patch("fastapi_lambdadocker.gmailmessages._token_path")
    def test_refresh_token_environment_authorizes_without_browser_or_token_file(
        self,
        get_token_path: MagicMock,
        create_flow: MagicMock,
        create_credentials: MagicMock,
        create_request: MagicMock,
        save_credentials: MagicMock,
        load_environment: MagicMock,
    ) -> None:
        get_token_path.return_value.exists.return_value = False
        credentials = create_credentials.return_value

        result = _authorize_user()

        self.assertIs(result, credentials)
        create_credentials.assert_called_once_with(
            token=None,
            refresh_token="test-refresh-token",
            token_uri="https://oauth2.googleapis.com/token",
            client_id="test-client-id",
            client_secret="test-secret",
            scopes=SCOPES,
        )
        credentials.refresh.assert_called_once_with(create_request.return_value)
        get_token_path.assert_not_called()
        save_credentials.assert_not_called()
        create_flow.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "GOOGLE_CLIENT_ID": "test-client-id",
            "GOOGLE_CLIENT_SECRET": "test-secret",
            "GOOGLE_OAUTH_INTERACTIVE": "false",
        },
        clear=True,
    )
    @patch("fastapi_lambdadocker.gmailmessages.load_dotenv")
    @patch("fastapi_lambdadocker.gmailmessages.InstalledAppFlow.from_client_config")
    @patch("fastapi_lambdadocker.gmailmessages._token_path")
    def test_noninteractive_auth_requires_refresh_token(
        self,
        get_token_path: MagicMock,
        create_flow: MagicMock,
        load_environment: MagicMock,
    ) -> None:
        get_token_path.return_value.exists.return_value = False

        with self.assertRaisesRegex(RuntimeError, "GOOGLE_REFRESH_TOKEN"):
            _authorize_user()

        create_flow.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("fastapi_lambdadocker.gmailmessages._token_path")
    @patch("fastapi_lambdadocker.gmailmessages.load_dotenv")
    def test_missing_environment_credentials_raise_error(
        self, load_environment: MagicMock, get_token_path: MagicMock
    ) -> None:
        get_token_path.return_value.exists.return_value = False
        with self.assertRaisesRegex(
            RuntimeError, "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET"
        ):
            listgmailmessages()


if __name__ == "__main__":
    unittest.main()
