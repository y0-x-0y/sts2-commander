"""CardDB — 卡牌数据的单一数据源。

所有卡牌查询统一走 detail(name) → {cost, type, rarity, keywords, desc_cn, id}。
数据来自 card_tooltip_db.json（569张牌的完整信息）。
"""

import html as _html
import json
import os
import re

from overlay.constants import (
    CARD_DB_FILE, _proj,
)

# ── 公用常量（定义一次，到处引用）──────────────────
TYPE_EN = {"攻击": "attack", "技能": "skill", "能力": "power",
           "诅咒": "curse", "状态": "status"}
TYPE_CN = {"attack": "攻击", "skill": "技能", "power": "能力",
           "curse": "诅咒", "status": "状态", "other": "其他"}
RARITY_CN = {"basic": "基础", "common": "普通", "uncommon": "罕见",
             "rare": "稀有", "ancient": "远古"}
RARITY_EN = {"基础": "basic", "普通": "common", "罕见": "uncommon",
             "稀有": "rare", "远古": "ancient"}
BASIC_CARDS = {"打击", "防御", "Strike", "Defend"}

# 太短/太常见的名字，tooltip 不匹配
_SKIP_TOOLTIP = {"打击", "防御", "状态", "能力", "攻击", "技能", "诅咒",
                 "烧伤", "伤口", "眩晕", "虚空", "召唤", "死神", "灵魂",
                 "愤怒", "恐惧", "冲击", "突破", "混沌", "燃烧"}


class CardDB:
    """卡牌数据库 — 启动时加载一次，运行时只有 collect_cards 会写入。"""

    def __init__(self):
        # ── 1. 运行时收集的卡牌（可变，由 collect_cards 更新）──
        self._runtime = self._load_json(CARD_DB_FILE, {})

        # ── 2. 完整信息：id↔中文名 映射 ──
        self._id_to_cn = {}   # "ReaperForm" → "死神形态"
        self._cn_to_id = {}   # "死神形态" → "ReaperForm"
        self._load_id_map()

        # ── 3. 统一卡牌数据库（唯一数据源）──
        # cn_name → {id, name_cn, cost, type, rarity, keywords, desc_cn}
        self._tooltip = self._load_json(_proj("data", "cards", "card_tooltip_db.json"), {})

        # ── 4. tooltip 替换用的预排序列表 ──
        self._tooltip_names = sorted(
            [n for n in self._tooltip if n not in _SKIP_TOOLTIP and len(n) >= 2],
            key=len, reverse=True
        )
        self._en_names = sorted(
            [eid for eid in self._id_to_cn if len(eid) >= 3 and self._id_to_cn[eid] in self._tooltip],
            key=len, reverse=True
        )
        # ── 5. 翻译用（含 CamelCase 拆分变体）──
        self._en_translate = {}
        for eid, cn in self._id_to_cn.items():
            self._en_translate[eid] = cn
            spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', eid)
            if spaced != eid:
                self._en_translate[spaced] = cn

        print(f"[CardDB] Ready: {len(self._tooltip)} cards, "
              f"{len(self._id_to_cn)} id→cn")

    # ══════════════════════════════════════════
    #  公开查询接口
    # ══════════════════════════════════════════

    def detail(self, name: str) -> dict:
        """完整信息 dict，给 tooltip/UI 用。
        返回 {cost, type, rarity, keywords, desc_cn, id} 或空 dict。
        """
        return self._tooltip.get(name, {})

    def id_to_cn(self, english_id: str) -> str:
        """英文 ID → 中文名。找不到返回 ''。"""
        return self._id_to_cn.get(english_id, "")

    def get_type(self, card: dict) -> str:
        """从 API 卡牌 dict 获取归一化类型 ('attack'/'skill'/'power'/…)。"""
        t = (card.get("type") or card.get("card_type") or "").lower()
        if not t:
            cid = card.get("id", "").replace("CARD.", "")
            t = self._runtime.get(cid, {}).get("type", "").lower()
        if not t:
            name = card.get("name", "")
            tip = self._tooltip.get(name, {})
            t = tip.get("type", "").lower() if tip else ""
        return self._normalize_type(t)

    def get_rarity(self, card: dict) -> str:
        """从 API 卡牌 dict 获取归一化稀有度 ('basic'/'common'/…)。"""
        r = (card.get("rarity") or "").lower()
        if not r:
            cid = card.get("id", "").replace("CARD.", "")
            r = self._runtime.get(cid, {}).get("rarity", "").lower()
        if not r:
            name = card.get("name", "")
            tip = self._tooltip.get(name, {})
            r = tip.get("rarity", "").lower() if tip else ""
        r = self._normalize_rarity(r)
        if not r:
            name = card.get("name", "")
            cid = card.get("id", "")
            if name in BASIC_CARDS or "STRIKE" in cid.upper() or "DEFEND" in cid.upper():
                r = "basic"
        return r

    def fmt_name(self, card: dict) -> str:
        """获取卡牌中文显示名。"""
        if card.get("name"):
            return card["name"]
        cid = card.get("id", "?").replace("CARD.", "")
        cn = self._id_to_cn.get(cid, "")
        if cn:
            return cn
        rt = self._runtime.get(cid, {})
        if rt.get("name"):
            return rt["name"]
        return cid.replace("_", " ").title()

    def translate(self, text: str) -> str:
        """将 AI 输出中的英文卡牌 ID 替换为中文名（含模糊匹配兜底）。"""
        for en, cn in sorted(self._en_translate.items(), key=lambda x: -len(x[0])):
            if en in text:
                text = text.replace(en, cn)
        # 模糊匹配剩余的 PascalCase 英文名（可能是 AI 幻觉）
        remaining = re.findall(r'(?<![A-Za-z])([A-Z][a-z]+(?:[A-Z][a-z]+)+)(?![a-z])', text)
        for word in remaining:
            cn = self._fuzzy_find(word)
            if cn:
                text = text.replace(word, cn)
        return text

    def add_tooltips(self, html_str: str) -> str:
        """扫描 HTML 中的卡牌名，包裹 tooltip span。"""
        tokens = {}
        counter = [0]

        def make_token(display_name, tip_data):
            token = f'\x00TIP{counter[0]}\x00'
            counter[0] += 1
            if isinstance(tip_data, dict):
                box = self._build_tooltip_html(tip_data)
            else:
                box = _html.escape(str(tip_data)[:100])
            tokens[token] = (f'<span class="card-tip">{display_name}'
                             f'<span class="card-tip-box">{box}</span></span>')
            return token

        # 1. 英文 ID → 中文名 + tooltip
        for eid in self._en_names:
            if eid not in html_str:
                continue
            cn = self._id_to_cn[eid]
            tip = self._tooltip.get(cn, {})
            html_str = re.sub(
                r'(?<!["\w])' + re.escape(eid) + r'(?!["\w])',
                lambda m, _cn=cn, _tip=tip: make_token(_cn, _tip),
                html_str, count=3
            )

        # 2. 中文卡牌名（最长优先）
        for name in self._tooltip_names:
            escaped = _html.escape(name)
            if escaped not in html_str:
                continue
            tip = self._tooltip[name]
            html_str = html_str.replace(escaped, make_token(escaped, tip), 3)

        # 3. 还原 token
        for token, replacement in tokens.items():
            html_str = html_str.replace(token, replacement)
        return html_str

    # ── 运行时收集 ──

    def collect(self, state: dict):
        """从 API state 收集卡牌信息到运行时 DB。"""
        changed = False
        for section in ("hand", "draw_pile", "discard_pile", "exhaust_pile"):
            cards = []
            battle = state.get("battle", {})
            player = battle.get("player", {})
            cards = player.get(section, [])
            for c in cards:
                cid = c.get("id", "").replace("CARD.", "")
                if cid and cid not in self._runtime:
                    self._runtime[cid] = {
                        "name": c.get("name", cid),
                        "cost": c.get("cost"),
                        "type": c.get("type", ""),
                        "description": c.get("description", ""),
                    }
                    changed = True
        # 也收集 deck 里的
        for src in (state.get("battle", {}).get("player", {}),
                    state.get("player", {})):
            for c in src.get("deck", []):
                cid = c.get("id", "").replace("CARD.", "")
                name = c.get("name", "")
                if cid and cid not in self._runtime and name:
                    self._runtime[cid] = {
                        "name": name,
                        "cost": c.get("cost"),
                        "type": c.get("type", ""),
                    }
                    changed = True
        if changed:
            self.save()

    def save(self):
        """保存运行时 DB 到磁盘。"""
        try:
            os.makedirs(os.path.dirname(CARD_DB_FILE), exist_ok=True)
            with open(CARD_DB_FILE, "w") as f:
                json.dump(self._runtime, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ── 给 prompt 注入用 ──

    def runtime_get(self, cid: str) -> dict:
        """直接访问运行时 DB（兼容旧代码过渡期使用）。"""
        return self._runtime.get(cid, {})

    # ══════════════════════════════════════════
    #  私有加载方法
    # ══════════════════════════════════════════

    @staticmethod
    def _load_json(path, default=None):
        try:
            if os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
        except Exception:
            pass
        return default if default is not None else {}

    def _load_id_map(self):
        """从 character_cards.json 构建 英文ID ↔ 中文名 映射。"""
        cc = self._load_json(_proj("data", "cards", "character_cards.json"), {})
        for char_name, cards in cc.items():
            if not isinstance(cards, list):
                continue
            for c in cards:
                cid = c.get("id", "")
                name = c.get("name", "")
                if not cid or not name:
                    continue
                self._id_to_cn[cid] = name
                self._id_to_cn[cid.upper()] = name
                snake = re.sub(r'(?<=[a-z])(?=[A-Z])', '_', cid).upper()
                if snake != cid.upper():
                    self._id_to_cn[snake] = name
                self._cn_to_id[name] = cid
                # 补充运行时 DB
                for key in (cid, cid.upper(), snake):
                    if key not in self._runtime:
                        self._runtime[key] = {
                            "name": name,
                            "cost": c.get("cost", "?"),
                            "type": c.get("type", ""),
                        }
        # 也从 merged DB 补充
        mdb = self._load_json(_proj("data", "cards", "card_database_merged.json"), {})
        for k, v in mdb.items():
            cn = v.get("name_cn", "")
            if cn and k != cn and k not in self._id_to_cn:
                self._id_to_cn[k] = cn

    # ── 归一化 ──

    @staticmethod
    def _normalize_type(t: str) -> str:
        if "attack" in t or "攻击" in t: return "attack"
        if "skill" in t or "技能" in t: return "skill"
        if "power" in t or "能力" in t: return "power"
        if "curse" in t or "诅咒" in t: return "curse"
        if "status" in t or "状态" in t: return "status"
        return "other"

    @staticmethod
    def _normalize_rarity(r: str) -> str:
        rl = r.lower()
        if "基础" in r or "basic" in rl: return "basic"
        if "罕见" in r or "uncommon" in rl: return "uncommon"  # before common!
        if "普通" in r or "common" in rl: return "common"
        if "稀有" in r or rl == "rare": return "rare"
        if "远古" in r or "ancient" in rl: return "ancient"
        if "诅咒" in r or "curse" in rl: return "basic"
        if "status" in rl: return "basic"
        return ""

    # ── tooltip HTML 构建 ──

    @staticmethod
    def _build_tooltip_html(tip: dict) -> str:
        parts = []
        cost = tip.get("cost", "")
        ctype = tip.get("type", "")
        rarity = tip.get("rarity", "")
        kw = tip.get("keywords", "")
        desc = tip.get("desc_cn", "")
        header = []
        if cost != "":
            header.append(f'<span class="ct-cost">{cost}费</span>')
        if ctype:
            header.append(f'<span class="ct-type">{_html.escape(ctype)}</span>')
        if rarity:
            header.append(f'<span class="ct-rarity-{_html.escape(rarity)}">{_html.escape(rarity)}</span>')
        if header:
            parts.append('<span class="ct-sep">·</span>'.join(header))
        if kw:
            parts.append(f' <span class="ct-kw">{_html.escape(kw)}</span>')
        if desc:
            parts.append(f'<span class="ct-desc">{_html.escape(desc[:100])}</span>')
        return "".join(parts)

    # ── 模糊匹配 ──

    def _fuzzy_find(self, word: str):
        wl = word.lower()
        best, best_score = None, 0
        for eid, cn in self._id_to_cn.items():
            if len(eid) < 4:
                continue
            el = eid.lower()
            i = j = matches = 0
            while i < len(wl) and j < len(el):
                if wl[i] == el[j]:
                    matches += 1
                    i += 1
                j += 1
            score = matches / max(len(wl), len(el))
            if score > best_score:
                best_score = score
                best = cn
        return best if best_score >= 0.6 else None
