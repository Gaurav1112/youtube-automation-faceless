"""YouTube Data API v3 upload with OAuth 2.0.

OAuth token is cached at ~/.youtube_automation_token.pkl — browser
opens once for initial auth, then auto-refreshes silently.
"""

import os
import pickle
import sys
import time
from pathlib import Path


SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_FILE = Path.home() / ".youtube_automation_token.pkl"


def _build_client():
    """Return an authenticated YouTube API client."""
    import google.auth.transport.requests
    import google.oauth2.credentials
    import googleapiclient.discovery

    creds = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
    elif not creds or not creds.valid:
        client_id = os.environ.get("YOUTUBE_CLIENT_ID", "")
        client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
        if not client_id or not client_secret or "your_" in client_id:
            sys.exit(
                "ERROR: YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be set in .env\n"
                "  Guide: https://console.cloud.google.com → Enable YouTube Data API v3 → "
                "Create OAuth 2.0 Client ID (Desktop app)"
            )
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_config(
            {
                "installed": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uris": ["http://localhost"],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            SCOPES,
        )
        creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)
        print(f"  [upload] OAuth token saved to {TOKEN_FILE}")

    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def upload_video(video_path: Path, thumbnail_path: Path, metadata: dict) -> str:
    """Upload video + thumbnail to YouTube. Returns public URL."""
    import googleapiclient.errors
    import googleapiclient.http

    youtube = _build_client()

    body = {
        "snippet": {
            "title": metadata["title"],
            "description": metadata["description"],
            "tags": metadata.get("tags", []),
            "categoryId": metadata.get("category_id", "22"),
            "defaultLanguage": "en",
            "defaultAudioLanguage": "en",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
            "madeForKids": False,
            # Required by YouTube for AI-generated voice/content
            "containsSyntheticMedia": True,
        },
    }

    req = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=googleapiclient.http.MediaFileUpload(
            str(video_path), chunksize=512 * 1024, resumable=True
        ),
    )

    video_id = _resumable_upload(req)
    print(f"  [upload] Video live: https://youtu.be/{video_id}")

    if thumbnail_path.exists():
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=googleapiclient.http.MediaFileUpload(str(thumbnail_path)),
        ).execute()
        print("  [upload] Custom thumbnail applied")

    return f"https://youtu.be/{video_id}"


def _resumable_upload(req) -> str:
    import googleapiclient.errors
    retry = 0
    while True:
        try:
            _, response = req.next_chunk()
            if response and "id" in response:
                return response["id"]
        except googleapiclient.errors.HttpError as e:
            if e.resp.status not in (500, 502, 503, 504):
                raise
            retry += 1
            if retry > 8:
                raise RuntimeError(f"Upload failed after 8 retries: {e}")
            wait = min(2 ** retry, 60)
            print(f"  [upload] Server error, retry {retry}/8 in {wait}s...")
            time.sleep(wait)
