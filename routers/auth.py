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


# 🌟 終極黑科技：全域記憶體金鑰保險箱！
# 用來繞過資料庫缺少 reset_code 欄位的死穴，直接安全存放在伺服器記憶體中
RESET_CODES = {}  # 結構：{ "user_id": {"code": "123456", "expires": datetime} }


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
            credits=5,             
            membership_type="free" 
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

class ForgotPasswordRequest(BaseModel):
    account: str = ""
    email: str = ""
    username: str = ""
    password: str = ""


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
    
    # 🌟 修正點：改存入記憶體保險箱，用用戶的唯一 ID 當鑰匙
    RESET_CODES[user.id] = {
        "code": code,
        "expires": datetime.utcnow() + timedelta(minutes=15)
    }

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
        payload = {
            "from": "onboarding@resend.dev",
            "to": [user.email],
            "subject": "【奇門大師】安全驗證碼",
            "html": mail_body
        }
        
        headers = {
            "Authorization": f"Bearer {resend_api_key.strip()}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
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
        error_reply = http_err.read().decode("utf-8")
        print(f"❌ [奇門發信] Resend 拒絕連線！官方真實回應內容為: {error_reply}")
        raise HTTPException(status_code=400, detail=f"發信服務商拒絕，原因: {error_reply}")
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"HTTP 管道發信失敗: {str(e)}")


@router.post("/api/v1/auth/reset-password")
async def reset_password(request: ResetPasswordRequest, db=Depends(get_db)):
    try:
        print(f"⚡ [奇門修改密碼] 收到修改密碼請求，目標帳號/信箱: {request.account}")
        
        user = db.query(User).filter((User.email == request.account) | (User.username == request.account)).first()
        if not user:
            raise HTTPException(status_code=404, detail="找不到該用戶")
        
        # 1. 🌟 修正點：從記憶體保險箱裡撈出這個用戶剛才生成的金鑰
        cached_data = RESET_CODES.get(user.id)
        if not cached_data:
            raise HTTPException(status_code=400, detail="請先獲取驗證碼，或驗證碼已失效")
            
        if cached_data["code"].strip() != request.code.strip():
            raise HTTPException(status_code=400, detail="安全驗證碼不正確")
            
        # 2. 檢查記憶體時間是否過期
        if cached_data["expires"] < datetime.utcnow():
            raise HTTPException(status_code=400, detail="驗證碼已超過 15 分鐘時效，請重新獲取")
            
        # 3. 驗證完全過關，進行新密碼雜湊與寫入
        print("⚡ [奇門修改密碼] 驗證碼完美對位！正在進行新密碼雜湊改運...")
        user.password_hash = hash_password(request.new_password)
        db.commit()
        
        # 4. 成功後清空該用戶的記憶體金鑰，防止一碼多用
        RESET_CODES.pop(user.id, None)
        
        print("⚡ [奇門修改密碼] 🎉 密碼修改成功，新磁場已同步完成！")
        return {"status": "success", "message": "密碼修改成功！新磁場已同步，請重新登入。"}
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print("❌ [奇門修改密碼] 後端執行期間發生未知崩潰！")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"後端內部錯誤: {str(e)}")