"""DisplayMixin — 所有自动显示方法（不调用LLM）。

修改UI格式只需编辑此文件。
pywebview v6.0 — builds HTML strings and pushes via JS.
"""
import html
import json
import re as _re
import requests
from overlay.constants import (
    API_URL, INTENT_CN,
    _cn_power, _cn_relic, _cn_potion,
)
from overlay.card_db import TYPE_CN, RARITY_CN


class DisplayMixin:

    # ══════════════════════════════════════════
    #  CLASS-LEVEL CONSTANTS
    # ══════════════════════════════════════════
    _RARITY_COLOR = {"basic": "var(--dim)", "common": "var(--text)", "uncommon": "var(--block)",
                     "rare": "var(--gold)", "ancient": "var(--accent2)"}
    _RARITY_CN = RARITY_CN
    _UPGRADED_COLOR = "var(--buff)"
    _TYPE_CN = TYPE_CN
    _TYPE_LABEL_COLOR = {
        "attack": ("攻击", "var(--hp)"), "skill": ("技能", "var(--block)"),
        "power": ("能力", "var(--buff)"),
    }
    _TYPE_ORDER = ["attack", "skill", "power"]
    _NODE_CN = {
        "Monster": "普通怪", "Elite": "精英怪", "Boss": "Boss",
        "Shop": "商店", "Rest": "休息点", "RestSite": "休息点",
        "Event": "事件", "Treasure": "宝箱", "Unknown": "未知", "Ancient": "古代事件",
    }
    _SVG_ICONS = {
        "Monster": '<svg viewBox="0 0 16 16"><path d="M8 2v8M6 4l2-2 2 2M5 10l6 0M6 10l-1 4M10 10l1 4" stroke="#d47a30" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg>',
        "Elite": '<svg viewBox="0 0 16 16"><circle cx="8" cy="7" r="4.5" stroke="#e74c3c" stroke-width="1.3" fill="none"/><circle cx="6.5" cy="6.5" r="1" fill="#e74c3c"/><circle cx="9.5" cy="6.5" r="1" fill="#e74c3c"/><path d="M6 9.5h4" stroke="#e74c3c" stroke-width="1"/><path d="M7 12v2M9 12v2" stroke="#e74c3c" stroke-width="1.2" stroke-linecap="round"/></svg>',
        "Rest": '<svg viewBox="0 0 16 16"><path d="M8 3C6 6 4 8 4 10.5a4 4 0 0 0 8 0C12 8 10 6 8 3z" fill="#45c480" opacity="0.9"/><path d="M8 7c-.8 1.2-1.5 2-1.5 3a1.5 1.5 0 0 0 3 0c0-1-.7-1.8-1.5-3z" fill="#0a0610" opacity="0.5"/></svg>',
        "RestSite": '<svg viewBox="0 0 16 16"><path d="M8 3C6 6 4 8 4 10.5a4 4 0 0 0 8 0C12 8 10 6 8 3z" fill="#45c480" opacity="0.9"/><path d="M8 7c-.8 1.2-1.5 2-1.5 3a1.5 1.5 0 0 0 3 0c0-1-.7-1.8-1.5-3z" fill="#0a0610" opacity="0.5"/></svg>',
        "Shop": '<svg viewBox="0 0 16 16"><path d="M5 6c0-2 1.5-3 3-3s3 1 3 3" stroke="#d4a840" stroke-width="1.3" fill="none"/><rect x="3.5" y="6" width="9" height="7" rx="1.5" fill="none" stroke="#d4a840" stroke-width="1.3"/><text x="8" y="11.5" text-anchor="middle" fill="#d4a840" font-size="6" font-weight="700">$</text></svg>',
        "Event": '<svg viewBox="0 0 16 16"><text x="8" y="12" text-anchor="middle" fill="#9b6fd4" font-size="11" font-weight="700">?</text></svg>',
        "Unknown": '<svg viewBox="0 0 16 16"><text x="8" y="12" text-anchor="middle" fill="#a89ab8" font-size="11" font-weight="700">?</text></svg>',
        "Treasure": '<svg viewBox="0 0 16 16"><rect x="3" y="6" width="10" height="6" rx="1" fill="none" stroke="#d4a840" stroke-width="1.3"/><path d="M3 9h10" stroke="#d4a840" stroke-width="1"/><circle cx="8" cy="9" r="1" fill="#d4a840"/><path d="M5 6c0-2 1.3-3 3-3s3 1 3 3" stroke="#d4a840" stroke-width="1.2" fill="none"/></svg>',
        "Boss": '<svg viewBox="0 0 16 16"><path d="M3 11L4 6l2.5 2.5L8 4l1.5 4.5L12 6l1 5z" fill="#e74c3c" opacity="0.9"/><rect x="3" y="11" width="10" height="2" rx="0.5" fill="#e74c3c"/></svg>',
        "Ancient": '<svg viewBox="0 0 16 16"><text x="8" y="12" text-anchor="middle" fill="#9b6fd4" font-size="10" font-weight="700">古</text></svg>',
    }
    _NODE_CSS = {
        "Monster": "mn-enemy", "Elite": "mn-elite", "Boss": "mn-boss",
        "Shop": "mn-shop", "Rest": "mn-rest", "RestSite": "mn-rest",
        "Event": "mn-event", "Treasure": "mn-chest", "Unknown": "mn-unknown",
        "Ancient": "mn-event",
    }
    _REST_LABELS = {
        "rest": ("补血", "回复35%最大HP"),
        "smith": ("锻造", "升级一张牌"),
        "recall": ("孵化", "激活炉子遗物"),
        "toke": ("抽牌", "记忆水晶"),
        "lift": ("力量+", "举重训练"),
        "dig": ("挖掘", "铲子"),
    }

    _CHAR_CN = {
        "CHARACTER.IRONCLAD": "铁甲战士", "CHARACTER.SILENT": "静默猎手",
        "CHARACTER.DEFECT": "缺陷体", "CHARACTER.REGENT": "储君",
        "CHARACTER.NECROBINDER": "亡灵契约师",
    }

    # ── Power-checking utilities ──────────────
    @staticmethod
    def _get_power_amount(powers, power_id, *cn_names):
        """Get total amount of a specific power. E.g. _get_power_amount(powers, 'Strength', '力量')"""
        return sum(p.get("amount", 0) for p in powers
                   if p.get("id") == power_id or p.get("name") in cn_names)

    @staticmethod
    def _has_power(powers, power_id, *cn_names):
        """Check if entity has a specific power."""
        return any(p.get("id") == power_id or p.get("name") in cn_names for p in powers)

    @staticmethod
    def _pile_summary(pile):
        """Summarize a card pile as 'cardA×2 cardB' string. For draw/discard pile display."""
        if not pile: return ""
        from collections import Counter
        names = Counter(c.get("name", "?") for c in pile)
        return " ".join(f"{n}×{cnt}" if cnt > 1 else n for n, cnt in names.most_common())

    def _render_option(self, label, desc=""):
        """Render a single option-block. THE one method for all options (event/rest/shop/etc)."""
        parts = ['<div class="option-block">']
        parts.append(f'<div class="option-label">{html.escape(str(label))}</div>')
        if desc:
            parts.append(f'<div class="option-desc">{self._colorize_desc(str(desc))}</div>')
        parts.append('</div>')
        return ''.join(parts)

    # ══════════════════════════════════════════
    #  ATOMIC HELPERS (Layer 0)
    # ══════════════════════════════════════════
    def _push_scene(self, parts, tab="situation"):
        """Push assembled HTML parts to scene and optionally switch tab.
        tab=None means no tab switch."""
        content = "".join(parts) if isinstance(parts, list) else parts
        self._js(f'app.updateScene({{type:"html",html:{json.dumps(content)}}})')
        if tab:
            self._js(f'app.setTab("{tab}")')

    def _colorize_desc(self, text):
        """Scan description text and wrap game-relevant terms in colored spans."""
        escaped = html.escape(text)
        # Gold/currency: 150金币, 50 金, 100金
        escaped = _re.sub(r'(\d+)\s*(?:点)?(金币|金(?!色))', r'<span style="color:var(--gold);font-weight:600">\1 \2</span>', escaped)
        # HP/damage: 7最大HP, 12 HP, 13点伤害, 8伤害, 6伤, 总伤X
        escaped = _re.sub(r'(\d+)\s*(?:点)?(最大HP|HP|最大生命值|生命值|生命)', r'<span style="color:var(--hp);font-weight:600">\1 \2</span>', escaped)
        escaped = _re.sub(r'(\d+)\s*(?:点)?(伤害|伤(?!口))', r'<span style="color:var(--hp);font-weight:600">\1\2</span>', escaped)
        escaped = _re.sub(r'(致命|不致命)', r'<span style="color:var(--hp);font-weight:600">\1</span>', escaped)
        # Block: 8格挡, 5挡
        escaped = _re.sub(r'(\d+)\s*(?:点)?(格挡|挡(?!住))', r'<span style="color:var(--block);font-weight:600">\1\2</span>', escaped)
        # Buffs/debuffs: 2力量, 3敏捷, 虚弱, 易伤
        escaped = _re.sub(r'(\d+)\s*(力量|敏捷|集中|能量)', r'<span style="color:var(--buff);font-weight:600">\1 \2</span>', escaped)
        escaped = _re.sub(r'(\d+)\s*(虚弱|易伤)', r'<span style="color:var(--debuff);font-weight:600">\1 \2</span>', escaped)
        escaped = _re.sub(r'(减益|虚弱|易伤|脆弱)', r'<span style="color:var(--debuff)">\1</span>', escaped)
        # Healing: 回复, 生命, 治疗
        escaped = _re.sub(r'(回复|恢复|治疗)\s*(?:最大)?(?:生命值的?)?\s*(\d+%?(?:\s*[（(]\d+[)）])?)',
                          r'<span style="color:var(--buff);font-weight:600">\1 \2</span>', escaped)
        escaped = _re.sub(r'(\d+)\s*(?:点)?(生命|最大生命值)', r'<span style="color:var(--buff);font-weight:600">\1 \2</span>', escaped)
        # Upgrade/锻造
        escaped = _re.sub(r'(升级|锻造)', r'<span style="color:var(--gold);font-weight:600">\1</span>', escaped)
        # Remove/删牌
        escaped = _re.sub(r'(移除|删除|删牌)', r'<span style="color:var(--hp);font-weight:600">\1</span>', escaped)
        # Items in「」
        escaped = _re.sub(r'「([^」]+)」', r'<span style="color:var(--accent2);font-weight:600">「\1」</span>', escaped)
        # Relic/card type labels (only specific terms, avoid over-matching)
        escaped = _re.sub(r'(稀有遗物|稀有卡牌|随机遗物)', r'<span style="color:var(--accent2)">\1</span>', escaped)
        # Numbers for 张牌
        escaped = _re.sub(r'(\d+)\s*(张牌|张)', r'<span style="font-weight:600">\1</span>\2', escaped)
        # Enchantments/附魔 — accent color
        escaped = _re.sub(r'附魔[：:]\s*(\S+)', r'附魔: <span style="color:var(--accent2);font-weight:600">\1</span>', escaped)
        escaped = _re.sub(r'(涡旋|烈焰|冰霜|雷电|暗影|圣光|毒素|荆棘|吸血|穿透|连锁|分裂|回响)',
                          r'<span style="color:var(--accent2);font-weight:600">\1</span>', escaped)
        # Map node types — colored to match route display
        escaped = _re.sub(r'(精英战斗|精英怪|精英)', r'<span class="node-elite">\1</span>', escaped)
        escaped = _re.sub(r'(篝火|休息点)', r'<span class="node-rest">\1</span>', escaped)
        escaped = _re.sub(r'(商店)', r'<span class="node-shop">\1</span>', escaped)
        escaped = _re.sub(r'(未知事件|事件)', r'<span class="node-event">\1</span>', escaped)
        escaped = _re.sub(r'(普通战斗|普通怪)', r'<span class="node-enemy">\1</span>', escaped)
        return escaped

    def _render_formatted_html(self, text, header=""):
        """Parse AI output and produce colored HTML string."""
        parts = []
        self._recommended_options = []  # Track ALL recommended options for highlighting
        if header:
            parts.append(f'<span class="gold" style="font-weight:600">{html.escape(header)}</span><br><br>')

        lines = text.split("\n")
        i = 0
        while i < len(lines):
            stripped = lines[i].strip()

            if not stripped:
                # Collapse consecutive blank lines
                if not parts or parts[-1] != "<br>":
                    parts.append("<br>")
                i += 1
                continue

            escaped = html.escape(stripped)

            # Separator
            if stripped.startswith("──") or stripped.startswith("─"):
                parts.append(f'<span class="gold" style="font-weight:600">{escaped}</span><br>')

            # Play order title
            elif stripped.startswith("▶"):
                parts.append(f'<span class="gold" style="font-weight:600">{escaped}</span><br>')

            # Numbered steps: "1. [4]护卫 — ..." → "① 护卫 → ..."
            elif len(stripped) > 2 and stripped[0].isdigit() and stripped[1] in ".、":
                _circled = "①②③④⑤⑥⑦⑧⑨⑩"
                num = int(stripped[0]) if stripped[0].isdigit() else 0
                circle = _circled[num - 1] if 0 < num <= len(_circled) else f"{num}."
                rest = stripped[2:].strip()
                # Strip [index] prefix
                rest = _re.sub(r'^\[\d+\]\s*', '', rest)
                # Split card name from description at — or -
                dash = _re.search(r'\s*[—–\-]\s*', rest)
                if dash:
                    card_part = rest[:dash.start()].strip()
                    desc_part = rest[dash.end():].strip()
                    # Card name in highlight, desc with colorize
                    parts.append(f'<span class="highlight">{circle} {html.escape(card_part)}</span>'
                                 f' → {self._colorize_desc(desc_part)}<br>')
                else:
                    parts.append(f'<span class="highlight">{circle} {self._colorize_desc(rest)}</span><br>')

            # Energy remaining
            elif stripped.startswith("（能量剩余") or stripped.startswith("(能量剩余"):
                parts.append(f'<span class="dim">{escaped}</span><br>')

            # Threat block ⚠ — gold header, debuff-colored body with colorized terms
            elif stripped.startswith("⚠"):
                header = stripped.split("：", 1)
                if len(header) == 2:
                    parts.append(f'<span class="gold" style="font-weight:600">{html.escape(header[0])}:</span> '
                                 f'{self._colorize_desc(header[1])}<br>')
                else:
                    parts.append(f'<span class="gold" style="font-weight:600">{html.escape(stripped)}</span><br>')
                i += 1
                while i < len(lines):
                    next_s = lines[i].strip()
                    if not next_s or next_s[0] in "▶★○✗💡📋─" or (len(next_s) > 2 and next_s[0].isdigit() and next_s[1] in ".、"):
                        break
                    parts.append(f'  {self._colorize_desc(next_s)}<br>')
                    i += 1
                continue

            # Strategy block 💡 — dim body with colorized terms
            elif stripped.startswith("💡"):
                content = stripped.lstrip("💡 ")
                header = content.split("：", 1)
                if len(header) == 2:
                    parts.append(f'<span class="dim"><span style="font-weight:600">💡 {html.escape(header[0])}:</span> '
                                 f'{self._colorize_desc(header[1])}</span><br>')
                else:
                    parts.append(f'<span class="dim">{self._colorize_desc(content)}</span><br>')
                i += 1
                while i < len(lines):
                    next_s = lines[i].strip()
                    if not next_s or next_s[0] in "▶★○✗⚠📋─" or (len(next_s) > 2 and next_s[0].isdigit() and next_s[1] in ".、"):
                        break
                    parts.append(f'  <span class="dim">{self._colorize_desc(next_s)}</span><br>')
                    i += 1
                continue

            # Recommend ★ — split marker + name from reasoning
            elif stripped.startswith("★") or stripped.startswith("推荐购买") or stripped.startswith("推荐选项"):
                content = stripped.lstrip("★ ")
                dash_pos = content.find("—")
                if dash_pos < 0: dash_pos = content.find("——")
                if dash_pos > 0:
                    name_part = content[:dash_pos].strip()
                    reason_part = content[dash_pos+1:].strip().lstrip("—").strip()
                    parts.append(f'<span class="gold" style="font-weight:600">★ {html.escape(name_part)}</span>'
                                 f' — {self._colorize_desc(reason_part)}<br>')
                    self._recommended_options.append(name_part)
                else:
                    parts.append(f'<span class="gold" style="font-weight:600">★ {self._colorize_desc(content)}</span><br>')
                    for sep in ['，', '。', '：', ',', '.']:
                        if sep in content:
                            self._recommended_options.append(content[:content.index(sep)].strip())
                            break

            # Not recommended ✗
            elif stripped.startswith("✗") or stripped.startswith("跳过") or stripped.startswith("避雷"):
                content = stripped.lstrip("✗ ")
                dash_pos = content.find("—")
                if dash_pos > 0:
                    name_part = content[:dash_pos].strip()
                    reason_part = content[dash_pos+1:].strip().lstrip("—").strip()
                    parts.append(f'<span style="color:var(--hp);font-weight:600">✗ {html.escape(name_part)}</span>'
                                 f' — <span class="dim">{self._colorize_desc(reason_part)}</span><br>')
                else:
                    parts.append(f'<span style="color:var(--hp)">✗ {self._colorize_desc(content)}</span><br>')

            # Remove card advice
            elif stripped.startswith("删牌建议"):
                parts.append(f'<span class="debuff">{escaped}</span><br>')

            # Play style
            elif stripped.startswith("打法"):
                parts.append(f'<span class="blue">{escaped}</span><br>')

            # Archetype / summary
            elif stripped.startswith("📋") or stripped.startswith("流派"):
                parts.append(f'<span class="gold" style="font-weight:600">{escaped}</span><br>')

            # Direction
            elif stripped.startswith("方向"):
                parts.append(f'<span class="buff">{escaped}</span><br>')

            # Core / support / transition / combo cards
            elif stripped.startswith("核心牌"):
                parts.append(f'<span class="highlight">{escaped}</span><br>')
            elif stripped.startswith("辅助牌"):
                parts.append(f'<span class="buff">{escaped}</span><br>')
            elif stripped.startswith("过渡牌"):
                parts.append(f'<span class="dim">{escaped}</span><br>')
            elif stripped.startswith("组合技"):
                parts.append(f'<span style="font-weight:600">{escaped}</span><br>')

            # Threat analysis (without ⚠ prefix)
            elif stripped.startswith("威胁分析"):
                header = stripped.split("：", 1)
                if len(header) == 2:
                    parts.append(f'<span class="gold" style="font-weight:600">⚠ {html.escape(header[0])}:</span> '
                                 f'{self._colorize_desc(header[1])}<br>')
                else:
                    parts.append(f'<span class="gold" style="font-weight:600">⚠ {html.escape(stripped)}</span><br>')

            # Core strategy (without 💡 prefix)
            elif stripped.startswith("核心思路") or stripped.startswith("核心策略"):
                header = stripped.split("：", 1)
                if len(header) == 2:
                    parts.append(f'<span class="dim" style="font-weight:600">{html.escape(header[0])}:</span> '
                                 f'<span class="dim">{self._colorize_desc(header[1])}</span><br>')
                else:
                    parts.append(f'<span class="dim">{self._colorize_desc(stripped)}</span><br>')

            # Strength / consider
            elif stripped.startswith("强度") or stripped.startswith("可以考虑"):
                parts.append(f'<span class="buff">{escaped}</span><br>')

            # Find cards
            elif stripped.startswith("找牌"):
                parts.append(f'<span class="highlight">{escaped}</span><br>')

            # Optional ○ — consider option
            elif stripped.startswith("○"):
                content = stripped.lstrip("○ ")
                dash_pos = content.find("—")
                if dash_pos > 0:
                    name_part = content[:dash_pos].strip()
                    reason_part = content[dash_pos+1:].strip().lstrip("—").strip()
                    parts.append(f'<span style="color:var(--block);font-weight:600">○ {html.escape(name_part)}</span>'
                                 f' — <span class="dim">{self._colorize_desc(reason_part)}</span><br>')
                else:
                    parts.append(f'<span style="color:var(--block)">○ {self._colorize_desc(content)}</span><br>')

            # Route recommendation header: "推荐路线 X，理由如下："
            elif stripped.startswith("推荐路线"):
                parts.append(f'<span class="gold" style="font-weight:600">{self._colorize_desc(stripped)}</span><br>')

            # Bullet points: "• xxxx"
            elif stripped.startswith("•"):
                parts.append(f'• {self._colorize_desc(stripped[1:].strip())}<br>')

            # Default — apply colorize for inline coloring
            else:
                parts.append(f'{self._colorize_desc(stripped)}<br>')

            i += 1

        return "".join(parts)

    def _add_card_tooltips(self, html_str):
        """委托给 CardDB.add_tooltips()。"""
        if hasattr(self, 'cards'):
            return self.cards.add_tooltips(html_str)
        return html_str

    # ══════════════════════════════════════════
    #  CARD RENDERING (Layer 1 — uses Layer 0)
    # ══════════════════════════════════════════
    def _render_card(self, c_or_name, show_type=False, price=None):
        """THE single card renderer. Every card display calls this.
        c_or_name: dict (API card) or str (card name).
        show_type: show type inline with cost (for reward cards not grouped by type).
        price: shop price string like "150金" (shown below cost).
        Inline: [name(left)  cost(right)].  Hover: type · rarity · description."""
        if isinstance(c_or_name, str):
            c = {"name": c_or_name}
        else:
            c = c_or_name
        name = c.get("name", "?")
        upg = "+" if c.get("is_upgraded") else ""

        # ALWAYS enrich from CardDB — single source of truth for display info
        db_cost, db_desc, db_type, db_rarity = "?", "", "", ""
        if hasattr(self, 'cards'):
            detail = self.cards.detail(name)
            if detail:
                db_cost = detail.get("cost", "?")
                db_desc = detail.get("desc_cn", "")
                db_type = detail.get("type", "").lower()
                db_rarity = detail.get("rarity", "").lower()

        # Use API values as override, CardDB as fallback
        cost = c.get("cost", db_cost) if c.get("cost") not in (None, "?") else db_cost
        desc = c.get("description", "") or db_desc
        ctype = (c.get("type") or c.get("card_type") or db_type or "").lower()
        raw_rarity = (c.get("rarity") or db_rarity or "").lower()
        # Normalize rarity: Chinese → English key (基础→basic, 罕见→uncommon, etc.)
        if hasattr(self, 'cards'):
            from overlay.card_db import CardDB
            rarity = CardDB._normalize_rarity(raw_rarity)
        else:
            rarity = raw_rarity

        # Name color by rarity
        if upg:
            name_color = self._UPGRADED_COLOR
        elif rarity in self._RARITY_COLOR:
            name_color = self._RARITY_COLOR[rarity]
        else:
            name_color = "var(--text)"

        # Right side: cost (+ optional type)
        cost_str = f"{cost}费" if cost != "?" else ""
        type_cn = self._TYPE_CN.get(ctype, "")
        if show_type and type_cn:
            right_text = f"{cost_str} · {type_cn}" if cost_str else type_cn
        else:
            right_text = cost_str

        # Tooltip: type · rarity · description (each a distinct color)
        rarity_cn = self._RARITY_CN.get(rarity, "")
        rarity_color = self._RARITY_COLOR.get(rarity, "var(--dim)")
        tip_parts = []
        if type_cn:
            tip_parts.append(f'<span style="color:var(--block);">{type_cn}</span>')
        if rarity_cn:
            tip_parts.append(f'<span style="color:{rarity_color};">{rarity_cn}</span>')
        tip_header = f'{" · ".join(tip_parts)}' if tip_parts else ""
        desc_html = f'<span class="ct-desc">{html.escape(desc[:80])}</span>' if desc else ""
        tooltip = ""
        if tip_header or desc_html:
            tooltip = f'<div class="card-tooltip">{tip_header}{desc_html}</div>'

        # Price line (shop only)
        price_html = f'<div class="card-price">{html.escape(price)}</div>' if price else ""

        return (
            f'<div class="card-item">'
            f'<span class="card-name" style="color:{name_color}">{html.escape(name)}{html.escape(upg)}</span>'
            f' <span class="card-cost">{right_text}</span>'
            f'{price_html}'
            f'{tooltip}'
            f'</div>'
        )

    def _card_type_key(self, c):
        """Get card type key for grouping. Used by card_reward, shop, deck."""
        ctype = (c.get("type") or c.get("card_type") or "").lower()
        if not ctype and hasattr(self, 'cards'):
            detail = self.cards.detail(c.get("name", c.get("card_name", "")))
            if detail:
                ctype = detail.get("type", "").lower()
        return ctype

    def _render_card_grid(self, cards, show_type=False, price_fn=None):
        """Render a grid of cards. cards: list of dicts.
        price_fn: optional func(card)->price_str for shop cards."""
        parts = ['<div class="card-grid">']
        for c in cards:
            price = price_fn(c) if price_fn else None
            parts.append(self._render_card(c, show_type=show_type, price=price))
        parts.append('</div>')
        return ''.join(parts)

    def _render_grouped_cards(self, cards, show_type=False, price_fn=None):
        """Render cards grouped by type (攻击/技能/能力) with colored headers."""
        TYPE_LABEL_COLOR = {
            "attack": ("攻击", "var(--hp)"),
            "skill": ("技能", "var(--block)"),
            "power": ("能力", "var(--buff)"),
        }
        TYPE_ORDER = ["attack", "skill", "power"]
        grouped = {}
        for c in cards:
            grouped.setdefault(self._card_type_key(c), []).append(c)
        parts = []
        for ct in TYPE_ORDER:
            items = grouped.pop(ct, [])
            if not items:
                continue
            label, color = TYPE_LABEL_COLOR.get(ct, ("其他", "var(--dim)"))
            parts.append(f'<div style="font-size:11px;color:{color};font-weight:600;margin:6px 0 3px;">{label} ({len(items)})</div>')
            parts.append(self._render_card_grid(items, show_type=show_type, price_fn=price_fn))
        # Remaining types
        for ct, items in grouped.items():
            if not items:
                continue
            label = self._TYPE_CN.get(ct, ct or "其他")
            parts.append(f'<div style="font-size:11px;color:var(--dim);font-weight:600;margin:6px 0 3px;">{label} ({len(items)})</div>')
            parts.append(self._render_card_grid(items, show_type=show_type, price_fn=price_fn))
        return ''.join(parts)

    def _push_advice(self, text, header="", card_tooltips=True):
        """Render AI advice HTML and push to UI, then highlight ALL recommended options."""
        advice_html = self._render_formatted_html(text, header)
        if card_tooltips:
            advice_html = self._add_card_tooltips(advice_html)
        self._js(f'app.updateAdvice({json.dumps(advice_html)})')
        # Highlight all recommended options
        for opt_name in getattr(self, '_recommended_options', []):
            self._js(f'app.highlightOption({json.dumps(opt_name)})')

    def _delayed_display_combat(self):
        """Delay then re-fetch latest state and display."""
        import threading
        def _do():
            try:
                state = requests.get(API_URL, timeout=5).json()
                if state.get("state_type") in ("monster", "elite", "boss"):
                    self._display_combat(state)
            except Exception:
                pass
        threading.Thread(target=_do, daemon=True).start()

    @staticmethod
    def _number_enemies(enemies):
        """Give same-name enemies numbers: 绿虱#1, 绿虱#2."""
        name_count = {}
        for e in enemies:
            n = e.get("name", "?")
            name_count[n] = name_count.get(n, 0) + 1
        name_idx = {}
        for e in enemies:
            n = e.get("name", "?")
            if name_count[n] > 1:
                name_idx[n] = name_idx.get(n, 0) + 1
                e["_display_name"] = f"{n}#{name_idx[n]}"
            else:
                e["_display_name"] = n
        return enemies

    def _parse_single_intent(self, intent):
        """Parse a single intent and return (text, color) tuple.
        Shared logic for both plain-text and HTML intent formatting."""
        import re as _re
        label = (intent.get("label") or "").strip()
        itype = intent.get("type", "")
        damage, hits = self._parse_intent_damage(intent)

        # Determine color based on intent type
        if "Attack" in itype or "Heavy" in itype:
            color = "var(--hp)"
        elif "Debuff" in itype or "debuff" in itype:
            color = "var(--debuff)"
        elif "Buff" in itype:
            color = "var(--buff)"
        elif "Defend" in itype:
            color = "var(--block)"
        else:
            color = "var(--dim)"

        if damage and hits > 1:
            text = f"攻击 {damage}×{hits}"
        elif damage:
            text = f"攻击 {damage}伤"
        elif label:
            m_multi = _re.match(r"(\d+)\s*[×xX]\s*(\d+)", label)
            if m_multi:
                dmg, ht = int(m_multi.group(1)), int(m_multi.group(2))
                text = f"攻击 {dmg}×{ht}"
            elif any(c.isdigit() for c in label):
                nums = [s.strip() for s in label.replace("，", ",").split(",") if s.strip().isdigit()]
                text = f"攻击 {nums[0]}伤" if len(nums) == 1 else label
            else:
                text = label
        elif itype:
            text = INTENT_CN.get(itype, itype)
        else:
            return None, None
        return text, color

    def _fmt_intent_html(self, intents):
        """Format intents as colored HTML spans — each part gets its own color."""
        parts = []
        for i in intents:
            text, color = self._parse_single_intent(i)
            if text is None:
                continue
            parts.append(f'<span style="color:{color};font-weight:600;">{html.escape(text)}</span>')
        return " ".join(parts) or '<span class="dim">—</span>'

    # Powers where amount is just a flag (1=active), not a meaningful number
    _FLAG_POWERS = {"为你而死", "飞行", "反击", "荆棘", "无实体", "好奇心", "分裂",
                    "转移", "尖刺", "卷曲", "膨胀", "金属化"}

    def _power_spans(self, powers, block=0):
        """Build list of colored stat spans from powers + optional block."""
        parts = []
        if block:
            parts.append(f'<span style="color:var(--block);">格挡 {block}</span>')
        for p in powers:
            amt = p.get("amount", 0)
            pname = _cn_power(p)
            cls = "color:var(--debuff)" if amt < 0 else "color:var(--buff)"
            if pname in self._FLAG_POWERS:
                parts.append(f'<span style="{cls}">{html.escape(pname)}</span>')
            else:
                parts.append(f'<span style="{cls}">{html.escape(pname)} {amt}</span>')
        return parts

    @staticmethod
    def _fmt_powers_text(powers):
        """Format powers as plain text for prompts."""
        parts = []
        for p in powers:
            pname = _cn_power(p)
            if pname in DisplayMixin._FLAG_POWERS:
                parts.append(pname)
            else:
                parts.append(f"{pname}×{p['amount']}")
        return "  ".join(parts)

    def _render_entity_block(self, name, hp, max_hp, intent_html="",
                             name_color="var(--hp)", bar_color="", stat_parts=None):
        """Render a reusable entity block (enemy, player, ally).
        Name + intent/stats on one line, HP text inside bar."""
        max_hp = max(max_hp, 1)
        hp_pct = int(hp / max_hp * 100)
        bar_style = f'background:{bar_color};' if bar_color else ''
        # Right side: intent or stats
        right_parts = []
        if intent_html:
            right_parts.append(intent_html)
        if stat_parts:
            right_parts.extend(stat_parts)
        right_html = ""
        if right_parts:
            sep = f' <span style="color:var(--dim);">&middot;</span> '
            right_html = f'<span style="font-size:11px;">{sep.join(right_parts)}</span>'
        parts = ['<div class="enemy-block">']
        parts.append(f'<div style="display:flex;justify-content:space-between;align-items:baseline;gap:6px;">'
                     f'<span style="color:{name_color};font-weight:600;font-size:13px;white-space:nowrap;">{name}</span>'
                     f'{right_html}</div>')
        # HP bar with text inside
        parts.append(f'<div class="hp-bar-outer" style="position:relative;height:14px;margin-top:3px;">'
                     f'<div class="hp-bar-inner" style="width:{hp_pct}%;{bar_style}"></div>'
                     f'<span style="position:absolute;left:6px;top:0;font-size:10px;font-weight:600;'
                     f'color:#fff;line-height:14px;text-shadow:0 1px 2px rgba(0,0,0,0.8);">{hp}/{max_hp}</span>'
                     f'</div>')
        parts.append('</div>')
        return ''.join(parts)

    def _display_combat(self, state):
        """Auto-display battlefield — matches reference layout."""
        battle  = state.get("battle", {})
        enemies = battle.get("enemies", [])
        player  = battle.get("player", {})
        hand    = player.get("hand", [])
        draw    = player.get("draw_pile_count", 0)
        disc    = player.get("discard_pile_count", 0)
        exhaust = player.get("exhaust_pile_count", 0)

        self._number_enemies(enemies)
        parts = []

        # ── Enemies ──
        parts.append('<div class="section-title">敌方信息</div>')
        parts.append('<div class="enemy-row">')
        for e in enemies:
            display_name = e.get("_display_name", e.get("name", "?"))
            parts.append(self._render_entity_block(
                html.escape(display_name), e.get("hp", 0), e.get("max_hp", 1),
                intent_html=self._fmt_intent_html(e.get("intents", [])),
                stat_parts=self._power_spans(e.get("powers", []), e.get("block", 0))))
        parts.append('</div>')

        # ── Allies (player + summons) ──
        allies = [a for a in battle.get("allies", []) if a.get("name")]
        p_char = self.last_player.get("character", "我") if hasattr(self, 'last_player') else "我"
        parts.append('<hr class="divider">')
        parts.append('<div class="section-title">友方信息</div>')
        parts.append('<div class="enemy-row">')
        # Player
        parts.append(self._render_entity_block(
            html.escape(p_char), player.get("hp", 0), player.get("max_hp", 1),
            name_color="var(--accent2)",
            bar_color="linear-gradient(90deg,var(--accent),#7b50b8)",
            stat_parts=self._power_spans(player.get("powers", []), player.get("block", 0))))
        # Summons
        for a in allies:
            a_stats = self._power_spans(a.get("powers", []), a.get("block", 0))
            parts.append(self._render_entity_block(
                html.escape(a.get("name", "?")), a.get("hp", 0), a.get("max_hp", 1),
                name_color="var(--buff)",
                bar_color="linear-gradient(90deg,var(--buff),#2d9e5e)",
                stat_parts=a_stats))
        parts.append('</div>')

        # ── Hand ──
        parts.append('<hr class="divider">')
        n_hand = len(hand)
        pile_info = f'<span class="dim" style="font-size:11px;float:right;">摸:{draw} 弃:{disc}'
        if exhaust:
            pile_info += f' 消:{exhaust}'
        pile_info += '</span>'
        parts.append(f'<div class="section-title">手牌 ({n_hand}张) {pile_info}</div>')
        if hand:
            parts.append('<div class="card-grid">')
            for c in hand:
                parts.append(self._render_card(c))
            parts.append('</div>')
        else:
            parts.append('<div class="textbox"><span class="dim">（空手牌）</span></div>')

        self._push_scene(parts)

    @staticmethod
    def _node_span(ntype):
        """Render a single map node as SVG icon circle."""
        css = DisplayMixin._NODE_CSS.get(ntype, "mn-unknown")
        svg = DisplayMixin._SVG_ICONS.get(ntype, DisplayMixin._SVG_ICONS.get("Unknown", "?"))
        return f'<span class="map-node {css}">{svg}</span>'

    @staticmethod
    def _summarize_route(types):
        """Summarize route composition: 精×1 火×2 etc."""
        elite_n = sum(1 for t in types if t == "Elite")
        rest_n = sum(1 for t in types if t in ("Rest", "RestSite"))
        shop_n = sum(1 for t in types if t == "Shop")
        p = []
        if elite_n: p.append(f"精×{elite_n}")
        if rest_n: p.append(f"火×{rest_n}")
        if shop_n: p.append(f"店×{shop_n}")
        return " ".join(p) or "纯怪"

    @staticmethod
    def _trace_all_routes(by_pos, start_col, start_row, max_depth=8, max_routes=12):
        """Trace ALL distinct routes from a node, following every fork. Used by map display + AI."""
        results = []
        stack = [((start_col, start_row), [])]
        while stack and len(results) < max_routes:
            cur, path = stack.pop()
            if len(path) >= max_depth:
                results.append(path)
                continue
            node = by_pos.get(cur)
            if not node or not node.get("children"):
                results.append(path)
                continue
            for child in node["children"]:
                child_key = (child[0], child[1])
                child_node = by_pos.get(child_key)
                if child_node:
                    stack.append((child_key, path + [child_node.get("type", "?")]))
                elif path:
                    results.append(path)
        return results

    @staticmethod
    def _build_map_by_pos(mdata):
        """Build {(col,row): node} lookup from map data."""
        by_pos = {}
        for n in mdata.get("nodes", []):
            by_pos[(n.get("col"), n.get("row"))] = n
        return by_pos

    def _display_map(self, state):
        """Auto-display map routes with rich info (no LLM)."""
        mdata = state.get("map", {})
        by_pos = self._build_map_by_pos(mdata)

        # Collect all distinct routes from all starting options
        opts = mdata.get("next_options", [])
        all_routes = []  # [(first_type, follow_types), ...]
        for o in opts:
            first_type = o.get("type", "")
            if by_pos:
                branches = self._trace_all_routes(by_pos, o.get("col", 0), o.get("row", 0))
                if not branches:
                    branches = [[]]
                # Deduplicate identical type sequences
                seen = set()
                for follow in branches:
                    key = tuple(follow)
                    if key not in seen:
                        seen.add(key)
                        all_routes.append((first_type, follow))
            else:
                follow_types = [n.get("type", "") for n in o.get("leads_to", [])]
                all_routes.append((first_type, follow_types))

        n_routes = len(all_routes)
        parts = [f'<div class="section-title">可选路线 ({n_routes}条)</div>']

        for idx, (first_type, follow_types) in enumerate(all_routes):
            route_num = idx + 1
            all_types = [first_type] + follow_types
            summary = self._summarize_route(all_types)

            parts.append(f'<div class="route-block" data-route="{route_num}">')
            chain = [self._node_span(t) for t in all_types[:10]]
            sep = '<span class="sep">›</span>'
            parts.append(
                f'<span class="route-label">{route_num}</span>'
                f'<span class="route-chain">{sep.join(chain)}</span>'
                f'<span class="route-meta">{html.escape(summary)}</span>'
            )
            parts.append('</div>')

        if not all_routes:
            parts.append('<div class="textbox"><span class="dim">（无路线信息）</span></div>')

        self._push_scene(parts)

    def _display_card_reward(self, state):
        """Auto-display card reward or card removal (no LLM)."""
        stype = state.get("state_type", "")
        cr = state.get("card_reward") or state.get("card_select") or {}
        rewards = cr.get("cards", [])

        # Detect if this is card removal vs card reward
        is_removal = stype == "card_select" or cr.get("is_removal", False)
        title = "移除卡牌" if is_removal else "选牌奖励"

        parts = [f'<div class="section-title">{title}</div>']

        if rewards:
            if is_removal:
                parts.append(self._render_grouped_cards(rewards))
            else:
                parts.append(self._render_card_grid(rewards))
                parts.append('<div class="textbox"><span class="dim">也可以跳过不选牌</span></div>')
        else:
            parts.append('<div class="textbox"><span class="dim">（无可选牌，可跳过）</span></div>')

        self._push_scene(parts)

    def _display_event(self, state):
        """Auto-display event options + knowledge base advice."""
        ev  = state.get("event", {})

        parts = []
        # Event box
        parts.append('<div class="event-box">')
        parts.append(f'<div class="event-title">{html.escape(ev.get("event_name", "未知事件"))}</div>')
        body = ev.get("body", "")
        if body:
            parts.append(f'<div class="event-desc">{html.escape(body)}</div>')
        parts.append('</div>')

        # Options
        parts.append('<div class="section-title">选项</div>')
        options = ev.get("options", [])
        for o in options:
            if o.get("is_locked"):
                continue
            idx = o.get("index", 0)
            parts.append(self._render_option(
                f"选项 {idx + 1}: {o.get('title', '?')}",
                o.get("description", "")))

        # Knowledge base guide
        event_id = ev.get("event_id") or ev.get("id") or ev.get("event_name", "")
        guide = self._event_guide.get(event_id, {})
        if guide:
            parts.append('<div class="section-title">知识库建议</div>')
            for go in guide.get("options", []):
                rating = go.get("rating", "")
                name = go.get("name", "?")
                effect = go.get("effect", "")[:60]
                parts.append(self._render_option(f"{rating} {name}", effect))
            strat = guide.get("strategy", "")
            if strat:
                parts.append(self._render_option("策略", strat[:100]))

        self._push_scene(parts)

    def _display_shop(self, state):
        """Auto-display shop items (no LLM)."""
        shop   = state.get("shop", {})
        player = self._get_player(state)
        gold   = player.get("gold", "?")

        # STS2MCP items array
        items = shop.get("items", [])
        if not items:
            items = []
            for c in shop.get("cards", []):
                items.append({"category": "card", "card_name": c.get("name"), "cost": c.get("price"),
                              "is_stocked": True, "can_afford": True, "card_description": c.get("description", "")})
            for r in shop.get("relics", []):
                items.append({"category": "relic", "relic_name": r.get("name"), "cost": r.get("price"),
                              "is_stocked": True, "relic_description": r.get("description", "")})
            for p in shop.get("potions", []):
                items.append({"category": "potion", "potion_name": p.get("name"), "cost": p.get("price"),
                              "is_stocked": True, "potion_description": p.get("description", "")})

        cards = [i for i in items if i.get("category") == "card" and i.get("is_stocked")]
        relics = [i for i in items if i.get("category") == "relic" and i.get("is_stocked")]
        potions = [i for i in items if i.get("category") == "potion" and i.get("is_stocked")]

        parts = []
        parts.append(f'<span class="gold" style="font-weight:600">商店</span>')
        parts.append(f'  <span class="dim">金币: </span>')
        parts.append(f'<span style="font-weight:600">{html.escape(str(gold))}</span>')

        def _shop_price(c):
            price_str = f"{c.get('gold_price', '?')}金"
            if c.get("on_sale"):
                price_str += " 折扣"
            return price_str

        if cards:
            parts.append('<div class="section-title">商店卡牌</div>')
            normalized = []
            for c in cards:
                nc = dict(c)
                nc["name"] = c.get("card_name", c.get("name", "?"))
                nc["description"] = self._clean_desc(c.get("card_description", ""))
                nc["gold_price"] = nc.pop("cost", "?")  # separate gold price from energy cost
                normalized.append(nc)
            parts.append(self._render_card_grid(normalized, show_type=True, price_fn=_shop_price))

        if relics or potions:
            parts.append('<div class="section-title">遗物 & 药水</div>')
            parts.append('<div class="card-grid">')
            for r in relics:
                rname = _cn_relic(r.get('relic_name', '?'))
                rcost = r.get('cost', '?')
                rdesc = self._clean_desc(r.get('relic_description', ''))
                tooltip = f'<div class="card-tooltip"><span class="ct-desc">{html.escape(rdesc)}</span></div>' if rdesc else ""
                parts.append(
                    f'<div class="card-item">'
                    f'<span class="card-name" style="color:var(--accent2)">{html.escape(rname)}</span>'
                    f' <span class="card-cost" style="color:var(--accent)">遗物</span>'
                    f'<div class="card-price">{rcost}金</div>'
                    f'{tooltip}'
                    f'</div>')
            for p in potions:
                pname = _cn_potion(p.get('potion_name', '?'))
                pcost = p.get('cost', '?')
                pdesc = self._clean_desc(
                    p.get('potion_description', '') or p.get('description', ''))
                tooltip = f'<div class="card-tooltip"><span class="ct-desc">{html.escape(pdesc)}</span></div>' if pdesc else ""
                parts.append(
                    f'<div class="card-item">'
                    f'<span class="card-name" style="color:var(--buff)">{html.escape(pname)}</span>'
                    f' <span class="card-cost" style="color:var(--buff)">药水</span>'
                    f'<div class="card-price">{pcost}金</div>'
                    f'{tooltip}'
                    f'</div>')
            parts.append('</div>')

        self._push_scene(parts)

    def _display_rest(self, state):
        """Auto-display rest site options — uses option-block (same as events)."""
        rest   = state.get("rest_site", state.get("rest", {}))
        player = self._get_player(state) or self.last_player or {}
        mhp = max(player.get("max_hp", 1), 1)
        heal_amt = int(mhp * 0.35)

        parts = [f'<div class="section-title">休息点</div>']

        opts = rest.get("options", [])
        if not opts:
            # Fallback: default rest options
            opts = [{"type": "rest"}, {"type": "smith"}]

        for oi, o in enumerate(opts):
            key = o.get("type") or o.get("id") or o.get("action") or o.get("label") or "?"
            # Fuzzy match to known labels
            label_pair = self._REST_LABELS.get(key)
            if not label_pair:
                for rk, rv in self._REST_LABELS.items():
                    if rk in key.lower():
                        label_pair = rv
                        key = rk
                        break

            if label_pair:
                title, desc = label_pair
                if key == "rest":
                    desc = f"回复35%最大HP（约+{heal_amt} HP）"
            else:
                title = o.get("label") or o.get("name") or o.get("title") or key
                desc = o.get("description", "")

            parts.append(self._render_option(f"选项 {oi + 1}: {title}", desc))

        self._push_scene(parts)
