from datetime import datetime

from sqlalchemy import create_engine, Column, Integer, String, Boolean, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import QueuePool

from config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=5,
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=True)
    credits = Column(Integer, default=5)  # 🌟 順手修正：資料庫預設點數同步升級為 5 點！
    membership_type = Column(String, default="free")
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    subscription_status = Column(String, default="inactive")
    gender = Column(String, nullable=True)
    bazi_birth_time = Column(String, nullable=True)
    
    # 🌟 核心新增：加在 User 的最底部（原第 32 行下方）
    last_daily_fortune_at = Column(DateTime, nullable=True)  # 追蹤每日個人深度運程時間
    last_weekly_shipan_at = Column(DateTime, nullable=True)  # 追蹤每週免費事盤時間


class History(Base):
    __tablename__ = "history"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False)
    category = Column(String, nullable=False)
    record_time = Column(Text, nullable=False)
    report_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_pinned = Column(Boolean, default=False)


class Session(Base):
    __tablename__ = "sessions"

    token = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False)


class CheckoutSessionRecord(Base):
    __tablename__ = "checkout_session_records"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False)
    price_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


def get_db():
    if not DATABASE_URL:
        raise Exception("請設定 DATABASE_URL！")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    if not DATABASE_URL:
        return
    Base.metadata.create_all(bind=engine)