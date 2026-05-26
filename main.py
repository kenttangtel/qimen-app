from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from datetime import datetime, date
from typing import List, Dict, Optional
from lunar_python import Solar
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, FileResponse
import os
import asyncio
import uuid
import hashlib
import re
import smtplib
from email.mime.text import MIMEText

import psycopg2
from psycopg2.extras import RealDictCursor
from openai import AsyncOpenAI
import stripe

# ==========================================
# 0. 初始化環境變數與資料庫
# ==========================================
DB_URL = os.environ.get("DATABASE_URL")
stripe.api_key = os.environ.get("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET")

# 📧 SMTP 伺服器預設值 (放在這裡確保全局可用)
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "kenttangtel@gmail.com" # 👈 請替換成您的 Gmail
SENDER_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

def get_db():
    if not DB_URL: raise Exception("請設定 DATABASE_URL！")
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def init_db():
    if not DB_URL: return
    conn = get_db()
    c = conn.cursor()
    
    # 1. 建立基礎資料表
    c.execute('''CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE, password_hash TEXT, credits INTEGER DEFAULT 3, is_vip BOOLEAN DEFAULT FALSE)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, user_id TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS history (id TEXT PRIMARY KEY, user_id TEXT, category TEXT, record_time TEXT, report_text TEXT, created_at TEXT, is_pinned BOOLEAN DEFAULT FALSE)''')
    conn.commit()
    
    # 🛡️ 2. 安全遷移：確保 is_vip 欄位存在
    try: 
        c.execute('''ALTER TABLE users ADD COLUMN is_vip BOOLEAN DEFAULT FALSE''')
        conn.commit()
    except: 
        conn.rollback() # 如果已經存在就解鎖狀態，繼續往下執行
        
    # 🛡️ 3. 安全遷移：確保 email 欄位存在 (修復註冊報錯的核心)
    try: 
        c.execute('''ALTER TABLE users ADD COLUMN email TEXT''')
        conn.commit()
    except: 
        conn.rollback()
    
    # 🛡️ 4. 歷史資料清洗
    try:
        c.execute("UPDATE history SET category = '「事盤」未分類' WHERE category IS NULL OR trim(category) = ''")
        c.execute("UPDATE history SET category = '「事盤」' || category WHERE category NOT LIKE %s AND category NOT LIKE %s", ('「命盤」%', '「事盤」%'))
        conn.commit()
    except Exception as e: 
        conn.rollback()

    conn.close()

init_db()

# ==========================================
# 1. 核心常數
# ==========================================
class Const:
    STEMS = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
    BRANCHES = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]
    QIMEN_STEMS = ["戊", "己", "庚", "辛", "壬", "癸", "丁", "丙", "乙"]
    STATES_12 = ["長", "沐", "冠", "臨", "旺", "衰", "病", "死", "墓", "絕", "胎", "養"]
    PALACE_NUM = {1: "坎宮", 2: "坤宮", 3: "震宮", 4: "巽宮", 5: "中宮", 6: "乾宮", 7: "兌宮", 8: "艮宮", 9: "離宮"}
    PALACE_NAME = {v: k for k, v in PALACE_NUM.items()}
    PALACE_RING = ["坎宮", "艮宮", "震宮", "巽宮", "離宮", "坤宮", "兌宮", "乾宮"]
    DOORS = ["休門", "生門", "傷門", "杜門", "景門", "死門", "驚門", "開門"]
    DEITIES = ["值符", "騰蛇", "太陰", "六合", "白虎", "玄武", "九地", "九天"]
    WX_MAP = {
        "坎宮": "水", "離宮": "火", "震宮": "木", "巽宮": "木", "乾宮": "金", "兌宮": "金", "艮宮": "土", "坤宮": "土", "中宮": "土",
        "天蓬星": "水", "天芮星": "土", "天衝星": "木", "天輔星": "木", "天禽星": "土", "天心星": "金", "天柱星": "金", "天任星": "土", "天英星": "火",
        "休門": "水", "生門": "土", "傷門": "木", "杜門": "木", "景門": "火", "死門": "土", "驚門": "金", "開門": "金"
    }
    XUN_SHOU = {"子": ("甲子", "戊"), "戌": ("甲戌", "己"), "申": ("甲申", "庚"), "午": ("甲午", "辛"), "辰": ("甲辰", "壬"), "寅": ("甲寅", "癸")}
    ORIGINAL_STAR_DOOR = {
        "坎宮": ("天蓬星", "休門"), "坤宮": ("天芮星", "死門"), "震宮": ("天衝星", "傷門"), "巽宮": ("天輔星", "杜門"), "中宮": ("天禽星", "死門"),
        "乾宮": ("天心星", "開門"), "兌宮": ("天柱星", "驚門"), "艮宮": ("天任星", "生門"), "離宮": ("天英星", "景門")
    }
    PALACE_BRANCHES = {"坎宮": ["子"], "艮宮": ["丑", "寅"], "震宮": ["卯"], "巽宮": ["辰", "巳"], "離宮": ["午"], "坤宮": ["未", "申"], "兌宮": ["酉"], "乾宮": ["戌", "亥"]}
    SOLAR_TERM_JU = {
        "冬至": ("陽遁", [1, 7, 4]), "小寒": ("陽遁", [2, 8, 5]), "大寒": ("陽遁", [3, 9, 6]), "立春": ("陽遁", [8, 5, 2]), "雨水": ("陽遁", [9, 6, 3]), "驚蟄": ("陽遁", [1, 7, 4]),
        "春分": ("陽遁", [3, 9, 6]), "清明": ("陽遁", [4, 1, 7]), "穀雨": ("陽遁", [5, 2, 8]), "立夏": ("陽遁", [4, 1, 7]), "小滿": ("陽遁", [5, 2, 8]), "芒種": ("陽遁", [6, 3, 9]),
        "夏至": ("陰遁", [9, 3, 6]), "小暑": ("陰遁", [8, 2, 5]), "大暑": ("陰遁", [7, 1, 4]), "立秋": ("陰遁", [2, 5, 8]), "處暑": ("陰遁", [1, 4, 7]), "白露": ("陰遁", [9, 3, 6]),
        "秋分": ("陰遁", [7, 1, 4]), "寒露": ("陰遁", [6, 9, 3]), "霜降": ("陰遁", [5, 8, 2]), "立冬": ("陰遁", [6, 9, 3]), "小雪": ("陰遁", [5, 8, 2]), "大雪": ("陰遁", [4, 7, 1])
    }
    # ... 第 91 行 class Const 結束的 }
# (在此處插入)

class QuantityEvaluator:
    # 1. 五行基礎能量權重 (得令 > 得地 > 得勢)
    MONTH_POWER = {
        "寅": {"木": 45, "火": 30, "土": 10, "金": 5,  "水": 10},
        "卯": {"木": 50, "火": 25, "土": 5,  "金": 5,  "水": 15},
        "辰": {"木": 20, "火": 15, "土": 40, "金": 15, "水": 10},
        "巳": {"木": 10, "火": 45, "土": 30, "金": 10, "水": 5},
        "午": {"木": 5,  "火": 50, "土": 35, "金": 5,  "水": 5},
        "未": {"木": 15, "火": 25, "土": 45, "金": 5,  "水": 10},
        "申": {"木": 5,  "火": 10, "土": 15, "金": 50, "水": 20},
        "酉": {"木": 5,  "火": 5,  "土": 10, "金": 55, "水": 25},
        "戌": {"木": 10, "火": 20, "土": 50, "金": 15, "水": 5},
        "亥": {"木": 25, "火": 5,  "土": 5,  "金": 10, "水": 55},
        "子": {"木": 20, "火": 5,  "土": 5,  "金": 10, "水": 60},
        "丑": {"木": 10, "火": 5,  "土": 50, "金": 20, "水": 15},
    }

    POSITION_WEIGHT = {
        "year_stem": 8, "year_branch": 12,
        "month_stem": 15,
        "day_branch": 15,
        "hour_stem": 10, "hour_branch": 15
    }

    @staticmethod
    def get_element(name):
        element_map = {
            "甲":"木","乙":"木","寅":"木","卯":"木","巽":"木","震":"木",
            "丙":"火","丁":"火","巳":"火","午":"火","離":"火",
            "戊":"土","己":"土","辰":"土","戌":"土","丑":"土","未":"土","艮":"土","坤":"土","中":"土",
            "庚":"金","辛":"金","申":"金","酉":"金","乾":"金","兌":"金",
            "壬":"水","癸":"水","亥":"水","子":"水","坎":"水"
        }
        for k, v in element_map.items():
            if k in name: return v
        return "土"

    @classmethod
    def evaluate(cls, bazi_data):
        scores = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}
        day_master = bazi_data['day'][0]
        dm_element = cls.get_element(day_master)
        month_branch = bazi_data['month'][1]
        
        month_influence = cls.MONTH_POWER.get(month_branch, {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0})
        for el, val in month_influence.items():
            scores[el] += val

        pillars = [
            ('year_stem', bazi_data['year'][0]), ('year_branch', bazi_data['year'][1]),
            ('month_stem', bazi_data['month'][0]),
            ('day_branch', bazi_data['day'][1]),
            ('hour_stem', bazi_data['hour'][0]), ('hour_branch', bazi_data['hour'][1])
        ]
        
        for pos, name in pillars:
            el = cls.get_element(name)
            scores[el] += cls.POSITION_WEIGHT.get(pos, 0)

        support_elements = {
            "木": ["木", "水"], "火": ["火", "木"], "土": ["土", "火"], 
            "金": ["金", "土"], "水": ["水", "金"]
        }
        
        my_support_score = sum(scores[e] for e in support_elements[dm_element])
        is_strong = my_support_score > 55 
        
        if is_strong:
            xi_yong = [e for e in ["木","火","土","金","水"] if e not in support_elements[dm_element]]
            ji_shen = support_elements[dm_element]
        else:
            xi_yong = support_elements[dm_element]
            ji_shen = [e for e in ["木","火","土","金","水"] if e not in support_elements[dm_element]]

        return {
            "scores": scores,
            "day_master_strength": "偏旺" if is_strong else "偏弱",
            "xi_yong": xi_yong,
            "ji_shen": ji_shen
        }

# 第 93 行 ==========================================
# 第 94 行 # 2. 數據模型與加密邏輯
# ...

# ==========================================
# 2. 數據模型與加密邏輯
# ==========================================
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

# ==========================================
# 3. 奇門推演引擎 
# ==========================================
class QimenEngine:
    @staticmethod
    def calculate_ju(solar_term, day_stem, day_branch):
        stem_idx = Const.STEMS.index(day_stem)
        branch_idx = Const.BRANCHES.index(day_branch)
        offset = stem_idx % 5
        futou_branch_idx = (branch_idx - offset + 12) % 12
        yuan_val = futou_branch_idx % 3
        yuan = "上元" if yuan_val == 0 else "中元" if yuan_val == 2 else "下元"
        dun_type, ju_list = Const.SOLAR_TERM_JU.get(solar_term, ("陽遁", [1, 1, 1]))
        ju_num = ju_list[0 if yuan == "上元" else 1 if yuan == "中元" else 2]
        return {"dun_type": dun_type, "yuan": yuan, "ju_num": ju_num, "description": f"{dun_type}{ju_num}局 ({yuan})"}

    @staticmethod
    def calculate_earth_pan(dun_type, ju_num):
        earth_pan = {}
        start_pos = ju_num - 1 
        for i, stem in enumerate(Const.QIMEN_STEMS):
            palace_num = ((start_pos + i) % 9) + 1 if dun_type == "陽遁" else ((start_pos - i) % 9) + 1
            earth_pan[Const.PALACE_NUM[palace_num]] = stem
        earth_pan["坤宮"] = f"{earth_pan['中宮']}{earth_pan['坤宮']}" 
        return earth_pan

    @staticmethod
    def calculate_xun(stem, branch):
        idx = (Const.BRANCHES.index(branch) - Const.STEMS.index(stem) + 12) % 12
        jia_name, hidden_stem = Const.XUN_SHOU[Const.BRANCHES[idx]]
        return {"jia_name": jia_name, "hidden_stem": hidden_stem, "full_name": f"{jia_name}{hidden_stem}"}

    @staticmethod
    def calculate_zhi_fu_zhi_shi(earth_pan, hidden_stem):
        target_palace = next((p for p, s in earth_pan.items() if hidden_stem in s), "中宮")
        star, door = Const.ORIGINAL_STAR_DOOR[target_palace]
        return {"palace": target_palace, "star": star, "door": door}

    @staticmethod
    def calculate_heaven_pan(earth_pan, hour_stem, hidden_stem, zhi_fu_palace):
        search_stem = hidden_stem if hour_stem == "甲" else hour_stem
        target_palace = next((p for p, s in earth_pan.items() if search_stem in s), "中宮")
        if target_palace == "中宮": target_palace = "坤宮"
        source_palace = zhi_fu_palace if zhi_fu_palace != "中宮" else "坤宮"
        offset = (Const.PALACE_RING.index(target_palace) - Const.PALACE_RING.index(source_palace) + 8) % 8
        heaven_stars = {"中宮": ""}
        heaven_stems = {"中宮": earth_pan.get("中宮", "")}
        for i, current_p in enumerate(Const.PALACE_RING):
            source_p = Const.PALACE_RING[(i - offset + 8) % 8]
            heaven_stars[current_p] = Const.ORIGINAL_STAR_DOOR[source_p][0]
            heaven_stems[current_p] = earth_pan.get(source_p, "")
        return {"stars": heaven_stars, "stems": heaven_stems}

    @staticmethod
    def calculate_doors(dun_type, zhi_shi_door, original_palace, xun_branch, hour_branch):
        steps = (Const.BRANCHES.index(hour_branch) - Const.BRANCHES.index(xun_branch) + 12) % 12
        start_num = Const.PALACE_NAME[original_palace]
        target_num = ((start_num + steps - 1) % 9) + 1 if dun_type == "陽遁" else ((start_num - steps - 1) % 9) + 1
        target_palace = Const.PALACE_NUM[target_num]
        if target_palace == "中宮": target_palace = "坤宮"
        target_idx = Const.PALACE_RING.index(target_palace)
        door_start_idx = Const.DOORS.index(zhi_shi_door)
        result = {"中宮": ""}
        for i, current_p in enumerate(Const.PALACE_RING):
            result[current_p] = Const.DOORS[(i - target_idx + door_start_idx + 8) % 8]
        return result

    @staticmethod
    def calculate_deities(dun_type, heaven_zhi_fu_palace):
        target_palace = "坤宮" if heaven_zhi_fu_palace == "中宮" else heaven_zhi_fu_palace
        target_idx = Const.PALACE_RING.index(target_palace)
        result = {"中宮": ""}
        for i, current_p in enumerate(Const.PALACE_RING):
            deity_idx = (i - target_idx + 8) % 8 if dun_type == "陽遁" else (target_idx - i + 8) % 8
            result[current_p] = Const.DEITIES[deity_idx]
        return result

    @staticmethod
    def calculate_hidden_stems(dun_type, actual_hour_stem, current_zhi_shi_palace):
        if current_zhi_shi_palace == "中宮": current_zhi_shi_palace = "坤宮"
        start_idx = Const.QIMEN_STEMS.index(actual_hour_stem) if actual_hour_stem in Const.QIMEN_STEMS else 0
        start_palace_num = Const.PALACE_NAME[current_zhi_shi_palace]
        result = {}
        for i in range(9):
            palace_num = ((start_palace_num + i - 1) % 9) + 1 if dun_type == "陽遁" else ((start_palace_num - i - 1) % 9) + 1
            result[Const.PALACE_NUM[palace_num]] = Const.QIMEN_STEMS[(start_idx + i) % 9]
        return result

class RuleEngine:
    @staticmethod
    def get_interaction(guest_wx, host_wx):
        relations = {"水": {"木":"生", "火":"剋", "金":"被生", "土":"被剋", "水":"同"},
                     "火": {"土":"生", "金":"剋", "木":"被生", "水":"被剋", "火":"同"},
                     "木": {"火":"生", "土":"剋", "水":"被生", "金":"被剋", "木":"同"},
                     "金": {"水":"生", "木":"剋", "土":"被生", "火":"被剋", "金":"同"},
                     "土": {"金":"生", "水":"剋", "火":"被生", "木":"被剋", "土":"同"}}
        rel = relations.get(guest_wx, {}).get(host_wx, "同")
        map_desc = {"生":"客生地，耗氣", "剋":"客剋地，得利", "被生":"地生客，得助", "被剋":"地剋客，受阻", "同":"客地同氣，平穩"}
        return map_desc.get(rel, "未知")

    @staticmethod
    def get_star_strength(star, solar_term):
        if not star: return ""
        star_wx = Const.WX_MAP.get(star)
        season_wx = "土"
        if solar_term in ["立春","雨水","驚蟄","春分","清明","穀雨"]: season_wx = "木"
        elif solar_term in ["立夏","小滿","芒種","夏至","小暑","大暑"]: season_wx = "火"
        elif solar_term in ["立秋","處暑","白露","秋分","寒露","霜降"]: season_wx = "金"
        elif solar_term in ["立冬","小雪","大雪","冬至","小寒","大寒"]: season_wx = "水"
        if star_wx == season_wx: return "旺"
        rel_map = {"木":{"火":"旺", "水":"廢", "土":"休", "金":"囚"},"火":{"土":"旺", "木":"廢", "金":"休", "水":"囚"},"土":{"金":"旺", "火":"廢", "水":"休", "木":"囚"},"金":{"水":"旺", "土":"廢", "木":"休", "火":"囚"},"水":{"木":"旺", "金":"廢", "火":"休", "土":"囚"}}
        return rel_map.get(star_wx, {}).get(season_wx, "廢")

    @staticmethod
    def get_door_strength(door, palace):
        if not door or not palace: return ""
        door_wx = Const.WX_MAP.get(door)
        palace_wx = Const.WX_MAP.get(palace)
        if palace_wx == door_wx: return "相"
        rel_map = {"木":{"土":"囚", "火":"休", "水":"旺", "金":"迫"},"火":{"金":"囚", "土":"休", "木":"旺", "水":"迫"},"土":{"水":"囚", "金":"休", "火":"旺", "木":"迫"},"金":{"木":"囚", "水":"休", "土":"旺", "火":"迫"},"水":{"火":"囚", "木":"休", "金":"旺", "土":"迫"}}
        return rel_map.get(door_wx, {}).get(palace_wx, "休")

    @staticmethod
    def get_pattern(h_stem, e_stem, star, door, deity, zhi_shi, palace):
        patterns = []
        if "戊" in h_stem and "戊" in e_stem: patterns.append("青龍伏吟")
        elif "乙" in h_stem and "乙" in e_stem: patterns.append("日奇伏吟")
        elif "丁" in h_stem and "癸" in e_stem: patterns.append("朱雀投江")
        elif "癸" in h_stem and "丁" in e_stem: patterns.append("騰蛇夭矯")
        elif "丙" in h_stem and "戊" in e_stem: patterns.append("飛鳥跌穴")
        elif "戊" in h_stem and "丙" in e_stem: patterns.append("青龍返首")
        elif "乙" in h_stem and "辛" in e_stem: patterns.append("青龍逃走")
        elif "辛" in h_stem and "乙" in e_stem: patterns.append("白虎猖狂")
        if "丙" in h_stem and "丁" in e_stem and door == "生門": patterns.append("天遁")
        if "乙" in h_stem and "己" in e_stem and deity == "九地": patterns.append("地遁")
        if "丁" in h_stem and "乙" in e_stem and deity == "太陰": patterns.append("人遁")
        if palace != "中宮":
            orig_star, orig_door = Const.ORIGINAL_STAR_DOOR.get(palace, ("", ""))
            opp_p = {"坎宮":"離宮", "艮宮":"坤宮", "震宮":"兌宮", "巽宮":"乾宮", "離宮":"坎宮", "坤宮":"艮宮", "兌宮":"震宮", "乾宮":"巽宮"}.get(palace)
            opp_star, opp_door = Const.ORIGINAL_STAR_DOOR.get(opp_p, ("", ""))
            if star and star == orig_star: patterns.append("星伏吟")
            elif star and star == opp_star: patterns.append("星反吟")
            if door and door == orig_door: patterns.append("門伏吟")
            elif door and door == opp_door: patterns.append("門反吟")
        return "、".join(patterns)

    @staticmethod
    def get_stem_tags(stem_str, palace):
        h_t, h_p = False, False
        for c in stem_str:
            if (c in ['甲','癸'] and palace=='坤宮') or (c in ['乙','丙','戊'] and palace=='乾宮') or (c in ['丁','己','庚'] and palace=='艮宮') or (c in ['壬','辛'] and palace=='巽宮'): h_t = True
            if (c=='戊' and palace=='震宮') or (c=='己' and palace=='坤宮') or (c=='庚' and palace=='艮宮') or (c=='辛' and palace=='離宮') or (c in ['壬','癸'] and palace=='巽宮'): h_p = True
        if h_t and h_p: return "(刑墓)"
        elif h_t: return "(墓)"
        elif h_p: return "(刑)"
        return ""

    @staticmethod
    def calculate_xun_kong(stem, branch):
        idx = (Const.BRANCHES.index(branch) - Const.STEMS.index(stem) + 12) % 12
        return Const.BRANCHES[(idx - 2) % 12] + Const.BRANCHES[(idx - 1) % 12]

    @staticmethod
    def calculate_12_states(stem_str, palace):
        if not stem_str or palace == "中宮": return ""
        start_map = {"甲": "亥", "丙": "寅", "戊": "寅", "庚": "巳", "壬": "申", "乙": "午", "丁": "酉", "己": "酉", "辛": "子", "癸": "卯"}
        res = ""
        for stem in stem_str:
            if stem not in start_map: continue
            s_idx = Const.BRANCHES.index(start_map[stem])
            branches = Const.PALACE_BRANCHES.get(palace, [])
            if branches:
                t_idx = Const.BRANCHES.index(branches[0])
                if stem in ["甲", "丙", "戊", "庚", "壬"]: res += Const.STATES_12[(t_idx - s_idx + 12) % 12]
                else: res += Const.STATES_12[(s_idx - t_idx + 12) % 12]
        return res

# ==========================================
# 4. FastAPI 進入點與攔截器
# ==========================================
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def clean_stream_content(text: str) -> str:
    patterns = [
        (r"AI", "本大師"), (r"語言模型", "推演系統"), (r"DeepSeek", "玄學大腦"),
        (r"人工智慧", "數理邏輯"), (r"OpenAI", "天體資料庫"), (r"GPT", "星盤程式")
    ]
    for p, r in patterns:
        text = re.sub(p, r, text, flags=re.IGNORECASE)
    return text

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    with open("index.html", "r", encoding="utf-8") as f: return f.read()

@app.get("/manifest.json")
async def get_manifest(): return FileResponse("manifest.json")

@app.get("/sw.js")
async def get_sw(): return FileResponse("sw.js", media_type="application/javascript")

@app.post("/api/v1/divination/calculate", response_model=CalculationResponse)
async def calculate_matrix(request: CalculationRequest):
    safe_time = request.time[:16].replace("T", " ")
    dt = datetime.strptime(safe_time, "%Y-%m-%d %H:%M")
    solar = Solar.fromYmdHms(dt.year, dt.month, dt.day, dt.hour, dt.minute, 0)
    lunar, bazi = solar.getLunar(), solar.getLunar().getEightChar()
    d_s, d_b, h_s, h_b = bazi.getDayGan(), bazi.getDayZhi(), bazi.getTimeGan(), bazi.getTimeZhi()
    hour_xk, ri_xk = RuleEngine.calculate_xun_kong(h_s, h_b), RuleEngine.calculate_xun_kong(d_s, d_b)
    horse_map = {"申":"艮宮", "子":"艮宮", "辰":"艮宮", "寅":"坤宮", "午":"坤宮", "戌":"坤宮", "亥":"巽宮", "卯":"巽宮", "未":"巽宮", "巳":"乾宮", "酉":"乾宮", "丑":"乾宮"}
    wu_bu_yu_map = {"甲":"庚", "乙":"辛", "丙":"壬", "丁":"癸", "戊":"甲", "己":"乙", "庚":"丙", "辛":"丁", "壬":"戊", "癸":"己"}
    term = lunar.getPrevJieQi(True).getName()
    qj = QimenEngine.calculate_ju(term, d_s, d_b)
    ep = QimenEngine.calculate_earth_pan(qj["dun_type"], qj["ju_num"])
    xi = QimenEngine.calculate_xun(h_s, h_b)
    zi = QimenEngine.calculate_zhi_fu_zhi_shi(ep, xi["hidden_stem"])
    hp = QimenEngine.calculate_heaven_pan(ep, h_s, xi["hidden_stem"], zi["palace"])
    dp = QimenEngine.calculate_doors(qj["dun_type"], zi["door"], zi["palace"], xi["jia_name"][1], h_b)
    current_zhi_fu_palace = next((p for p, s in hp["stars"].items() if s == zi["star"]), "坤宮")
    deities = QimenEngine.calculate_deities(qj["dun_type"], current_zhi_fu_palace)
    hs = QimenEngine.calculate_hidden_stems(qj["dun_type"], xi["hidden_stem"] if h_s == "甲" else h_s, next((p for p, d in dp.items() if d == zi["door"]), "中宮"))
    q_matrix = []
    for p_n in ["坎宮", "坤宮", "震宮", "巽宮", "中宮", "乾宮", "兌宮", "艮宮", "離宮"]:
        h_t, e_t, door, star, deity = hp["stems"].get(p_n, ""), ep.get(p_n, ""), dp.get(p_n, ""), hp["stars"].get(p_n, ""), deities.get(p_n, "")
        st = LogicState(
            is_in_tomb="(墓)" in RuleEngine.get_stem_tags(h_t + e_t, p_n),
            is_punished="(刑)" in RuleEngine.get_stem_tags(h_t + e_t, p_n),
            is_empty=any(b in hour_xk for b in Const.PALACE_BRANCHES.get(p_n, [])),
            is_horse=(p_n == horse_map.get(h_b, "")),
            is_door_forced=(RuleEngine.get_door_strength(door, p_n) == "迫")
        )
        q_matrix.append(PalaceData(
            palace_id=p_n, hidden_stem=hs.get(p_n, ""), heaven_stem=h_t, heaven_stem_tags=RuleEngine.get_stem_tags(h_t, p_n), heaven_stem_state=RuleEngine.calculate_12_states(h_t, p_n),
            earth_stem=e_t, earth_stem_tags=RuleEngine.get_stem_tags(e_t, p_n), earth_stem_state=RuleEngine.calculate_12_states(e_t, p_n), door=door, star=star, deity=deity, pattern=RuleEngine.get_pattern(h_t, e_t, star, door, deity, zi["door"], p_n),
            star_strength=RuleEngine.get_star_strength(star, term), door_strength=RuleEngine.get_door_strength(door, p_n), host_guest=RuleEngine.get_interaction(Const.WX_MAP.get(star, "土"), Const.WX_MAP.get(p_n, "土")), logic_states=st
        ))
    return CalculationResponse(solar_time=safe_time, lunar_time=f"{lunar.getYearInChinese()}年{lunar.getMonthInChinese()}月{lunar.getDayInChinese()}日", bazi={"year":bazi.getYear(),"month":bazi.getMonth(),"day":bazi.getDay(),"hour":bazi.getTime(),"day_empty":hour_xk, "is_wby": "True" if wu_bu_yu_map.get(d_s) == h_s else "False"}, qimen_info=QimenInfo(solar_term=term, dun_type=qj["dun_type"], yuan=qj["yuan"], ju_num=qj["ju_num"], hour_xun=xi["full_name"], zhi_fu=zi["star"], zhi_shi=zi["door"], description=qj["description"], ri_kong=ri_xk), qimen_matrix=q_matrix)

# ==========================================
# ✨ 5. 大師深度解盤 API
# ==========================================
api_key = os.environ.get("DEEPSEEK_API_KEY")
client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com") if api_key else None

@app.post("/api/v1/divination/interpret")
async def interpret_matrix(request: CalculationRequest):
    if not client: return StreamingResponse(iter(["**❌ 磁場連接異常**"]), media_type="text/event-stream")
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT u.id, u.credits, u.is_vip FROM users u JOIN sessions s ON u.id = s.user_id WHERE s.token=%s", (request.token,))
    user = c.fetchone()
    if not user: 
        conn.close()
        return StreamingResponse(iter(["**⚠️ 請先登入帳號**"]), media_type="text/event-stream")

    is_free = False
    today_str = date.today().isoformat()
    month_str = date.today().strftime("%Y-%m")
    
    if user["is_vip"]:
        if "專屬每日運程" in request.category:
            c.execute("SELECT count(*) FROM history WHERE user_id=%s AND category LIKE %s AND created_at LIKE %s", (user["id"], '%專屬每日運程%', today_str+"%"))
            if c.fetchone()["count"] == 0: is_free = True
        elif "「命盤」" in request.category:
            c.execute("SELECT count(*) FROM history WHERE user_id=%s AND category LIKE %s AND created_at LIKE %s", (user["id"], '%「命盤」%', month_str+"%"))
            if c.fetchone()["count"] == 0: is_free = True

    if not is_free:
        if user["credits"] < 1: 
            conn.close()
            return StreamingResponse(iter(["**💎 推演能量不足**"]), media_type="text/event-stream")
        c.execute("UPDATE users SET credits = credits - 1 WHERE id=%s", (user["id"],))
    
    # 👑 VIP 本命人自動攔截與八字反查系統 
    seeker_info_prompt = ""
    is_destiny = ("「命盤」" in request.category)
    
    if user["is_vip"] and not is_destiny:
        seeker_match = re.search(r"\(求測人：(.*?)\)", request.question)
        if seeker_match:
            seeker_name = seeker_match.group(1)
            c.execute("SELECT record_time FROM history WHERE user_id=%s AND category=%s ORDER BY created_at DESC LIMIT 1", (user["id"], f"「命盤」{seeker_name}"))
            seeker_record = c.fetchone()
            if seeker_record:
                try:
                    s_dt = datetime.strptime(seeker_record["record_time"][:16].replace("T", " "), "%Y-%m-%d %H:%M")
                    s_solar = Solar.fromYmdHms(s_dt.year, s_dt.month, s_dt.day, s_dt.hour, s_dt.minute, 0)
                    s_bazi = s_solar.getLunar().getEightChar()
                    bz_str = f"{s_bazi.getYearGan()}{s_bazi.getYearZhi()}年 {s_bazi.getMonthGan()}{s_bazi.getMonthZhi()}月 {s_bazi.getDayGan()}{s_bazi.getDayZhi()}日 {s_bazi.getTimeGan()}{s_bazi.getTimeZhi()}時"
                    seeker_info_prompt = f"\n\n【💎 VIP 專屬交叉分析】\n求測人「{seeker_name}」本命八字：{bz_str}。請務必將此奇門局象與本命人的八字進行交叉共振分析，給出專屬指引！"
                except Exception: pass
                    
    conn.commit()
    conn.close()
    
    try:
        matrix_data = await calculate_matrix(request)
        # 🌟 執行五行量化評分 (QuantityEvaluator)
        bazi_eval = QuantityEvaluator.evaluate(matrix_data.bazi)

        # 🌟 將評分數據轉化為 AI 專用的引導文字 (請接在 bazi_eval 之後)
        eval_text = f"""
\n【⚖️ 核心數據：五行量化能量分析 (LLM 必讀)】
- 日主旺衰基準：{bazi_eval['day_master_strength']}
- 五行細分得分：{bazi_eval['scores']}
- 喜用五行（必須生旺）：{', '.join(bazi_eval['xi_yong'])}
- 忌諱五行（絕對避開）：{', '.join(bazi_eval['ji_shen'])}
- 決策指令：若奇門方位/顏色與忌諱五行衝突，必須使用『通關轉譯法』。
"""
        
        # 將評分數據轉化為 AI 專用的引導文字
        palace_details = "".join([f"[{p.palace_id}] 天:{p.heaven_stem}/{p.earth_stem}, 星:{p.star}, 門:{p.door}, 神:{p.deity}, 格:{p.pattern}\n" for p in matrix_data.qimen_matrix])
        
        # 🌟 日干時干抓取
        day_stem = matrix_data.bazi['day'][0]
        hour_stem = matrix_data.bazi['hour'][0]
        bazi_str = f"{matrix_data.bazi['year']} {matrix_data.bazi['month']} {matrix_data.bazi['day']} {matrix_data.bazi['hour']}"
        
        # 🌟 真實年齡推算
        try:
            dt = datetime.strptime(request.time[:16].replace("T", " "), "%Y-%m-%d %H:%M")
            age = date.today().year - dt.year
        except:
            age = "未知"

        identity_prompt = f"\n【代體識別】求測人(日干)為「{day_stem}」，事體(時干)為「{hour_stem}」。請精確定位。"

        if is_destiny:
            # ==========================================
            # 📜 【終身命盤】解讀邏輯 (格局、底色、長線)
            # ==========================================
            destiny_context = f"""
\n【⚠️ 核心鐵律：終身命卦架構與年齡適配】
1. 視角隔離：此為【終身格局】推演。請從「本命身分」出發，解讀求測人一生的人格特質、天賦能量與家庭根基。
2. 年齡適配：求測人目前 {age} 歲，身分現況為「{request.status}」。解讀必須符合此年齡段的社會邏輯。
   - 若為「未成年/學生」：將『財運』轉化為『學業資源』，絕不可談論職場競爭或婚姻成敗！
   - 若為「退休長者」：請著重養生、家庭和睦與晚年生活。
   - 若為「老闆/就業」：請著重事業發展與實質財富。

\n【🔥 終極密令：雙系統玄學融合校準 (Bazi-Qimen Calibration Protocol)】
1. 確立主從關係：子平八字為【體】（主、核心底色），奇門遁甲為【用】（從、時空工具）。
2. 規則：奇門遁甲所生成的「幸運五行」與「顏色」，必須在八字的「喜用神」框架內進行過濾，絕對不允許輸出與八字喜用神相衝、相剋的五行/顏色。
3. 動態校準演算法：
   - Step 1：獲取八字底色（確認求測人八字喜用神，如：喜水木、忌土金）。
   - Step 2：解讀奇門局部（找出當前盤中帶吉門吉星的奇門五行）。
   - Step 3：交叉過濾。若奇門五行是八字忌神，【必須強行校準】。AI 必須尋找奇門盤中「既符合吉方，又能生旺八字喜用」的次強五行。
4. 顏色轉譯規則（通關法）：若奇門利「金」（白）但八字忌金喜水。不可輸出白色，應輸出黑色/藍色（水），取「金生水」之意轉化能量。
"""
            
            # 這裡注入 eval_text，讓 AI 拿到硬數據進行解盤
            prompt = f"""你是奇門遁甲頂級大師。推演類別：【{request.category}】。{identity_prompt}{destiny_context}
{eval_text} 
求測人八字：{bazi_str}
起盤數據：局勢：{matrix_data.qimen_info.description}，旬首：{matrix_data.qimen_info.hour_xun}，詳情：\n{palace_details}

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
            # ==========================================
            # 🏹 【時家事體】解讀邏輯 (當下、動態、戰術) + 隔離令
            # ==========================================
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
            yongshen_prompt = f"\n【用神定位法則】此次推演類別為【{request.category}】。請大師務必嚴格依據類別選取「專屬用神」（例如：求財看生門/戊，事業看開門，運勢看日干與時干生剋），並以此作為解盤核心！"

            prompt = f"""你是奇門遁甲國師。推演類別：【{request.category}】，背景：【{request.question}】{identity_prompt}{event_context}{yongshen_prompt}
起盤數據：局勢：{matrix_data.qimen_info.description}，旬首：{matrix_data.qimen_info.hour_xun}，詳情：\n{palace_details}

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
            stream = await client.chat.completions.create(
                model="deepseek-chat", 
                messages=[
                    {"role": "system", "content": "你是香港頂級奇門遁甲大師，語氣莊重專業、客觀權威。請務必全程使用「香港繁體中文的書面語」進行解答（符合香港人的閱讀習慣，避免內地網絡用語，但保持高級命理顧問的質感）。絕對禁止透露 AI 身份。"}, 
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7, stream=True
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content: yield clean_stream_content(content)

        return StreamingResponse(generate(), media_type="text/event-stream")
    except Exception as e:
        return StreamingResponse(iter([f"**❌ 磁場異常**：{str(e)}"]), media_type="text/event-stream")

# ==========================================
# 6. 會員、歷史與 Stripe 
# ==========================================
@app.post("/api/v1/auth/register")
def register(req: AuthRequest):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username=%s", (req.username,))
        if c.fetchone(): 
            return {"status": "error", "message": "帳號已存在"}
        
        if req.email:
            c.execute("SELECT id FROM users WHERE email=%s", (req.email,))
            if c.fetchone():
                return {"status": "error", "message": "此 Email 已被使用"}
    
        user_id = str(uuid.uuid4())
        pwd_hash = hashlib.sha256(req.password.encode()).hexdigest()
        
        c.execute("INSERT INTO users (id, username, password_hash, credits, is_vip, email) VALUES (%s, %s, %s, 3, FALSE, %s)", 
                  (user_id, req.username, pwd_hash, req.email))
        conn.commit()
        return {"status": "success", "message": "註冊成功，送 3 點推演能量"}
    except Exception as e:
        if conn: conn.rollback()
        print(f"註冊錯誤: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        if conn: conn.close()

@app.post("/api/v1/auth/forgot-password")
async def forgot_password(req: Dict):
    user_email = req.get("email")
    if not user_email: return {"status": "error", "message": "請提供 Email"}

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT username FROM users WHERE email=%s", (user_email,))
    user = c.fetchone()
    conn.close()

    if not user:
        return {"status": "success", "message": "若帳號存在，系統將發送重置指示"}

    # ✉️ 組合信件內容
    msg_content = f"【奇門大師】您好，您的帳號是：{user['username']}\n若您忘記密碼，請聯繫管理員重置，或回覆此信件。"
    msg = MIMEText(msg_content)
    msg['Subject'] = "【奇門大師】帳號找回通知"
    msg['From'] = SENDER_EMAIL
    msg['To'] = user_email

    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            if SENDER_PASSWORD:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.send_message(msg)
        return {"status": "success", "message": "重置指示已發送到您的信箱"}
    except Exception as e:
        print(f"發信錯誤: {e}")
        return {"status": "error", "message": "郵件系統暫時無法連線"}

@app.post("/api/v1/auth/login")
def login(req: AuthRequest):
    conn = get_db()
    c = conn.cursor()
    try:
        pwd_hash = hashlib.sha256(req.password.encode()).hexdigest()
        c.execute("SELECT id, credits, is_vip FROM users WHERE username=%s AND password_hash=%s", (req.username, pwd_hash))
        row = c.fetchone()
        
        if not row: 
            return {"status": "error", "message": "帳號或密碼錯誤"}
            
        user = dict(row)
        
        # 👑 終極測試帳號外掛
        if req.username.lower() == "tester":
            c.execute("UPDATE users SET credits=9999, is_vip=TRUE WHERE id=%s", (user["id"],))
            conn.commit()
            user["credits"] = 9999
            user["is_vip"] = True
        
        token = str(uuid.uuid4())
        c.execute("INSERT INTO sessions (token, user_id) VALUES (%s, %s)", (token, user["id"]))
        conn.commit()
        
        return {"status": "success", "token": token, "username": req.username, "credits": user["credits"], "is_vip": user["is_vip"]}
    except Exception as e:
        conn.rollback()
        print("登入錯誤:", e)
        return {"status": "error", "message": "系統登入異常，請稍後再試"}
    finally:
        conn.close()

@app.post("/api/v1/user/info")
def get_user_info(req: Dict):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT u.username, u.credits, u.is_vip FROM users u JOIN sessions s ON u.id = s.user_id WHERE s.token=%s", (req.get('token'),))
    user = c.fetchone(); conn.close()
    if not user: return {"status": "error"}
    return {"status": "success", "username": user["username"], "credits": user["credits"], "is_vip": user["is_vip"]}

@app.post("/api/v1/history/save")
def save_history(req: Dict):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT user_id FROM sessions WHERE token=%s", (req.get('token'),))
    session = c.fetchone()
    if not session: return {"status": "error"}
    c.execute("INSERT INTO history (id, user_id, category, record_time, report_text, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
              (str(uuid.uuid4()), session["user_id"], req.get('category'), req.get('record_time'), req.get('report_text'), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit(); conn.close(); return {"status": "success"}

@app.post("/api/v1/history/list")
def list_history(req: Dict):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT user_id FROM sessions WHERE token=%s", (req.get('token'),))
    session = c.fetchone()
    if not session: return {"status": "error"}
    c.execute("SELECT id, category, record_time, created_at, report_text, is_pinned FROM history WHERE user_id=%s ORDER BY created_at DESC", (session["user_id"],))
    records = [dict(row) for row in c.fetchall()]; conn.close()
    return {"status": "success", "data": records}

@app.post("/api/v1/history/detail")
def detail_history(req: Dict):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM history WHERE id=%s", (req.get('record_id'),))
    record = c.fetchone(); conn.close()
    return {"status": "success", "data": dict(record)} if record else {"status": "error"}

@app.post("/api/v1/history/delete")
def delete_history(req: Dict):
    conn = get_db(); c = conn.cursor()
    c.execute("DELETE FROM history WHERE id=%s", (req.get('record_id'),))
    conn.commit(); conn.close(); return {"status": "success"}

@app.post("/api/v1/payment/create-checkout-session")
def create_checkout_session(req: Dict):
    if not stripe.api_key: return {"status": "error", "message": "Stripe 未設定"}
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT u.id FROM users u JOIN sessions s ON u.id = s.user_id WHERE s.token=%s", (req.get('token'),))
    user = c.fetchone()
    conn.close()
    
    if not user: return {"status": "error", "message": "請先登入"}
    
    plan = req.get('plan') 
    
    # ✨ Stripe 商品價目表
    plans = {
        "vip_monthly": {"price": "price_1TWoBB3V96ZHfX3JG75wInUE", "mode": "subscription", "action": "vip"},
        "vip_lifetime": {"price": "price_1TWo0c3V96ZHfX3JGcctcTL3", "mode": "payment", "action": "vip"},
        "topup_5": {"price": "price_1TWoGE3V96ZHfX3JxWCUpV8G", "mode": "payment", "action": "add_5"},
        "topup_15": {"price": "price_1TWoHh3V96ZHfX3Jdq5GMHyl", "mode": "payment", "action": "add_15"},
    }
    
    selected_plan = plans.get(plan)
    if not selected_plan: return {"status": "error", "message": "無效的商品選項"}
        
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': selected_plan["price"],
                'quantity': 1,
            }],
            mode=selected_plan["mode"],
            success_url="https://kenttangtel-qimen-api.hf.space/?payment=success",
            cancel_url="https://kenttangtel-qimen-api.hf.space/?payment=cancel",
            client_reference_id=user['id'],
            metadata={"action": selected_plan["action"]} 
        )
        return {"status": "success", "url": session.url}
    except Exception as e: 
        return {"status": "error", "message": str(e)}

@app.post("/webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return {"error": str(e)}

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        user_id = session.get('client_reference_id')
        action = session.get('metadata', {}).get('action')
        
        if user_id and action:
            conn = get_db()
            c = conn.cursor()
            
            if action == "vip":
                c.execute("UPDATE users SET is_vip = TRUE WHERE id = %s", (user_id,))
                print(f"用户 {user_id} 升級為 VIP！")
            elif action == "add_5":
                c.execute("UPDATE users SET credits = credits + 5 WHERE id = %s", (user_id,))
                print(f"用户 {user_id} 補充 5 點能量！")
            elif action == "add_15":
                c.execute("UPDATE users SET credits = credits + 15 WHERE id = %s", (user_id,))
                print(f"用户 {user_id} 補充 15 點能量！")
                
            conn.commit()
            conn.close()

    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)