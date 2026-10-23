import base64
import os
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _token_path() -> Path:
    configured_path = os.environ.get("GOOGLE_TOKEN_FILE")
    if configured_path:
        return Path(configured_path)
    return Path.home() / ".gmail-mcp" / "gmail-user-token.json"


def _save_credentials(credentials: Credentials) -> None:
    token_path = _token_path()
    token_path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        token_path.parent.chmod(0o700)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    if os.name != "nt":
        token_path.chmod(0o600)


def _authorize_user() -> Credentials:
    load_dotenv(Path(__file__).with_name(".env"))

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN")
    if refresh_token:
        if not client_id or not client_secret:
            raise RuntimeError(
                "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET with "
                "GOOGLE_REFRESH_TOKEN to authorize Gmail access."
            )
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=SCOPES,
        )
        creds.refresh(Request())
        return creds

    token_path = _token_path()
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if creds.valid:
            return creds
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_credentials(creds)
            return creds

    interactive_auth = os.environ.get(
        "GOOGLE_OAUTH_INTERACTIVE", "true"
    ).strip().lower()
    if interactive_auth not in {"1", "true", "yes", "on"}:
        raise RuntimeError(
            "Non-interactive Gmail authorization requires GOOGLE_REFRESH_TOKEN "
            "and GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET, or a saved token file "
            "with a refresh token."
        )

    if not client_id or not client_secret:
        raise RuntimeError(
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to authorize Gmail access."
        )

    callback_uri = "http://localhost:3000/oauth2callback"
    client_config = {
        "web": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [callback_uri],
        }
    }
    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    flow.redirect_uri = callback_uri
    auth_url, _ = flow.authorization_url(access_type="offline", prompt="consent")
    authorization_response: list[str] = []

    class OAuthCallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if urlsplit(self.path).path == "/oauth2callback":
                authorization_response.append(self.path)
                self.send_response(200)
                message = b"Gmail authorization complete. You may close this tab."
            else:
                self.send_response(404)
                message = b"Waiting for Gmail authorization callback."

            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(message)))
            self.end_headers()
            self.wfile.write(message)

    with HTTPServer(("localhost", 3000), OAuthCallbackHandler) as server:
        print(f"Please visit this URL to authorize Gmail access: {auth_url}")
        webbrowser.open(auth_url, new=1, autoraise=True)
        while not authorization_response:
            server.handle_request()

    response_url = f"https://localhost:3000{authorization_response[0]}"
    flow.fetch_token(authorization_response=response_url)
    _save_credentials(flow.credentials)
    return flow.credentials


def listgmailmessages():
    """Shows basic usage of the Gmail API.
    Lists the user's Gmail messages.
    """
    try:
        creds = _authorize_user()
        # Call the Gmail API
        service = build("gmail", "v1", credentials=creds)
        results = (
            service.users().messages().list(userId="me", labelIds=["INBOX"]).execute()
        )
        messages = results.get("messages", [])

        if not messages:
            print("No messages found.")
            return

        print("Messages:")
        for message in messages:
            print(f'Message ID: {message["id"]}')
            msg = (
                service.users().messages().get(userId="me", id=message["id"]).execute()
            )
            print(f'  Subject: {msg["snippet"]}')

    except HttpError as error:
        # TODO(developer) - Handle errors from gmail API.
        print(f"An error occurred: {error}")



def _decode_message_body(payload: dict[str, object]) -> str:
    """Extract and decode the plain-text body, falling back to HTML when needed."""
    bodies: dict[str, list[str]] = {"text/plain": [], "text/html": []}

    def collect_parts(part: dict[str, object]) -> None:
        mime_type = part.get("mimeType")
        body = part.get("body")
        if isinstance(body, dict) and isinstance(body.get("data"), str):
            if mime_type in bodies:
                bodies[mime_type].append(body["data"])

        parts = part.get("parts")
        if isinstance(parts, list):
            for child in parts:
                if isinstance(child, dict):
                    collect_parts(child)

    collect_parts(payload)
    encoded_bodies = bodies["text/plain"] or bodies["text/html"]
    decoded = []
    for body in encoded_bodies:
        padded_body = body + "=" * (-len(body) % 4)
        decoded.append(base64.urlsafe_b64decode(padded_body).decode("utf-8"))
    return "\n".join(decoded)


def gmailmessagesjson() -> list[dict[str, str]]:
    """Return the five most recent inbox messages with their snippets and content."""
    creds = _authorize_user()
    service = build("gmail", "v1", credentials=creds)
    results = (
        service.users()
        .messages()
        .list(userId="me", labelIds=["INBOX"], maxResults=5)
        .execute()
    )
    messages = results.get("messages", [])

    response = []
    for message in messages[:5]:
        message_id = message["id"]
        details = (
            service.users()
            .messages()
            .get(userId="me", id=message_id, format="full")
            .execute()
        )
        payload = details.get("payload", {})
        response.append(
            {
                "id": message_id,
                "snippet": details.get("snippet", ""),
                "content": _decode_message_body(payload),
            }
        )
        print(response)
    return response



if __name__ == "__main__":
    #listgmailmessages()
    gmailmessagesjson()