from datetime import datetime, timedelta
import secrets
import string
import smtplib
import traceback
import os
from email.mime.text import MIMEText
from email.header import Header

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import bcrypt
from pydantic import BaseModel
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
            credits=5,             # 🌟 新註冊免費會員直接送 5 點！
            membership_type="free" # 預設初始為免費會員
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
        is_vip=user.membership_type in {"monthly", "lifetime"},
        last_daily_fortune_at=user.last_daily_fortune_at.isoformat() if user.last_daily_fortune_at else None,
        last_weekly_shipan_at=user.last_weekly_shipan_at.isoformat() if user.last_weekly_shipan_at else None
    )


# ==========================================
# 🔐 忘記密碼與密碼重置核心完全體模組
# ==========================================

# 🌟 萬能相容模型：防禦一切前端新舊欄位打架，徹底消滅 422 錯誤
class ForgotPasswordRequest(BaseModel):
    account: str = ""
    email: str = ""
    username: str = ""
    password: str = ""


# 🌟 重置密碼驗證結構
class ResetPasswordRequest(BaseModel):
    account: str
    code: str
    new_password: str


@router.post("/api/v1/auth/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, db=Depends(get_db)):
    import os
    import urllib.request
    import urllib.error
    import json
    
    search_target = request.account or request.email or request.username
    if not search_target:
        raise HTTPException(status_code=400, detail="請輸入帳號或電子信箱")

    user = db.query(User).filter((User.email == search_target) | (User.username == search_target)).first()
    if not user or not user.email:
        raise HTTPException(status_code=404, detail="找不到該用戶或該帳號未綁定信箱")

    # 1. 生成 6 位數驗證碼
    code = "".join(secrets.choice(string.digits) for _ in range(6))
    user.reset_code = code
    user.reset_code_expires = datetime.utcnow() + timedelta(minutes=15)
    db.commit()

    # 2. 讀取環境變數
    resend_api_key = os.environ.get("RESEND_API_KEY")
    if not resend_api_key:
        raise HTTPException(status_code=500, detail="後端未偵測到 RESEND_API_KEY 環境變數")
    
    print(f"⚡ [奇門發信] 準備透過 Resend HTTP API 發送驗證碼至: {user.email}")

    mail_body = f"""
    <h3>【奇門大師】密碼重置驗證碼</h3>
    <p>您好，系統收到您重置密碼的請求。</p>
    <p>您的 6 位數驗證碼為：<b style='font-size: 24px; color: #4f46e5; letter-spacing: 4px;'>{code}</b></p>
    <p>請於 15 分鐘內在網頁畫面上輸入此驗證碼。若非本人操作，請忽略此郵件。</p>
    """
    
    try:
        # 免費版固定發信人格式
        payload = {
            "from": "onboarding@resend.dev",
            "to": [user.email],
            "subject": "【奇門大師】安全驗證碼",
            "html": mail_body
        }
        
        # 3. 🌟 終極修正：加入偽裝瀏覽器的 User-Agent，並強行剔除 Token 前後可能誤複製的空格
        headers = {
            "Authorization": f"Bearer {resend_api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        req = urllib.request.Request(
            "https://api.resend.com/emails",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )
        
        print("⚡ [奇門發信] 正在向 Resend 伺服器發射 HTTP 請求...")
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            print(f"⚡ [奇門發信] 🎉 Resend 響應成功: {res_body}")
            
        return {"status": "success", "message": "驗證碼已成功送達您的信箱"}
        
    except urllib.error.HTTPError as http_err:
        # 🌟 偵錯終極外掛：如果被拒絕，強行把 Resend 官方回傳的「真心自白黑盒子」拆開印在日誌上！
        error_reply = http_err.read().decode("utf-8")
        print(f"❌ [奇門發信] Resend 拒絕連線！官方真實回應內容為: {error_reply}")
        raise HTTPException(status_code=400, detail=f"發信服務商拒絕，原因: {error_reply}")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"HTTP 管道發信失敗: {str(e)}")

@router.post("/api/v1/auth/reset-password")
async def reset_password(request: ResetPasswordRequest, db=Depends(get_db)):
    # 同時相容用帳號或信箱查詢要求改密碼的人
    user = db.query(User).filter((User.email == request.account) | (User.username == request.account)).first()
    if not user:
        raise HTTPException(status_code=404, detail="找不到該用戶")
    
    # 驗證碼安全防禦檢查
    if not user.reset_code or user.reset_code != request.code:
        raise HTTPException(status_code=400, detail="安全驗證碼不正確")
        
    if not user.reset_code_expires or user.reset_code_expires < datetime.utcnow():
        raise HTTPException(status_code=400, detail="驗證碼已超過 15 分鐘時效，請重新獲取")
        
    # 成功過關，強制進行新密碼改運雜湊
    user.password_hash = hash_password(request.new_password)
    
    # 清空金鑰欄位，防止一碼多用
    user.reset_code = None
    user.reset_code_expires = None
    db.commit()
    
    return {"status": "success", "message": "密碼修改成功！新磁場已同步，請重新登入。"}