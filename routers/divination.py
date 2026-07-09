from datetime import date, datetime
import logging
import re
import pytz

from fastapi import APIRouter, HTTPException, Depends, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import config
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from lunar_python import Solar

from config import DEEPSEEK_API_KEY
from models.db import engine, get_db, SessionLocal, User, History, Session
from routers.auth import get_current_user
from models.schemas import (
    AuthRequest,
    CalculationRequest,
    CalculationResponse,
    LogicState,
    PalaceData,
    QimenInfo,
)
from services.qimen import Const, QuantityEvaluator, QimenEngine, RuleEngine

try:
    from openai import AsyncOpenAI
except ImportError:
    AsyncOpenAI = None

router = APIRouter()
security = HTTPBearer()
client = AsyncOpenAI(api_key=DEEPSEEK_API_KEY, base_url="https://api.deepseek.com") if AsyncOpenAI and DEEPSEEK_API_KEY else None

# logger for debugging in live environment
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

from datetime import datetime, timedelta
from fastapi import HTTPException

def verify_and_deduct_credits(user, category: str, db):
    """
    🌟 奇門大師核心商業權限驗證閘門
    """
    current_time = datetime.now()
    today_date = current_time.date()

    # -------------------------------------------------------------------------
    # 核心邏輯 A：個人專屬運程報告 (深度推演)
    # -------------------------------------------------------------------------
    if category in ["綜合運勢", "個人運程"]:
        if user.membership_type == "free":
            raise HTTPException(
                status_code=403, 
                detail="❌ 免費會員無法使用『個人專屬深度推演』！請先升級為尊享月費會員或永久會員。"
            )
        
        if user.last_daily_fortune_at and user.last_daily_fortune_at.date() == today_date:
            raise HTTPException(
                status_code=403, 
                detail="⏳ 您今日的免費個人運程報告額度已用完，請明天再試！"
            )
        
        user.last_daily_fortune_at = current_time
        db.commit()
        return True

    # -------------------------------------------------------------------------
    # 核心邏輯 B：事盤推演
    # -------------------------------------------------------------------------
    elif category == "事盤":
        if user.membership_type == "lifetime":
            is_free_weekly_available = (
                user.last_weekly_shipan_at is None or 
                (current_time - user.last_weekly_shipan_at) >= timedelta(days=7)
            )
            if is_free_weekly_available:
                user.last_weekly_shipan_at = current_time
                db.commit()
                return True
        
        if user.credits < 1:
            raise HTTPException(
                status_code=402, 
                detail="🪙 您的基礎能量點數不足！無法進行事盤推演，請前往個人中心補充點數包。"
            )
        
        user.credits -= 1
        db.commit()
        return True
        
    return True

def clean_stream_content(text: str) -> str:
    patterns = [
        (r"AI", "本大師"),
        (r"語言模型", "推演系統"),
        (r"DeepSeek", "玄學大腦"),
        (r"人工智慧", "數理邏輯"),
        (r"OpenAI", "天體資料庫"),
        (r"GPT", "星盤程式"),
    ]
    for p, r in patterns:
        text = re.sub(p, r, text, flags=re.IGNORECASE)
    return text


def get_user_field(user, key, default=None):
    """Return attribute or mapping value for `user` supporting ORM instance or dict."""
    if user is None:
        return default
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)


def normalize_time_to_hk(request_time: str) -> tuple[str, datetime]:
    safe_time = request_time[:16].replace("T", " ")
    try:
        dt = datetime.strptime(safe_time, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="time must follow format YYYY-MM-DD HH:MM",
        ) from exc
    hk_tz = pytz.timezone("Asia/Hong_Kong")
    if dt.tzinfo is None:
        dt = hk_tz.localize(dt)
    else:
        dt = dt.astimezone(hk_tz)
    return safe_time, dt


def get_user_by_token(token: str | None) -> User | None:
    if not token:
        return None
    # First try JWT decode (tokens issued by auth.login)
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[config.JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id:
            with engine.connect() as conn:
                res = conn.execute(text("SELECT id, credits, membership_type FROM users WHERE id=:uid"), {"uid": user_id})
                row = res.mappings().first()
                if row:
                    # normalize is_vip flag for legacy code
                    row = dict(row)
                    row["is_vip"] = row.get("membership_type") in ("monthly", "lifetime")
                    return row
    except JWTError:
        # not a JWT or invalid JWT, fallback to session lookup
        pass

    db = SessionLocal()
    try:
        session_record = db.query(Session).filter(Session.token == token).first()
        if not session_record:
            return None
        user = db.query(User).filter(User.id == session_record.user_id).first()
        if not user:
            return None
        # return mapping-like object similar to the SQL path above
        return {"id": user.id, "credits": user.credits, "membership_type": user.membership_type, "is_vip": user.membership_type in ("monthly", "lifetime")}
    finally:
        db.close()


def build_matrix_response(request_time: str, user: User | None = None) -> CalculationResponse:
    safe_time, dt = normalize_time_to_hk(request_time)
    try:
        logger.debug(f"build_matrix_response: safe_time={safe_time}, dt={dt.isoformat()}")
    except Exception:
        pass
    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
    lunar = solar.getLunar()
    bazi = lunar.getEightChar()
    d_s, d_b, h_s, h_b = (
        bazi.getDayGan(),
        bazi.getDayZhi(),
        bazi.getTimeGan(),
        bazi.getTimeZhi(),
    )
    hour_xk = RuleEngine.calculate_xun_kong(h_s, h_b)
    ri_xk = RuleEngine.calculate_xun_kong(d_s, d_b)
    horse_map = {
        "申": "艮宮",
        "子": "艮宮",
        "辰": "艮宮",
        "寅": "坤宮",
        "午": "坤宮",
        "戌": "坤宮",
        "亥": "巽宮",
        "卯": "巽宮",
        "未": "巽宮",
        "巳": "乾宮",
        "酉": "乾宮",
        "丑": "乾宮",
    }
    wu_bu_yu_map = {
        "甲": "庚",
        "乙": "辛",
        "丙": "壬",
        "丁": "癸",
        "戊": "甲",
        "己": "乙",
        "庚": "丙",
        "辛": "丁",
        "壬": "戊",
        "癸": "己",
    }
    term = lunar.getPrevJieQi(True).getName()
    qj = QimenEngine.calculate_ju(term, d_s, d_b)
    ep = QimenEngine.calculate_earth_pan(qj["dun_type"], qj["ju_num"])
    xi = QimenEngine.calculate_xun(h_s, h_b)
    zi = QimenEngine.calculate_zhi_fu_zhi_shi(ep, xi["hidden_stem"])
    hp = QimenEngine.calculate_heaven_pan(ep, h_s, xi["hidden_stem"], zi["palace"])
    dp = QimenEngine.calculate_doors(
        qj["dun_type"],
        zi["door"],
        zi["palace"],
        xi["jia_name"][1],
        h_b,
    )
    current_zhi_fu_palace = next(
        (p for p, s in hp["stars"].items() if s == zi["star"]),
        "坤宮",
    )
    deities = QimenEngine.calculate_deities(qj["dun_type"], current_zhi_fu_palace)
    hs = QimenEngine.calculate_hidden_stems(
        qj["dun_type"],
        xi["hidden_stem"] if h_s == "甲" else h_s,
        next((p for p, d in dp.items() if d == zi["door"]), "中宮"),
    )
    q_matrix = []
    for p_n in [
        "坎宮",
        "坤宮",
        "震宮",
        "巽宮",
        "中宮",
        "乾宮",
        "兌宮",
        "艮宮",
        "離宮",
    ]:
        h_t = hp["stems"].get(p_n, "")
        e_t = ep.get(p_n, "")
        door = dp.get(p_n, "")
        star = hp["stars"].get(p_n, "")
        deity = deities.get(p_n, "")
        pattern = RuleEngine.get_pattern(h_t, e_t, star, door, deity, zi["door"], p_n)
        st = RuleEngine.get_stem_tags(h_t + e_t, p_n)
        logic_state = LogicState(
            is_in_tomb="(墓)" in st,
            is_punished="(刑)" in st,
            is_empty=any(b in hour_xk for b in Const.PALACE_BRANCHES.get(p_n, [])),
            is_horse=(p_n == horse_map.get(h_b, "")),
            is_door_forced=(RuleEngine.get_door_strength(door, p_n) == "迫"),
        )
        q_matrix.append(
            PalaceData(
                palace_id=p_n,
                hidden_stem=hs.get(p_n, ""),
                heaven_stem=h_t,
                heaven_stem_tags=RuleEngine.get_stem_tags(h_t, p_n),
                heaven_stem_state=RuleEngine.calculate_12_states(h_t, p_n),
                earth_stem=e_t,
                earth_stem_tags=RuleEngine.get_stem_tags(e_t, p_n),
                earth_stem_state=RuleEngine.calculate_12_states(e_t, p_n),
                door=door,
                star=star,
                deity=deity,
                pattern=pattern,
                star_strength=RuleEngine.get_star_strength(star, term),
                door_strength=RuleEngine.get_door_strength(door, p_n),
                host_guest=RuleEngine.get_interaction(Const.WX_MAP.get(star, "土"), Const.WX_MAP.get(p_n, "土")),
                logic_states=logic_state,
            )
        )
    report = CalculationResponse(
        solar_time=safe_time,
        lunar_time=f"{lunar.getYearInChinese()}年{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}日",
        bazi={
            "year": bazi.getYear(),
            "month": bazi.getMonth(),
            "day": bazi.getDay(),
            "hour": bazi.getTime(),
            "day_empty": hour_xk,
            "is_wby": "True" if wu_bu_yu_map.get(d_s) == h_s else "False",
        },
        qimen_info=QimenInfo(
            solar_term=term,
            dun_type=qj["dun_type"],
            yuan=qj["yuan"],
            ju_num=qj["ju_num"],
            hour_xun=xi["full_name"],
            zhi_fu=zi["star"],
            zhi_shi=zi["door"],
            description=qj["description"],
            ri_kong=ri_xk,
        ),
        qimen_matrix=q_matrix,
        solution="",
    )

    user_membership = getattr(user, "membership_type", None) if user is not None else None
    if not user_membership and isinstance(user, dict):
        user_membership = user.get("membership_type")

    if user and user_membership in ("monthly", "lifetime"):
        report.qimen_info.description += "\n【專屬加值】系統已融合本命八字，加強準度。"
    if user and user_membership in ("monthly", "lifetime"):
        report.solution = "完整解決方案與能量策略已啟動。"
    else:
        report.solution = "鎖定內容：請升級會員解鎖專屬解決方案"
    return report


@router.post("/api/v1/divination/calculate", response_model=CalculationResponse)
async def calculate_route(request: CalculationRequest) -> CalculationResponse:
    return await calculate_matrix(request)


async def calculate_matrix(request: CalculationRequest) -> CalculationResponse:
    user = get_user_by_token(request.token)
    # support both ORM User and mapping returned by legacy token lookup
    user_membership = getattr(user, "membership_type", None) if user is not None else None
    if not user_membership and isinstance(user, dict):
        user_membership = user.get("membership_type")
    if user and user_membership not in ("monthly", "lifetime"):
        user = None
    return build_matrix_response(request.time, user)


@router.post("/api/v1/divination/interpret")
async def interpret_matrix(
    request: CalculationRequest, 
    user: User = Depends(get_current_user),
    db=Depends(get_db)  # 🌟 這裡直接帶入第 15 行已經準備好的 get_db
):
    try:
        if not client:
            return StreamingResponse(iter(["**❌ 磁場連接異常**"]), media_type="text/event-stream")
        
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")
            
        # 🌟 在發送給 AI 算命前，先執行權限攔截與扣點驗證！
        verify_and_deduct_credits(user, request.category, db)

        with engine.connect() as conn:
            # normalize VIP flag for downstream logic
            is_vip = get_user_field(user, "membership_type") in ("monthly", "lifetime")

            is_free = False
            today_str = date.today().isoformat()
            month_str = date.today().strftime("%Y-%m")

            if is_vip:
                if "專屬每日運程" in request.category:
                    result = conn.execute(
                        text(
                            "SELECT count(*) AS cnt FROM history WHERE user_id=:user_id AND category LIKE :category AND created_at LIKE :created_at"
                        ),
                        {
                            "user_id": get_user_field(user, "id"),
                            "category": "%專屬每日運程%",
                            "created_at": today_str + "%",
                        },
                    )
                    if result.mappings().first()["cnt"] == 0:
                        is_free = True
                elif "「命盤」" in request.category:
                    result = conn.execute(
                        text(
                            "SELECT count(*) AS cnt FROM history WHERE user_id=:user_id AND category LIKE :category AND created_at LIKE :created_at"
                        ),
                        {
                            "user_id": get_user_field(user, "id"),
                            "category": "%「命盤」%",
                            "created_at": month_str + "%",
                        },
                    )
                    if result.mappings().first()["cnt"] == 0:
                        is_free = True

            if not is_free:
                if get_user_field(user, "credits", 0) < 1:
                    return StreamingResponse(iter(["**💎 推演能量不足**"]), media_type="text/event-stream")
                conn.execute(
                    text("UPDATE users SET credits = credits - 1 WHERE id=:user_id"),
                    {"user_id": get_user_field(user, "id")},
                )

            seeker_info_prompt = ""
            is_destiny = "「命盤」" in request.category

            if is_vip and not is_destiny:
                seeker_match = re.search(r"\(求測人：(.*?)\)", request.question)
                if seeker_match:
                    seeker_name = seeker_match.group(1)
                    result = conn.execute(
                        text(
                            "SELECT record_time FROM history WHERE user_id=:user_id AND category=:category ORDER BY created_at DESC LIMIT 1"
                        ),
                        {
                            "user_id": get_user_field(user, "id"),
                            "category": f"「命盤」{seeker_name}",
                        },
                    )
                    seeker_record = result.mappings().first()
                    if seeker_record:
                        try:
                            _, s_dt = normalize_time_to_hk(seeker_record["record_time"])
                            s_solar = Solar.fromYmdHms(
                                s_dt.year, s_dt.month, s_dt.day, s_dt.hour, s_dt.minute, 0
                            )
                            s_bazi = s_solar.getLunar().getEightChar()
                            bz_str = (
                                f"{s_bazi.getYearGan()}{s_bazi.getYearZhi()}年 {s_bazi.getMonthGan()}{s_bazi.getMonthZhi()}月"
                                f" {s_bazi.getDayGan()}{s_bazi.getDayZhi()}日 {s_bazi.getTimeGan()}{s_bazi.getTimeZhi()}時"
                            )
                            seeker_info_prompt = (
                                f"\n\n【💎 VIP 專屬交叉分析】\n求測人「{seeker_name}」本命八字：{bz_str}。"
                                "請務必將此奇門局象與本命人的八字進行交叉共振分析，給出專屬指引！"
                            )
                        except Exception:
                            pass

        try:
            matrix_data = build_matrix_response(request.time)
        except HTTPException as exc:
            return StreamingResponse(
                iter([f"**❌ {exc.detail}**"]),
                media_type="text/event-stream",
                status_code=exc.status_code,
            )
        except Exception as exc:
            logger.exception("build_matrix_response failed")
            return StreamingResponse(
                iter(["**❌ 盤象產生失敗**"]),
                media_type="text/event-stream",
                status_code=400,
            )
        if not getattr(matrix_data, "bazi", None):
            logger.error("build_matrix_response returned no bazi data")
            return StreamingResponse(iter(["**❌ 盤象產生失敗**"]), media_type="text/event-stream", status_code=500)
        try:
            bazi_eval = QuantityEvaluator.evaluate(matrix_data.bazi)
        except Exception as exc:
            logger.exception("QuantityEvaluator failed")
            return StreamingResponse(iter(["**❌ 盤象量化失敗**"]), media_type="text/event-stream", status_code=500)

        eval_text = f"""
\n【⚖️ 核心數據：五行量化能量分析 (LLM 必讀)】
- 日主旺衰基準：{bazi_eval['day_master_strength']}
- 五行細分得分：{bazi_eval['scores']}
- 喜用五行（必須生旺）：{', '.join(bazi_eval['xi_yong'])}
- 忌諱五行（絕對避開）：{', '.join(bazi_eval['ji_shen'])}
- 決策指令：若奇門方位/顏色與忌諱五行衝突，必須使用『通關轉譯法』。
"""

        palace_details = "".join(
            [
                f"[{p.palace_id}] 天:{p.heaven_stem}/{p.earth_stem}, 星:{p.star}, 門:{p.door}, 神:{p.deity}, 格:{p.pattern}\n"
                for p in matrix_data.qimen_matrix
            ]
        )

        day_stem = matrix_data.bazi["day"][0]
        hour_stem = matrix_data.bazi["hour"][0]
        bazi_str = (
            f"{matrix_data.bazi['year']} {matrix_data.bazi['month']} {matrix_data.bazi['day']} {matrix_data.bazi['hour']}"
        )

        try:
            dt = datetime.strptime(request.time[:16].replace("T", " "), "%Y-%m-%d %H:%M")
            age = date.today().year - dt.year
        except Exception:
            age = "未知"

        identity_prompt = (
            f"\n【代體識別】求測人(日干)為「{day_stem}」，事體(時干)為「{hour_stem}」。請精確定位。"
        )

        if is_destiny:
            destiny_context = f"""
\n【⚠️ 核心鐵律：終身命卦架構與年齡適配】
1. 視角隔離：此為【終身格局】推演。請從「本命身分」出發，解讀求測人一生的人格特質、天賦能量與家庭根基。
2. 年齡適配：求測人目前 {age} 歲，身分現況為「{request.status}」。解讀必須符合此年齡段的社會邏輯。
   - 若為「未成年/學生」：將『財運』轉化為『學業資源』，絕不可談論職場競爭或婚姻成敗！
   - 若為「退休長者」：請著重養生、家庭和睦與晚年生活。
   - 若為「老闆/就業」：請著重事業發展與實質財富。

【🔥 終極密令：雙系統玄學融合校準 (Bazi-Qimen Calibration Protocol)】
1. 確立主從關係：子平八字為【體】（主、核心底色），奇門遁甲為【用】（從、時空工具）。
2. 規則：奇門遁甲所生成的「幸運五行」與「顏色」，必須在八字的「喜用神」框架內進行過濾，絕對不允許輸出與八字喜用神相衝、相剋的五行/顏色。
3. 動態校準演算法：
   - Step 1：獲取八字底色（確認求測人八字喜用神，如：喜水木、忌土金）。
   - Step 2：解讀奇門局部（找出當前盤中帶吉門吉星的奇門五行）。
   - Step 3：交叉過濾。若奇門五行是八字忌神，【必須強行校準】。AI 必須尋找奇門盤中「既符合吉方，又能生旺八字喜用」的次強五行。
4. 顏色轉譯規則（通關法）：若奇門利「金」（白）但八字忌金喜水。不可輸出白色，應輸出黑色/藍色（水），取「金生水」之意轉化能量。
"""

            prompt = f"""
你是奇門遁甲頂級大師。推演類別：【{request.category}】。{identity_prompt}{destiny_context}{eval_text}
求測人八字：{bazi_str}
起盤數據：局勢：{matrix_data.qimen_info.description}，旬首：{matrix_data.qimen_info.hour_xun}，詳情：
{palace_details}

請嚴格依照以下「8大板塊」架構輸出（使用 Markdown）。每一個分析段落（一至六），必須嚴格分為「### 🧭 盤象解析」與「### 💡 大師解讀」上下兩個部分：

## 🎯 斷語金句
> （直斷一生格局，20字內。例如：大吉，烈火煉金，必成大器。）

## 一、性格特徵（外表與內在）
### 🧭 盤象解析
(針對懂得奇門遁甲的使用者，使用專業術語解釋用神落宮、星門神儀、格局生剋等客觀依據)
### 💡 大師解讀
(針對一般求測人，用香港繁體書面語，清晰地解釋性格與特質)

## 二、家庭背景（早年與六親）
### 🧭 盤象解析
### 💡 大師解讀

## 三、人際關係（貴人與小人）
### 🧭 盤象解析
### 💡 大師解讀

## 四、愛情及婚姻（感情特質與建議）
### 🧭 盤象解析
### 💡 大師解讀

## 五、財運與生意（事業格局與求財方針）
### 🧭 盤象解析
### 💡 大師解讀

## 六、大運和流年（目前10年大運總評）
### 🧭 盤象解析
### 💡 大師解讀

## 七、未來五年運勢推演表
(強制輸出 Markdown 表格，請勿加上【盤象解析】或【大師解讀】的子標題，直接輸出下方格式的表格即可)
| 年份 | 干支 | 運勢基調 | 詳細解析與建議 |
|---|---|---|---|
| (推演第1年) | | | |
| (推演第2年) | | | |
| (推演第3年) | | | |
| (推演第4年) | | | |
| (推演第5年) | | | |

## 八、雙系統專屬開運指南
(直接用香港繁體書面語給予總結。請務必啟動「雙系統玄學融合校準指令」，清晰說明如何根據其八字喜用神過濾並轉譯奇門五行，最終給出最精準的【專屬幸運五行】與【專屬幸運顏色】。最後提供人生心法，不需分解析與解讀標題。)
"""
        else:
            event_context = """
\n【⚡ 強制命令：時家事體與斷卦層次隔離令】
1. 嚴格隔離：此為【時家奇門】當下時空推演。嚴禁在此處用單一時辰的奇門盤去推論用戶一生的早年家境、父母管教、子女孝順、晚年壽命等六親長線大運！否則將判定為嚴重偏離主題！
2. 聚焦當下：解讀重心必須 100% 聚焦於【當下求測之具體事體】。請深入且聚焦於：
   - 求財：看「生門/戊落宮與旺衰」
   - 事業：看「開門落宮、天盤天干奇儀、阻礙與機會」
   - 壓力與現狀：看「日干落宮、臨何星門神，以及目前承受何種環境局限」
3. 糾正宮位星門生剋與現代化解讀：
   - 務必遵循客觀生剋邏輯！例如天芮星落巽宮，巽木剋芮土，此為「星受宮剋(星受剋)」，代表原本繁雜的困擾受到環境制度、文化或紀律的實質制約與壓制。
   - 傷門落坤宮，傷木剋坤土，此為「門剋宮(宮受剋，即門迫)」，代表行動或衝突會對環境體制造成實質破壞，並產生直接摩擦。
   - 嚴禁直接生搬硬套古代農耕社會的封建「六親公式」或刑罰恐嚇！必須結合九星旺衰與八門克應，給出符合「現代商務、職場、個人心理與生活抉擇」的邏輯轉譯和正面實戰建議。
"""
            yongshen_prompt = (
                f"\n【用神定位法則】此次推演類別為【{request.category}】。"
                "請大師務必嚴格依據類別選取「專屬用神」（例如：求財看生門/戊，事業看開門，運勢看日干與時干生剋），並以此作為解盤核心！"
            )

            prompt = f"""
你是奇門遁甲國師。推演類別：【{request.category}】，背景：【{request.question}】{identity_prompt}{event_context}{yongshen_prompt}
起盤數據：局勢：{matrix_data.qimen_info.description}，旬首：{matrix_data.qimen_info.hour_xun}，詳情：
{palace_details}

請嚴格依照以下架構輸出（使用 Markdown）。每一個分析段落（一至四），必須嚴格分為「### 🧭 盤象解析」與「### 💡 大師解讀」上下兩個部分：

## 🎯 斷語金句
> （直斷當下吉凶，20字內。例如：大吉，財星高照，宜大膽進取。）

## 一、局勢解讀
### 🧭 盤象解析
(針對懂得奇門遁甲的使用者，使用專業術語解釋用神落宮、星門神儀、格局生剋等客觀依據)
### 💡 大師解讀
(針對一般求測人，用香港繁體書面語，清晰地解釋目前求測事項的大環境與局勢)

## 二、核心關鍵
### 🧭 盤象解析
(指出當前面臨的實質壓力、阻礙或機會的專業客觀與星門生剋依據)
### 💡 大師解讀
(用香港繁體書面語，結合現代商務或生活，點出目前阻礙或轉機的核心癥結)

## 三、未來演化
### 🧭 盤象解析
(推演此事未來動態變化的專業依據)
### 💡 大師解讀
(用香港繁體書面語，說明事情接下來的發展趨勢與階段變化)

## 四、建議化解
### 🧭 盤象解析
(提出化解方針的專業五行/時空依據)
### 💡 大師解讀
(用香港繁體書面語，給予具體可行的執行行動建議，包括有利方向或轉折借氣建議)
"""

        async def generate():
            try:
                stream = await client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {
                            "role": "system",
                            "content": "你是香港頂級奇門遁甲大師，語氣莊重專業、客觀權威。請務必全程使用「香港繁體中文的書面語」進行解答（符合香港人的閱讀習慣，避免內地網絡用語，但保持高級命理顯問的質感）。絕對禁止透露 AI 身份。",
                        },
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.7,
                    stream=True,
                )
            except Exception as exc:
                logger.exception("AI stream creation failed")
                yield "**❌ AI 解盤失敗，請稍後再試**"
                return

            try:
                async for chunk in stream:
                    content = None
                    try:
                        content = chunk.choices[0].delta.content
                    except Exception:
                        continue
                    if content:
                        yield clean_stream_content(content)
            except Exception as exc:
                logger.exception("AI stream iteration failed")
                yield "**❌ AI 串流中斷，請稍後再試**"
                return

        return StreamingResponse(generate(), media_type="text/event-stream")
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("interpret_matrix unexpected error")
        # Return a safe streaming error message and include the exception text for debugging in logs
        return StreamingResponse(
            iter([f"**❌ Internal Server Error: {str(exc)}**"]),
            media_type="text/event-stream",
            status_code=500,
        )