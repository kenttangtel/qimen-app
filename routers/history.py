from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
import uuid

from models.db import get_db, History
from models.schemas import HistoryCreate, HistoryResponse
from routers.auth import SECRET_KEY, ALGORITHM
from jose import jwt, JWTError

router = APIRouter()
security = HTTPBearer()


def get_current_user_id(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/api/v1/history", response_model=HistoryResponse)
async def create_history(
    payload: HistoryCreate,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
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
        created_at=entry.created_at.isoformat(),
        is_pinned=entry.is_pinned,
    )


@router.get("/api/v1/history", response_model=list[HistoryResponse])
async def list_history(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    entries = db.query(History).filter(History.user_id == user_id).order_by(History.created_at.desc()).all()
    return [
        HistoryResponse(
            id=e.id,
            category=e.category,
            record_time=e.record_time,
            report_text=e.report_text,
            created_at=e.created_at.isoformat(),
            is_pinned=e.is_pinned,
        )
        for e in entries
    ]