"""FastAPI application: input screen, analysis execution, result + Excel download.

The Excel is delivered inline (base64 data URI in the result page), so there is
no server-side file storage and the app is fully stateless — it runs identically
on a normal server and on serverless platforms (Vercel) with no external store.
"""
from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .config import settings
from .excel import build_excel_bytes
from .normalize import MAX_ACCOUNTS, normalize_input
from .pipeline import analyze_accounts

app = FastAPI(title="Instagram Influencer Analysis")
_templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return _templates.TemplateResponse(
        "index.html",
        {"request": request, "max_accounts": MAX_ACCOUNTS, "provider": settings.provider},
    )


@app.post("/analyze", response_class=HTMLResponse)
def analyze(request: Request, accounts: str = Form("")):
    norm = normalize_input(accounts)

    if norm.over_limit:
        return _templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "max_accounts": MAX_ACCOUNTS,
                "provider": settings.provider,
                "error": f"アカウントは最大{MAX_ACCOUNTS}件までです。件数を減らして再度お試しください。",
                "previous": accounts,
            },
            status_code=400,
        )

    if not norm.accounts:
        return _templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "max_accounts": MAX_ACCOUNTS,
                "provider": settings.provider,
                "error": "有効なアカウントが入力されていません。",
                "rejected": norm.rejected,
                "previous": accounts,
            },
            status_code=400,
        )

    rows = analyze_accounts(norm.accounts)

    # Generate the Excel and embed it in the result page as a base64 data URI,
    # so the download needs no server-side storage (stateless / serverless-safe).
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"influencer_analysis_{stamp}.xlsx"
    xlsx_b64 = base64.b64encode(build_excel_bytes(rows)).decode("ascii")

    success = sum(1 for r in rows if r.status == "成功")
    failed = len(rows) - success

    return _templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "rows": rows,
            "success": success,
            "failed": failed,
            "total": len(rows),
            "xlsx_b64": xlsx_b64,
            "download_filename": filename,
            "rejected": norm.rejected,
        },
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok", "provider": settings.provider}
