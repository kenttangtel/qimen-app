from datetime import datetime, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import bcrypt
import traceback
from sqlalchemy.exc import IntegrityError

from models.db import get_db, User
from models.schemas import AuthRequest, TokenResponse, UserResponse
import config

router = APIRouter()
security = HTTPBearer()

ALGORITHM = config.JWT_ALGORITHM


def get_secret_key() -> str:
    if not config.SECRET_KEY:
        raise RuntimeError("SECRET_KEY is required in environment variables for JWT authentication")
    return config.SECRET_KEY


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, get_secret_key(), algorithm=ALGORITHM)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db=Depends(get_db)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return user
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


@router.post("/api/v1/auth/register", response_model=TokenResponse)
async def register(request: AuthRequest, db=Depends(get_db)):
    try:
        user = User(
            id=secrets.token_hex(8),
            username=request.username,
            password_hash=hash_password(request.password),
            email=request.email,
            credits=5,             # 🌟 核心修正：新註冊免費會員直接大方送 5 點！
            membership_type="free" # 預設初始為免費會員
        )
        db.add(user) # [cite: 21]
        db.commit() # [cite: 21]
        token = create_access_token({"sub": user.id}) # [cite: 21]
        return TokenResponse(access_token=token) # [cite: 21]
    except IntegrityError:
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=400, detail="Username or email already exists")
    except Exception as exc:
        traceback.print_exc()
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to register user")


@router.post("/api/v1/auth/login", response_model=TokenResponse)
async def login(request: AuthRequest, db=Depends(get_db)):
    try:
        user = db.query(User).filter(User.username == request.username).first()
        if not user or not verify_password(request.password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        token = create_access_token({"sub": user.id})
        return TokenResponse(access_token=token)
    except HTTPException:
        raise
    except Exception as exc:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="Unable to login")


@router.get("/api/v1/auth/me", response_model=UserResponse)
def read_current_user(user: User = Depends(get_current_user)):
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        credits=user.credits,
        membership_type=user.membership_type,
        subscription_status=user.subscription_status,
        gender=user.gender,
        bazi_birth_time=user.bazi_birth_time,
        is_vip=user.membership_type in {"monthly", "lifetime"}, # 
        # 🌟 核心修正：將資料庫的 datetime 物件安全轉換為 ISO 字串傳給前端
        last_daily_fortune_at=user.last_daily_fortune_at.isoformat() if user.last_daily_fortune_at else None,
        last_weekly_shipan_at=user.last_weekly_shipan_at.isoformat() if user.last_weekly_shipan_at else None
    )