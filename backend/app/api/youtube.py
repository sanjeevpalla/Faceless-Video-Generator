"""
YouTube OAuth API — one-time channel-connect flow for the youtube_upload pipeline step.

Endpoints:
  GET /youtube/oauth/start     — redirect to Google's consent screen
  GET /youtube/oauth/callback  — exchange the auth code, store the refresh token
  GET /youtube/oauth/status    — whether a channel is currently connected

Prerequisite: the user creates a Google Cloud OAuth 2.0 Client (type "Web application")
with this backend's callback URL added to "Authorized redirect URIs", then pastes the
client_id/client_secret into Settings → YouTube before hitting /oauth/start.
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from app.config import get_settings as get_app_settings
from app.core.dependencies import get_settings_repo
from app.repositories.settings_repo import SettingsRepository
from app.services.youtube_service import SCOPES

router = APIRouter()


def _redirect_uri() -> str:
    cfg = get_app_settings()
    return f"http://{cfg.HOST}:{cfg.PORT}/api/v1/youtube/oauth/callback"


@router.get("/oauth/start")
async def youtube_oauth_start(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Redirect the user's browser to Google's OAuth consent screen."""
    from google_auth_oauthlib.flow import Flow

    yt = await settings_repo.get_youtube_settings()
    if not yt.client_id or not yt.client_secret:
        raise HTTPException(
            status_code=400,
            detail="Set client_id and client_secret in Settings → YouTube first.",
        )

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": yt.client_id,
                "client_secret": yt.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=_redirect_uri(),
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true",
    )
    return RedirectResponse(auth_url)


@router.get("/oauth/callback")
async def youtube_oauth_callback(
    request: Request,
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    """Exchange the authorization code for tokens and persist the refresh token."""
    from google_auth_oauthlib.flow import Flow

    code = request.query_params.get("code")
    error = request.query_params.get("error")
    if error:
        raise HTTPException(status_code=400, detail=f"Google OAuth error: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Missing 'code' query parameter")

    yt = await settings_repo.get_youtube_settings()
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": yt.client_id,
                "client_secret": yt.client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=_redirect_uri(),
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    if not creds.refresh_token:
        raise HTTPException(
            status_code=400,
            detail="Google did not return a refresh token. Revoke this app's access at "
                   "https://myaccount.google.com/permissions and try connecting again "
                   "(consent must be re-granted to receive a new refresh token).",
        )

    await settings_repo.set_value("youtube.refresh_token", creds.refresh_token, category="youtube")

    return HTMLResponse(
        "<html><body><h3>YouTube channel connected.</h3>"
        "<p>You can close this tab and return to the app.</p></body></html>"
    )


@router.get("/oauth/status")
async def youtube_oauth_status(
    settings_repo: SettingsRepository = Depends(get_settings_repo),
):
    yt = await settings_repo.get_youtube_settings()
    return {"connected": bool(yt.refresh_token)}
