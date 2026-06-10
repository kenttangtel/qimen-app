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
    credits = Column(Integer, default=3)
    membership_type = Column(String, default="free")
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    subscription_status = Column(String, default="inactive")
    gender = Column(String, nullable=True)
    bazi_birth_time = Column(String, nullable=True)


class History(Base):
    __tablename__ = "history"

    id = Column(String, primary_key=True, index=True)
    user_id = Column(String, nullable=False)
    category = Column(String, nullable=False)
    record_time = Column(Text, nullable=False)
    report_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_pinned = Column(Boolean, default=False)


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