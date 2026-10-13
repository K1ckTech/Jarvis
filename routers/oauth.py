import os
import json
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional

from models.schemas import OAuthConfig, GoogleExchangeRequest
from core.google_drive_auth import (
    GOOGLE_DRIVE_PROVIDER,
    get_google_drive_status,
    generate_google_auth_url,
    exchange_code_for_tokens,
    save_google_drive_config,
    read_oauth_config,
    write_oauth_config
)

router = APIRouter()

@router.get("/status/{provider}")
def get_oauth_status(provider: str):
    if provider == GOOGLE_DRIVE_PROVIDER:
        return get_google_drive_status()

    data = read_oauth_config()
    pdata = data.get(provider, {})
    return {
        "configured": bool(pdata.get("client_id")),
        "connected": bool(pdata.get("access_token")),
        "client_id": pdata.get("client_id", "")
    }

@router.post("/config")
def save_oauth_config(config: OAuthConfig):
    if config.provider == GOOGLE_DRIVE_PROVIDER:
        if not config.client_id or not config.client_secret:
            raise HTTPException(status_code=400, detail="Client ID and Client Secret are required.")
        
        if config.auth_code and config.redirect_uri:
            try:
                exchange_code_for_tokens(
                    code=config.auth_code,
                    redirect_uri=config.redirect_uri,
                    client_id=config.client_id,
                    client_secret=config.client_secret
                )
                return {"status": "success", "message": "Tokens exchanged and saved successfully."}
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Token exchange failed: {str(e)}")

        save_google_drive_config(
            client_id=config.client_id,
            client_secret=config.client_secret,
            refresh_token=config.refresh_token,
            access_token=config.access_token
        )
        return {"status": "success"}

    data = read_oauth_config()
    data[config.provider] = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "access_token": config.client_secret
    }
    write_oauth_config(data)
    return {"status": "success"}

@router.get("/google/auth-url")
def get_google_auth_url(redirect_uri: str, client_id: Optional[str] = None):
    try:
        url = generate_google_auth_url(redirect_uri=redirect_uri, client_id=client_id)
        return {"auth_url": url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/google/callback", response_class=HTMLResponse)
def google_callback(request: Request, code: Optional[str] = None, error: Optional[str] = None):
    if error:
        return HTMLResponse(
            content=f"""<!DOCTYPE html>
            <html lang="ja"><head><meta charset="utf-8"><title>OAuth Error</title>
            <style>body{{font-family:sans-serif;background:#090d16;color:#f87171;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}}</style>
            </head><body><div style="text-align:center;"><h2>認証エラー</h2><p>{error}</p></div></body></html>""",
            status_code=400
        )
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code missing.")

    redirect_uri = str(request.url).split("?")[0]
    try:
        exchange_code_for_tokens(code=code, redirect_uri=redirect_uri)
    except Exception as e:
        return HTMLResponse(
            content=f"""<!DOCTYPE html>
            <html lang="ja"><head><meta charset="utf-8"><title>OAuth Error</title>
            <style>body{{font-family:sans-serif;background:#090d16;color:#f87171;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}}</style>
            </head><body><div style="text-align:center;"><h2>トークン取得エラー</h2><p>{str(e)}</p></div></body></html>""",
            status_code=400
        )

    return HTMLResponse(
        content="""<!DOCTYPE html>
        <html lang="ja"><head><meta charset="utf-8"><title>連携完了</title>
        <style>body{font-family:sans-serif;background:#090d16;color:#34d399;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}</style>
        </head><body>
        <div style="text-align:center;">
            <h2>Google Drive 連携完了</h2>
            <p style="color:#94a3b8;font-size:14px;">認証が正常に完了しました。このタブを閉じてダッシュボードに戻ってください。</p>
            <script>
                if (window.opener) {
                    window.opener.postMessage({ type: 'oauth_connected', provider: 'Google Drive' }, '*');
                    setTimeout(() => window.close(), 1500);
                }
            </script>
        </div>
        </body></html>"""
    )

@router.post("/google/exchange")
def exchange_google_code_endpoint(req: GoogleExchangeRequest):
    try:
        tokens = exchange_code_for_tokens(
            code=req.code,
            redirect_uri=req.redirect_uri,
            client_id=req.client_id,
            client_secret=req.client_secret
        )
        return {"status": "success", "tokens": {k: v for k, v in tokens.items() if k != "refresh_token"}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post('/disconnect/{provider}')
def disconnect_oauth(provider: str):
    data = read_oauth_config()
    if provider in data:
        del data[provider]
        write_oauth_config(data)
    return {'status': 'success'}
