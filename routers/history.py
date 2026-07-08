import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import uuid

from models.db import get_db, History
from models.schemas import HistoryCreate, HistoryResponse
import config
from jose import jwt, JWTError

router = APIRouter()
security = HTTPBearer()
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)


def format_created_at(value):
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return value.isoformat()
    except AttributeError:
        return str(value)


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
        return payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/api/v1/history", response_model=HistoryResponse)
async def create_history(
    payload: HistoryCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        entry = History(
            id=str(uuid.uuid4()),
            user_id=user_id,
            category=payload.category,
            record_time=payload.record_time,
            report_text=payload.report_text,
            is_pinned=payload.is_pinned,
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return HistoryResponse(
            id=entry.id,
            category=entry.category,
            record_time=entry.record_time,
            report_text=entry.report_text,
            created_at=format_created_at(entry.created_at),
            is_pinned=entry.is_pinned,
        )
    except Exception as exc:
        print(f"DB Error: {exc}")
        logger.exception("Failed to save history for user_id=%s", user_id)
        db.rollback()
        return HistoryResponse(
            id="",
            category=payload.category or "",
            record_time=payload.record_time or "",
            report_text=payload.report_text or "",
            created_at="",
            is_pinned=payload.is_pinned or False,
        )


def _build_history_response(entries: list[History]) -> list[HistoryResponse]:
    return [
        HistoryResponse(
            id=e.id,
            category=e.category,
            record_time=e.record_time,
            report_text=e.report_text,
            created_at=format_created_at(e.created_at),
            is_pinned=e.is_pinned,
        )
        for e in entries
    ]


@router.get("/api/v1/history", response_model=list[HistoryResponse])
async def list_history(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        entries = db.query(History).filter(History.user_id == user_id).order_by(History.created_at.desc()).all()
        return _build_history_response(entries)
    except Exception as exc:
        print(f"DB Error: {exc}")
        logger.exception("Failed to list history for user_id=%s", user_id)
        return []


@router.post("/api/v1/history/save", response_model=HistoryResponse)
async def save_history(
    payload: HistoryCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    return await create_history(payload=payload, user_id=user_id, db=db)


@router.post("/api/v1/history/list", response_model=list[HistoryResponse])
async def list_history_post(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    try:
        entries = db.query(History).filter(History.user_id == user_id).order_by(History.created_at.desc()).all()
        return _build_history_response(entries)
    except Exception as exc:
        print(f"DB Error: {exc}")
        logger.exception("Failed to list history for user_id=%s", user_id)
        return []
        # 🌟 新增：刪除歷史紀錄端點（極致防禦型設計，相容多種方法與傳參格式）
@router.get("/api/v1/history/delete")
@router.post("/api/v1/history/delete")
@router.delete("/api/v1/history/delete")
async def delete_history(
    request: Request,
    id: str = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    record_id = id
    if not record_id:
        try:
            body = await request.json()
            record_id = body.get("id")
        except Exception:
            pass
            
    if not record_id:
        raise HTTPException(status_code=400, detail="缺少紀錄 ID (id)")
        
    entry = db.query(History).filter(History.id == record_id, History.user_id == user_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="在資料庫中找不到該筆紀錄")
        
    db.delete(entry)
    db.commit()
    return {"status": "success", "message": "紀錄已成功刪除"}


# 🌟 新增：查看歷史紀錄詳情端點（同樣做雙重格式防禦）
@router.get("/api/v1/history/detail", response_model=HistoryResponse)
@router.post("/api/v1/history/detail", response_model=HistoryResponse)
async def get_history_detail(
    request: Request,
    id: str = Query(None),
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    record_id = id
    if not record_id:
        try:
            body = await request.json()
            record_id = body.get("id")
        except Exception:
            pass
            
    if not record_id:
        raise HTTPException(status_code=400, detail="缺少紀錄 ID (id)")
        
    entry = db.query(History).filter(History.id == record_id, History.user_id == user_id).first()
    if not entry:
        raise HTTPException(status_code=404, detail="找不到該筆紀錄的詳細內容")
        
    return HistoryResponse(
        id=entry.id,
        category=entry.category,
        record_time=entry.record_time,
        report_text=entry.report_text,
        created_at=format_created_at(entry.created_at),
        is_pinned=entry.is_pinned,
    )