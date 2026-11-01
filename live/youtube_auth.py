"""One-time YouTube sign-in, so the stream can read its live chat.

    python youtube_auth.py

Needs client_secret.json: Google Cloud Console > APIs & Services > enable "YouTube Data API v3" >
Credentials > Create credentials > OAuth client ID > Desktop app > Download JSON, saved in this folder.
A browser opens; sign in with the channel's Google account and allow read-only access. This saves
token.json here (keep it private, never commit it). Run again if the sign-in is ever revoked.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gitalive.config import Config  # noqa: E402
from gitalive.youtube import SCOPES  # noqa: E402


def main() -> int:
    cfg = Config.load()
    if not cfg.google_client_secret.exists():
        print(f"Missing {cfg.google_client_secret}. See the instructions at the top of this file.")
        return 1
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(str(cfg.google_client_secret), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    if not creds.refresh_token:
        print("Google did not return a refresh token. Remove the app's access at myaccount.google.com/permissions and try again.")
        return 1
    cfg.token_file.write_text(creds.to_json(), encoding="utf-8")
    print(f"Saved {cfg.token_file}. The stream can now read live chat.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
