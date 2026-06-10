from datetime import datetime, timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import bcrypt
import traceback
from sqlalchemy.exc import IntegrityError

from models.db import get_db, User
from models.schemas import AuthRequest, TokenResponse

router = APIRouter()
security = HTTPBearer()

SECRET_KEY = secrets.token_hex(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db=Depends(get_db)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
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
        )
        db.add(user)
        db.commit()
        token = create_access_token({"sub": user.id})
        return TokenResponse(access_token=token)
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