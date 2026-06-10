from typing import Dict, List


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
        "坎宮": ("天蓬星", "休門"), "坤宮": ("天芮星", "死門"), "震宮": ("天衝星", "傷門"), "巽宮": ("天輔星", "杜門"),
        "中宮": ("天禽星", "死門"), "乾宮": ("天心星", "開門"), "兌宮": ("天柱星", "驚門"), "艮宮": ("天任星", "生門"), "離宮": ("天英星", "景門")
    }
    PALACE_BRANCHES = {"坎宮": ["子"], "艮宮": ["丑", "寅"], "震宮": ["卯"], "巽宮": ["辰", "巳"], "離宮": ["午"], "坤宮": ["未", "申"], "兌宮": ["酉"], "乾宮": ["戌", "亥"]}
    SOLAR_TERM_JU = {
        "冬至": ("陽遁", [1, 7, 4]), "小寒": ("陽遁", [2, 8, 5]), "大寒": ("陽遁", [3, 9, 6]), "立春": ("陽遁", [8, 5, 2]),
        "雨水": ("陽遁", [9, 6, 3]), "驚蟄": ("陽遁", [1, 7, 4]), "春分": ("陽遁", [3, 9, 6]), "清明": ("陽遁", [4, 1, 7]),
        "穀雨": ("陽遁", [5, 2, 8]), "立夏": ("陽遁", [4, 1, 7]), "小滿": ("陽遁", [5, 2, 8]), "芒種": ("陽遁", [6, 3, 9]),
        "夏至": ("陰遁", [9, 3, 6]), "小暑": ("陰遁", [8, 2, 5]), "大暑": ("陰遁", [7, 1, 4]), "立秋": ("陰遁", [2, 5, 8]),
        "處暑": ("陰遁", [1, 4, 7]), "白露": ("陰遁", [9, 3, 6]), "秋分": ("陰遁", [7, 1, 4]), "寒露": ("陰遁", [6, 9, 3]),
        "霜降": ("陰遁", [5, 8, 2]), "立冬": ("陰遁", [6, 9, 3]), "小雪": ("陰遁", [5, 8, 2]), "大雪": ("陰遁", [4, 7, 1])
    }


class QuantityEvaluator:
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
            if k in name:
                return v
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
            xi_yong = [e for e in ["木", "火", "土", "金", "水"] if e not in support_elements[dm_element]]
            ji_shen = support_elements[dm_element]
        else:
            xi_yong = support_elements[dm_element]
            ji_shen = [e for e in ["木", "火", "土", "金", "水"] if e not in support_elements[dm_element]]

        return {
            "scores": scores,
            "day_master_strength": "偏旺" if is_strong else "偏弱",
            "xi_yong": xi_yong,
            "ji_shen": ji_shen
        }


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
        if target_palace == "中宮":
            target_palace = "坤宮"
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
        if target_palace == "中宮":
            target_palace = "坤宮"
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
        if current_zhi_shi_palace == "中宮":
            current_zhi_shi_palace = "坤宮"
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
        if not star:
            return ""
        star_wx = Const.WX_MAP.get(star)
        season_wx = "土"
        if solar_term in ["立春", "雨水", "驚蟄", "春分", "清明", "穀雨"]:
            season_wx = "木"
        elif solar_term in ["立夏", "小滿", "芒種", "夏至", "小暑", "大暑"]:
            season_wx = "火"
        elif solar_term in ["立秋", "處暑", "白露", "秋分", "寒露", "霜降"]:
            season_wx = "金"
        elif solar_term in ["立冬", "小雪", "大雪", "冬至", "小寒", "大寒"]:
            season_wx = "水"
        if star_wx == season_wx:
            return "旺"
        rel_map = {
            "木": {"火":"旺", "水":"廢", "土":"休", "金":"囚"},
            "火": {"土":"旺", "木":"廢", "金":"休", "水":"囚"},
            "土": {"金":"旺", "火":"廢", "水":"休", "木":"囚"},
            "金": {"水":"旺", "土":"廢", "木":"休", "火":"囚"},
            "水": {"木":"旺", "金":"廢", "火":"休", "土":"囚"}
        }
        return rel_map.get(star_wx, {}).get(season_wx, "廢")

    @staticmethod
    def get_door_strength(door, palace):
        if not door or not palace:
            return ""
        door_wx = Const.WX_MAP.get(door)
        palace_wx = Const.WX_MAP.get(palace)
        if palace_wx == door_wx:
            return "相"
        rel_map = {
            "木": {"土":"囚", "火":"休", "水":"旺", "金":"迫"},
            "火": {"金":"囚", "土":"休", "木":"旺", "水":"迫"},
            "土": {"水":"囚", "金":"休", "火":"旺", "木":"迫"},
            "金": {"木":"囚", "水":"休", "土":"旺", "火":"迫"},
            "水": {"火":"囚", "木":"休", "金":"旺", "土":"迫"}
        }
        return rel_map.get(door_wx, {}).get(palace_wx, "休")

    @staticmethod
    def get_pattern(h_stem, e_stem, star, door, deity, zhi_shi, palace):
        patterns = []
        if "戊" in h_stem and "戊" in e_stem:
            patterns.append("青龍伏吟")
        elif "乙" in h_stem and "乙" in e_stem:
            patterns.append("日奇伏吟")
        elif "丁" in h_stem and "癸" in e_stem:
            patterns.append("朱雀投江")
        elif "癸" in h_stem and "丁" in e_stem:
            patterns.append("騰蛇夭矯")
        elif "丙" in h_stem and "戊" in e_stem:
            patterns.append("飛鳥跌穴")
        elif "戊" in h_stem and "丙" in e_stem:
            patterns.append("青龍返首")
        elif "乙" in h_stem and "辛" in e_stem:
            patterns.append("青龍逃走")
        elif "辛" in h_stem and "乙" in e_stem:
            patterns.append("白虎猖狂")
        if "丙" in h_stem and "丁" in e_stem and door == "生門":
            patterns.append("天遁")
        if "乙" in h_stem and "己" in e_stem and deity == "九地":
            patterns.append("地遁")
        if "丁" in h_stem and "乙" in e_stem and deity == "太陰":
            patterns.append("人遁")
        if palace != "中宮":
            orig_star, orig_door = Const.ORIGINAL_STAR_DOOR.get(palace, ("", ""))
            opp_p = {"坎宮":"離宮", "艮宮":"坤宮", "震宮":"兌宮", "巽宮":"乾宮", "離宮":"坎宮", "坤宮":"艮宮", "兌宮":"震宮", "乾宮":"巽宮"}.get(palace)
            opp_star, opp_door = Const.ORIGINAL_STAR_DOOR.get(opp_p, ("", ""))
            if star and star == orig_star:
                patterns.append("星伏吟")
            elif star and star == opp_star:
                patterns.append("星反吟")
            if door and door == orig_door:
                patterns.append("門伏吟")
            elif door and door == opp_door:
                patterns.append("門反吟")
        return "、".join(patterns)

    @staticmethod
    def get_stem_tags(stem_str, palace):
        h_t, h_p = False, False
        for c in stem_str:
            if (c in ['甲','癸'] and palace=='坤宮') or (c in ['乙','丙','戊'] and palace=='乾宮') or (c in ['丁','己','庚'] and palace=='艮宮') or (c in ['壬','辛'] and palace=='巽宮'):
                h_t = True
            if (c=='戊' and palace=='震宮') or (c=='己' and palace=='坤宮') or (c=='庚' and palace=='艮宮') or (c=='辛' and palace=='離宮') or (c in ['壬','癸'] and palace=='巽宮'):
                h_p = True
        if h_t and h_p:
            return "(刑墓)"
        elif h_t:
            return "(墓)"
        elif h_p:
            return "(刑)"
        return ""

    @staticmethod
    def calculate_xun_kong(stem, branch):
        idx = (Const.BRANCHES.index(branch) - Const.STEMS.index(stem) + 12) % 12
        return Const.BRANCHES[(idx - 2) % 12] + Const.BRANCHES[(idx - 1) % 12]

    @staticmethod
    def calculate_12_states(stem_str, palace):
        if not stem_str or palace == "中宮":
            return ""
        start_map = {"甲": "亥", "丙": "寅", "戊": "寅", "庚": "巳", "壬": "申", "乙": "午", "丁": "酉", "己": "酉", "辛": "子", "癸": "卯"}
        res = ""
        for stem in stem_str:
            if stem not in start_map:
                continue
            s_idx = Const.BRANCHES.index(start_map[stem])
            branches = Const.PALACE_BRANCHES.get(palace, [])
            if branches:
                t_idx = Const.BRANCHES.index(branches[0])
                if stem in ["甲", "丙", "戊", "庚", "壬"]:
                    res += Const.STATES_12[(t_idx - s_idx + 12) % 12]
                else:
                    res += Const.STATES_12[(s_idx - t_idx + 12) % 12]
        return res