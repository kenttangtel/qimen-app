from datetime import datetime, timedelta
from pydantic import BaseModel  # 🌟 核心修正：把漏掉的大腦憑證補進來！
import string  # 🌟 核心補位：給後端隨機生成 6 位數純數字驗證碼使用！
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

import string
import smtplib
from email.mime.text import MIMEText
from email.header import Header

# 🌟 忘記密碼第一關：生成 6 位數驗證碼並透過 SMTP 發信
@router.post("/api/v1/auth/forgot-password")
async def forgot_password(request: AuthRequest, db=Depends(get_db)):
    # 這裡借用 AuthRequest 結構，我們只需要 request.username 或 request.email
    # 支援用戶輸入信箱或帳號找回
    user = db.query(User).filter((User.email == request.username) | (User.username == request.username)).first()
    if not user or not user.email:
        raise HTTPException(status_code=404, detail="找不到該用戶或該帳號未綁定信箱")

    # 1. 隨機生成 6 位數純數字驗證碼
    code = "".join(secrets.choice(string.digits) for _ in range(6))
    
    # 2. 設定 15 分鐘有效期限
    user.reset_code = code
    user.reset_code_expires = datetime.utcnow() + timedelta(minutes=15)
    db.commit()

    # 3. 發送郵件（使用通用發信引擎，SMTP 設定請在下方環境變數設定）
    smtp_server = config.SMTP_SERVER if hasattr(config, "SMTP_SERVER") else "smtp.gmail.com"
    smtp_port = config.SMTP_PORT if hasattr(config, "SMTP_PORT") else 587
    smtp_user = config.SMTP_USER if hasattr(config, "SMTP_USER") else "您的發信郵件@gmail.com"
    smtp_pass = config.SMTP_PASS if hasattr(config, "SMTP_PASS") else "您的密碼或應用程式密碼"

    mail_body = f"""
    <h3>【奇門大師】密碼重置驗證碼</h3>
    <p>您好，系統收到您重置密碼的請求。</p>
    <p>您的 6 位數驗證碼為：<b style='font-size: 24px; color: #4f46e5; letter-spacing: 4px;'>{code}</b></p>
    <p>請於 15 分鐘內在網頁畫面上輸入此驗證碼。若非本人操作，請忽略此郵件。</p>
    """
    
    try:
        msg = MIMEText(mail_body, "html", "utf-8")
        msg["Subject"] = Header("【奇門大師】安全驗證碼", "utf-8")
        msg["From"] = smtp_user
        msg["To"] = user.email

        # 啟動加密連線發信
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [user.email], msg.as_string())
        server.quit()
        return {"status": "success", "message": "驗證碼已成功送達您的信箱"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="發送郵件失敗，請檢查後端 SMTP 配置")


# 🌟 萬能相容模型：不管前端丟什麼欄位過來，通通設為預設空字串，絕不噴 422 錯誤！
class ForgotPasswordRequest(BaseModel):
    account: str = ""
    email: str = ""
    username: str = ""
    password: str = ""

@router.post("/api/v1/auth/forgot-password")
async def forgot_password(request: ForgotPasswordRequest, db=Depends(get_db)):
    # 🌟 萬能解鎖鑰匙：哪一個欄位有填，就用哪一個當作查找目標！
    search_target = request.account or request.email or request.username
    if not search_target:
        raise HTTPException(status_code=400, detail="請輸入帳號或電子信箱")

    # 同時支援用戶輸入信箱或用戶名來查找
    user = db.query(User).filter((User.email == search_target) | (User.username == search_target)).first()
    if not user or not user.email:
        raise HTTPException(status_code=404, detail="找不到該用戶或該帳號未綁定信箱")

    # 1. 隨機生成 6 位數純數字驗證碼
    code = "".join(secrets.choice(string.digits) for _ in range(6))
    
    # 2. 設定 15 分鐘有效期限
    user.reset_code = code
    user.reset_code_expires = datetime.utcnow() + timedelta(minutes=15)
    db.commit()

    # 3. 取得發信設定
    smtp_server = config.SMTP_SERVER if hasattr(config, "SMTP_SERVER") else "smtp.gmail.com"
    smtp_port = config.SMTP_PORT if hasattr(config, "SMTP_PORT") else 587
    smtp_user = config.SMTP_USER if hasattr(config, "SMTP_USER") else "您的發信郵件@gmail.com"
    smtp_pass = config.SMTP_PASS if hasattr(config, "SMTP_PASS") else "您的密碼"

    mail_body = f"""
    <h3>【奇門大師】密碼重置驗證碼</h3>
    <p>您好，系統收到您重置密碼的請求。</p>
    <p>您的 6 位數驗證碼為：<b style='font-size: 24px; color: #4f46e5; letter-spacing: 4px;'>{code}</b></p>
    <p>請於 15 分鐘內在網頁畫面上輸入此驗證碼。若非本人操作，請忽略此郵件。</p>
    """
    
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.header import Header
        
        msg = MIMEText(mail_body, "html", "utf-8")
        msg["Subject"] = Header("【奇門大師】安全驗證碼", "utf-8")
        msg["From"] = smtp_user
        msg["To"] = user.email

        # 🌟 終極修正：改用內建的 SMTP_SSL 走 Port 465 管道，強制繞過 Render 的 IPv6 路由死穴！
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [user.email], msg.as_string())
        server.quit()
        return {"status": "success", "message": "驗證碼已成功送達您的信箱"}
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="發送郵件失敗，請檢查後端 SMTP 配置")