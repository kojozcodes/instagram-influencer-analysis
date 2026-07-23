"""FastAPI application: input screen, analysis execution, result + Excel download."""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from .config import settings
from .excel import build_excel_bytes
from .normalize import MAX_ACCOUNTS, normalize_input
from .pipeline import analyze_accounts
from .storage import save_report, load_report

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

    # Generate the Excel file and store it for download (backend-agnostic).
    file_id = uuid.uuid4().hex
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"influencer_analysis_{stamp}.xlsx"
    save_report(file_id, build_excel_bytes(rows), filename)

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
            "file_id": file_id,
            "rejected": norm.rejected,
        },
    )


@app.get("/download/{file_id}")
def download(file_id: str):
    # Guard against path traversal: only hex ids are valid.
    if not file_id or not all(c in "0123456789abcdef" for c in file_id):
        return HTMLResponse("不正なリクエストです", status_code=400)
    result = load_report(file_id)
    if result is None:
        return HTMLResponse("ファイルが見つかりません（有効期限切れの可能性があります）", status_code=404)
    data, filename = result
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/healthz")
def healthz():
    return {"status": "ok", "provider": settings.provider}
