from typing import Dict, List, Optional

from pydantic import BaseModel


class LogicState(BaseModel):
    is_in_tomb: bool = False
    is_punished: bool = False
    is_empty: bool = False
    is_horse: bool = False
    is_door_forced: bool = False
    description: str = ""


class PalaceData(BaseModel):
    palace_id: str
    hidden_stem: str
    heaven_stem: str
    heaven_stem_tags: str
    heaven_stem_state: str
    earth_stem: str
    earth_stem_tags: str
    earth_stem_state: str
    door: str
    star: str
    deity: str
    pattern: str
    star_strength: str = ""
    door_strength: str = ""
    host_guest: str = ""
    logic_states: LogicState


class QimenInfo(BaseModel):
    solar_term: str
    dun_type: str
    yuan: str
    ju_num: int
    hour_xun: str
    zhi_fu: str
    zhi_shi: str
    description: str
    ri_kong: str = ""


class CalculationResponse(BaseModel):
    solar_time: str
    lunar_time: str
    bazi: Dict[str, str]
    qimen_info: QimenInfo
    qimen_matrix: List[PalaceData]
    solution: str


class CalculationRequest(BaseModel):
    time: str
    lat: float = 22.3
    lon: float = 114.1
    gender: str = "男"
    category: str = "綜合運勢"
    question: str = ""
    status: str = ""
    token: str = ""
    main_title: str = ""


class AuthRequest(BaseModel):
    username: str
    password: str
    email: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    username: str
    email: Optional[str] = None
    credits: int = 0
    membership_type: str = "free"
    subscription_status: str = "inactive"
    gender: Optional[str] = None
    bazi_birth_time: Optional[str] = None
    is_vip: bool = False


class HistoryCreate(BaseModel):
    category: str
    record_time: str
    report_text: str
    is_pinned: bool = False


class HistoryResponse(BaseModel):
    id: str
    category: str
    record_time: str
    report_text: str
    created_at: str
    is_pinned: bool