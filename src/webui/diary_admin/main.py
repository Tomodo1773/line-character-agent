"""日記の管理 UI（ADR-0001 §7）。

閲覧・日付変更・削除だけを提供する。作成と本文の編集は LINE 経由が本線なので持たない。
ホスト先の Azure Container Apps Express はシークレット管理も Easy Auth も未対応のため、
UI 自体の保護は環境変数の資格情報による Basic 認証で行い、全ルートに一律で適用する。
"""

import datetime
import secrets
from pathlib import Path
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request, status
from fastapi import Path as PathParam
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.templating import Jinja2Templates

from diary_admin import cosmos
from diary_admin.config import create_logger, get_settings, log_safe

logger = create_logger(__name__)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# 入口でユーザ入力の形式を制約する。ID は URL やログにそのまま流れるため、
# 改行やスラッシュを含み得ない安全な文字種に限定する（オープンリダイレクト対策も兼ねる）。
EntryId = Annotated[str, PathParam(pattern=r"^[A-Za-z0-9_.:-]+$")]
Month = Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}$")]


def require_admin(credentials: Annotated[HTTPBasicCredentials, Depends(HTTPBasic())]) -> None:
    """Basic 認証。管理者は1名なので、環境変数のユーザ名とパスワードを定数時間で照合する。"""
    settings = get_settings()
    correct_user = secrets.compare_digest(credentials.username.encode(), settings.admin_user.encode())
    correct_password = secrets.compare_digest(credentials.password.encode(), settings.admin_password.encode())
    if not (correct_user and correct_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "認証に失敗しました", headers={"WWW-Authenticate": "Basic"})


app = FastAPI(title="日記管理", dependencies=[Depends(require_admin)])


def _find_entry(entry_id: str) -> dict[str, Any]:
    entry = cosmos.read_entry(entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "日記が見つかりません")
    return entry


@app.get("/")
def index(request: Request, month: Month = None):
    """日記の一覧。`month`（`YYYY-MM`）が指定されていればその月に絞る。"""
    logger.info("index が呼び出されました: month=%s", log_safe(month))
    context = {"entries": cosmos.list_entries(month), "months": cosmos.list_months(), "selected_month": month}
    return templates.TemplateResponse(request, "index.html", context)


@app.get("/entries/{entry_id}")
def detail(request: Request, entry_id: EntryId):
    """日記の本文表示と、日付変更・削除の操作。"""
    logger.info("detail が呼び出されました: id=%s", log_safe(entry_id))
    return templates.TemplateResponse(request, "entry.html", {"entry": _find_entry(entry_id)})


@app.post("/entries/{entry_id}/date")
def change_date(entry_id: EntryId, date: Annotated[datetime.date, Form()]):
    """日記の日付を変更する。"""
    cosmos.change_date(_find_entry(entry_id), date)
    return RedirectResponse(f"/entries/{quote(entry_id, safe='')}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/entries/{entry_id}/delete")
def delete(entry_id: EntryId):
    """日記を削除する。"""
    cosmos.delete_entry(_find_entry(entry_id))
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
