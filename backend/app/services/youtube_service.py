"""
YouTubeService — YouTube Data API v3 upload for the final automation step.

Uses the standard OAuth2 installed-app flow (one-time human consent, see
backend/app/api/youtube.py for the /oauth/start and /oauth/callback endpoints
that obtain and store a refresh token via SettingsRepository). Once connected,
uploads are fully automatic using the stored refresh token — no further human
interaction needed.
"""
import asyncio
from pathlib import Path
from typing import List, Optional

from app.core.logging import get_logger
from app.schemas.settings import YouTubeSettings

logger = get_logger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeConfigError(Exception):
    """Raised when YouTube OAuth credentials are missing/incomplete."""


class YouTubeService:
    def __init__(self, settings: YouTubeSettings) -> None:
        if not settings.client_id or not settings.client_secret or not settings.refresh_token:
            raise YouTubeConfigError(
                "YouTube is not connected — go to Settings → YouTube and connect your channel "
                "before running the youtube_upload pipeline step."
            )
        self.settings = settings

    def _build_client(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=None,
            refresh_token=self.settings.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.settings.client_id,
            client_secret=self.settings.client_secret,
            scopes=SCOPES,
        )
        return build("youtube", "v3", credentials=creds)

    async def upload_video(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: Optional[List[str]] = None,
        thumbnail_path: Optional[Path] = None,
        privacy_status: Optional[str] = None,
    ) -> str:
        """Resumable upload of `video_path` to the connected channel. Returns the
        new YouTube video id. Runs the blocking googleapiclient calls in a thread
        so this coroutine doesn't block the event loop."""
        privacy = privacy_status or self.settings.default_privacy_status or "unlisted"
        return await asyncio.to_thread(
            self._upload_sync, video_path, title, description, tags or [], thumbnail_path, privacy,
        )

    def _upload_sync(
        self,
        video_path: Path,
        title: str,
        description: str,
        tags: List[str],
        thumbnail_path: Optional[Path],
        privacy_status: str,
    ) -> str:
        from googleapiclient.http import MediaFileUpload

        youtube = self._build_client()
        body = {
            "snippet": {
                "title": title[:100] or "Untitled",
                "description": description[:5000],
                "tags": tags[:500],
                "categoryId": "27",  # Education — reasonable default for documentary/news content
            },
            "status": {"privacyStatus": privacy_status},
        }
        media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info("YouTube upload progress: %d%%", int(status.progress() * 100))

        video_id = response["id"]
        logger.info("Uploaded YouTube video %s (%s)", video_id, title)

        if thumbnail_path and Path(thumbnail_path).exists():
            try:
                youtube.thumbnails().set(
                    videoId=video_id, media_body=MediaFileUpload(str(thumbnail_path)),
                ).execute()
            except Exception as exc:
                logger.warning("Thumbnail upload failed for %s: %s", video_id, exc)

        return video_id
