"""AIAdvisorMixin — 所有LLM调用和策略分析。

修改AI prompt和策略逻辑只需编辑此文件。
"""
import threading
import time
# subprocess — 已迁移到 LLMClient
import os
# shutil — 已迁移到 LLMClient
import json
import re
from collections import Counter

import requests

import html as _html

from overlay.constants import (
    API_URL, LLM_CLI, STRATEGY_DB, COMBAT_BASICS,
    _cn_power, _cn_relic, _cn_potion,
    PARCH, GOLD, GREEN,
)


class AIAdvisorMixin:

    # ══════════════════════════════════════════
    #  KNOWLEDGE DATABASES (loaded once, data-driven)
    # ══════════════════════════════════════════
    _power_db = None
    _relic_db = None
    _potion_db = None
    _char_mechanics_db = None

    @classmethod
    def _load_knowledge_db(cls, attr, filename):
        """Generic lazy-load for JSON knowledge bases."""
        if getattr(cls, attr) is None:
            path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "knowledge", filename)
            try:
                with open(path) as f:
                    setattr(cls, attr, json.load(f))
            except Exception:
                setattr(cls, attr, {})
        return getattr(cls, attr)

    def _explain_powers(self, powers_list):
        """Look up effect descriptions for active powers. Returns prompt-ready string."""
        db = self._load_knowledge_db('_power_db', 'power_effects.json')
        seen, lines = set(), []
        for p in powers_list:
            pid = p.get("id", "")
            pname = _cn_power(p)
            amt = p.get("amount", 0)
            if pname in seen: continue
            seen.add(pname)
            info = db.get(pid)
            if not info:
                info = next((v for v in db.values() if v.get("name_cn") == pname), None)
            if info and info.get("effect"):
                lines.append(f"{pname}({amt}): {info['effect']}")
        return "\n".join(lines)

    def _explain_relics(self, relic_list, context="combat"):
        """Look up relic effects relevant to a given context.
        context: "combat" / "map" (matches map_*) / "rest" / "shop" / "card_reward" / "potion".
        Only includes relics the player actually has AND that matter for the context."""
        db = self._load_knowledge_db('_relic_db', 'relic_effects.json')
        lines = []
        relic_ids = {r.get("id", r.get("name", "")) for r in relic_list}
        relic_names = {r.get("name", "") for r in relic_list}
        for rid, rdata in db.items():
            cn = rdata.get("name_cn", "")
            if rid not in relic_ids and cn not in relic_names:
                continue
            relic_contexts = rdata.get("context", [])
            # "map" matches any map_* sub-context
            if context == "map":
                if not any(c.startswith("map_") for c in relic_contexts):
                    continue
            elif context not in relic_contexts:
                continue
            lines.append(f"{cn}: {rdata['desc']}")
        return "\n".join(lines)

    def _get_char_mechanic(self, char_name):
        """Get character-specific mechanic description from knowledge base."""
        db = self._load_knowledge_db('_char_mechanics_db', 'character_mechanics.json')
        info = db.get(char_name, {})
        if not info:
            return ""
        parts = []
        if info.get("innate"):
            parts.append(info["innate"])
        if info.get("note"):
            parts.append(info["note"])
        return " ".join(parts)

    def _card_prompt_line(self, c):
        """Build a compact card description for AI prompts. Used by card_reward, combat hand, shop.
        Format: name cost费 [type] [mechanics] desc"""
        name = c.get('name', '?')
        upg = '+' if c.get('is_upgraded') else ''
        cost = c.get('cost', '?')
        parts = [f"{name}{upg}"]

        if hasattr(self, 'cards'):
            detail = self.cards.detail(name)
            if detail:
                if cost == '?': cost = detail.get('cost', '?')
                ctype = detail.get('type', '')
                mechanics = detail.get('mechanics', [])
                desc_cn = detail.get('desc_cn', '')

                parts.append(f"{cost}费")
                if ctype:
                    parts.append(f"[{ctype}]")
                # Mechanics tags from source code (reliable)
                _MECH_CN = {'exhaust':'消耗','ethereal':'虚无','retain':'保留','innate':'固有',
                            'osty_attack':'Osty攻击','calamity':'灾厄','soul':'灵魂','aoe':'AOE',
                            'summon_osty':'召唤Osty','scry':'预见','channel_orb':'充能球',
                            'repeatable':'可重复','draw':'抽牌'}
                mech_tags = [_MECH_CN.get(m, m) for m in mechanics if m not in ('block','draw')]
                if mech_tags:
                    parts.append(f"[{'/'.join(mech_tags)}]")
                if desc_cn:
                    parts.append(desc_cn[:60])
        else:
            parts.append(f"{cost}费")
            desc = c.get('description', '')
            if desc: parts.append(desc[:40])

        return ' '.join(parts)

    def _explain_potions(self, potion_list):
        """Look up potion effects for AI decision making."""
        db = self._load_knowledge_db('_potion_db', 'potion_effects.json')
        lines = []
        for p in potion_list:
            pname = p.get("name", "")
            pid = p.get("id", "")
            if not pname or pname == "None": continue
            info = db.get(pid)
            if not info:
                info = next((v for v in db.values() if v.get("name_cn") == pname), None)
            cn = _cn_potion(pname) if pname else ""
            desc = info.get("desc", "") if info else ""
            lines.append(f"{cn}: {desc}" if desc else cn)
        return "\n".join(lines)

    # ───── 智能上下文构建器（0 token 查表）─────

    def _build_context(self, context_type="combat"):
        """根据当前状态查本地数据库，返回精准上下文字符串（0 token开销）。

        context_type: combat / deck / card_reward / map / event / shop / boss
        返回: 字符串，直接注入prompt
        """
        state = self.last_state or {}
        player = self._get_player(state) or self.last_player or {}
        run = state.get("run") or self.last_run or {}
        char = player.get("character", "?")
        ascension = run.get("ascension", 0)
        relics = [r.get("name", "") for r in player.get("relics", [])]
        relic_ids = [r.get("id", r.get("name", "")) for r in player.get("relics", [])]

        parts = []

        # 1. 从 archetype_matrix 查当前角色的流派推荐
        if hasattr(self, '_matrix') and self._matrix and char in self._matrix.get("characters", {}):
            char_data = self._matrix["characters"][char]
            archetypes = char_data.get("archetypes", {})

            # 进阶区间
            if ascension <= 2: asc_key = "0-2"
            elif ascension <= 5: asc_key = "3-5"
            elif ascension <= 7: asc_key = "6-7"
            else: asc_key = "8-10"

            # 筛选：只输出当前进阶下A级以上的流派 + 有匹配遗物的流派
            relevant = []
            for aname, adata in archetypes.items():
                asc_info = adata.get("ascension_impact", {}).get(asc_key, {})
                tier = asc_info.get("tier", "B")
                # 检查遗物匹配
                relic_match = []
                for t in ["S_tier", "A_tier"]:
                    for r in adata.get("relic_synergies", {}).get(t, []):
                        rname = r.get("name", "")
                        if any(rname in pr for pr in relics):
                            relic_match.append(f"{rname}({r.get('reason', '')[:20]})")

                # 检查遗物触发转向
                pivots = []
                for p in adata.get("relic_synergies", {}).get("pivot_relics", []):
                    pname = p.get("name", "")
                    if any(pname in pr for pr in relics):
                        pivots.append(f"🔥{pname}→{p.get('pivot_to','')}: {p.get('reason','')[:30]}")

                score = 0
                if "S" in tier: score = 3
                elif "A" in tier: score = 2
                elif "B" in tier: score = 1
                if relic_match: score += 2
                if pivots: score += 3

                if score >= 2:  # 只保留有意义的
                    # Extract core card Chinese names
                    core_cards_cn = []
                    for cc in adata.get("core_cards", adata.get("key_cards", [])):
                        if isinstance(cc, dict):
                            cn = cc.get("name_cn", cc.get("name", ""))
                            if cn:
                                core_cards_cn.append(cn)
                    relevant.append({
                        "name": aname,
                        "tier": tier,
                        "note": asc_info.get("note", ""),
                        "relic_match": relic_match,
                        "pivots": pivots,
                        "win": adata.get("win_condition", "")[:50],
                        "weakness": adata.get("weakness", "")[:50],
                        "combos": adata.get("key_combos", [])[:2],
                        "core_cards": core_cards_cn,
                        "score": score
                    })

            relevant.sort(key=lambda x: -x["score"])

            if relevant:
                lines = [f"[{char} A{ascension} 流派参考]"]
                for r in relevant[:3]:  # 最多3个
                    core_str = "、".join(r.get('core_cards', [])[:5])
                    line = f"  {r['name']}({r['tier']})"
                    if core_str:
                        line += f" 核心牌:{core_str}"
                    if r['relic_match']:
                        line += f" | 遗物协同: {', '.join(r['relic_match'][:2])}"
                    if r['pivots']:
                        line += f" | {'  '.join(r['pivots'])}"
                    lines.append(line)
                    if r.get('combos') and context_type in ("combat", "deck"):
                        for combo in r['combos'][:1]:
                            if isinstance(combo, dict):
                                cmech = combo.get('mechanic', '') or combo.get('cards', '')
                                lines.append(f"    combo: {str(cmech)[:60]}")
                            else:
                                lines.append(f"    combo: {str(combo)[:60]}")
                parts.append("\n".join(lines))

        # 2. 战斗时：查Boss/精英应对
        if context_type == "combat" and hasattr(self, '_boss_guide') and self._boss_guide:
            enemies = []
            battle = state.get("battle", {})
            for e in battle.get("enemies", []):
                ename = e.get("name", "")
                # 查Boss指南
                for bid, bdata in self._boss_guide.get("bosses", {}).items():
                    if bdata.get("name_cn") == ename:
                        tips = bdata.get("general_tips", [])[:2]
                        danger = [d.get("name", "") + ": " + d.get("counter", "") for d in bdata.get("danger_moves", [])[:2]]
                        # 查当前流派 matchup
                        arch_match = ""
                        if self._deck_archetype:
                            mu = bdata.get("archetype_matchups", {}).get(self._deck_archetype, {})
                            if mu:
                                arch_match = f"{self._deck_archetype} vs {ename}: {mu.get('rating','')} — {mu.get('counter','')[:30]}"

                        info = f"[Boss指南: {ename}]"
                        if arch_match: info += f"\n  {arch_match}"
                        if tips: info += f"\n  要点: {'; '.join(tips)}"
                        if danger: info += f"\n  危险招: {'; '.join(danger)}"
                        enemies.append(info)
                        break
                # 也查精英
                for eid_key, edata in self._boss_guide.get("elites", {}).items():
                    if edata.get("name_cn") == ename:
                        tips = edata.get("general_tips", [])[:2]
                        info = f"[精英指南: {ename}]"
                        if tips: info += f"\n  要点: {'; '.join(tips)}"
                        enemies.append(info)
                        break
            if enemies:
                parts.append("\n".join(enemies))

        # 3. 选牌/卡组分析时：查卡牌协同
        if context_type in ("card_reward", "deck") and hasattr(self, '_synergy_index') and self._synergy_index:
            deck_cards = [c.get("id", c.get("name", "")) for c in player.get("deck", [])]
            # 如果是选牌，查每个选项与当前牌组的协同
            if context_type == "card_reward":
                options = state.get("card_reward", {}).get("cards", [])
                synergy_hints = []
                for opt in options:
                    oid = opt.get("id", opt.get("name", ""))
                    oname = opt.get("name", oid)
                    card_syn = self._synergy_index.get(oid, {})
                    if card_syn:
                        fits = card_syn.get("archetype_fit", [])
                        tags = card_syn.get("tags", [])
                        # 检查与牌组中牌的协同
                        synergies_found = []
                        for s in card_syn.get("synergies", [])[:5]:
                            if s.get("card") in deck_cards:
                                synergies_found.append(f"{s['name']}: {s['reason'][:25]}")
                        if synergies_found or fits:
                            hint = f"  {oname}: "
                            if fits: hint += f"流派[{','.join(fits[:2])}] "
                            if synergies_found: hint += f"与牌组协同[{'; '.join(synergies_found[:2])}]"
                            synergy_hints.append(hint)
                if synergy_hints:
                    parts.append("[选牌协同分析]\n" + "\n".join(synergy_hints))

        # 4. 遗物转向规则（单遗物）
        if hasattr(self, '_pivot_rules') and self._pivot_rules:
            for rule in self._pivot_rules.get("rules", []):
                cond = rule.get("condition", {})
                req_relic = cond.get("has_relic", "")
                req_char = cond.get("character", "")
                if req_char and req_char != char:
                    continue
                if req_relic and any(req_relic in r for r in relics):
                    req_cards = cond.get("has_card_any", [])
                    if req_cards:
                        deck_ids = set(c.get("id", "") for c in player.get("deck", []))
                        if not any(c in deck_ids for c in req_cards):
                            continue
                    parts.append(f"[遗物转向] {rule['action']}: {rule['reason'][:50]}")
                    break

            # 5. 多遗物联合效应
            combo_hits = []
            for rule in self._pivot_rules.get("combo_rules", []):
                cond = rule.get("condition", {})
                req_cns = cond.get("has_relics_cn", [])
                req_char = cond.get("character", "")
                req_chars = cond.get("character_any", [])
                if req_char and req_char != char:
                    continue
                if req_chars and char not in req_chars:
                    continue
                # 用中文名匹配
                if req_cns and all(any(rcn == r for r in relics) for rcn in req_cns):
                    combo_hits.append(f"🔥 {rule['action']}: {rule['reason'][:60]}")
            if combo_hits:
                parts.append("[遗物联合效应]\n" + "\n".join(combo_hits[:3]))

        # 6. 事件时：查事件指南
        if context_type == "event" and self._event_guide:
            event_data = state.get("event", {})
            event_id = event_data.get("event_id") or event_data.get("id") or event_data.get("name", "")
            guide = self._event_guide.get(event_id, {})
            if guide:
                lines = [f"[事件指南: {guide.get('name_cn', event_id)}]"]
                for opt in guide.get("options", []):
                    rating = opt.get("rating", "")
                    lines.append(f"  {rating} {opt.get('name','?')}: {opt.get('effect','?')[:60]}")
                strat = guide.get("strategy", "")
                if strat:
                    lines.append(f"  策略: {strat[:80]}")
                parts.append("\n".join(lines))

        # 7. 选牌时：查Tier评级
        if context_type == "card_reward" and self._card_tiers:
            char_tiers = self._card_tiers.get(char, {})
            if char_tiers:
                options = state.get("card_reward", {}).get("cards", [])
                tier_hints = []
                # 判断阶段
                floor = run.get("floor", 0)
                if floor <= 8: phase = "early"
                elif floor <= 20: phase = "mid"
                else: phase = "late"
                for opt in options:
                    oid = opt.get("id", opt.get("name", ""))
                    ct = char_tiers.get(oid, {})
                    if ct:
                        tier = ct.get("tier", {}).get(phase, "?")
                        note = ct.get("note", "")[:40]
                        tier_hints.append(f"  {ct.get('name_cn', oid)}[{phase}:{tier}] {note}")
                if tier_hints:
                    parts.append("[牌评级]\n" + "\n".join(tier_hints))

        # 8. 战斗中：查怪物AI行为模式
        if context_type == "combat" and self._monster_ai:
            battle = state.get("battle", state.get("monster", {}))
            for e in battle.get("enemies", []):
                eid = e.get("id", e.get("name", ""))
                # 尝试多种key匹配
                ai = self._monster_ai.get(eid, {})
                if not ai:
                    # 尝试用中文名匹配
                    ename = e.get("name", "")
                    for mk, mv in self._monster_ai.items():
                        if isinstance(mv, dict) and mv.get("name_cn") == ename:
                            ai = mv
                            break
                if ai and isinstance(ai, dict):
                    pattern = ai.get("ai_pattern", "")
                    if pattern:
                        parts.append(f"[{ai.get('name_cn', eid)}行为] {pattern[:80]}")

        return "\n\n".join(parts) if parts else ""

    # _ask_llm 已迁移到 self.llm.ask()（LLMClient）

    def _translate_card_names(self, text):
        """委托给 CardDB.translate()。"""
        if hasattr(self, 'cards'):
            return self.cards.translate(text)
        return text

    @staticmethod
    def _parse_intent_damage(intent):
        """从intent提取(damage, hits)。优先用数值字段，fallback到label解析。"""
        import re as _re
        damage = intent.get("damage") or intent.get("base_damage")
        hits = intent.get("hits") or intent.get("times") or intent.get("count")
        if damage:
            return int(damage), int(hits or 1)
        label = (intent.get("label") or "").strip()
        if not label:
            return 0, 0
        m = _re.match(r"(\d+)\s*[×xX]\s*(\d+)", label)
        if m:
            return int(m.group(1)), int(m.group(2))
        m2 = _re.match(r"(\d+)", label)
        if m2:
            return int(m2.group(1)), 1
        return 0, 0

    @staticmethod
    def _clean_desc(text):
        """清理描述文本中的图片标记等。"""
        import re as _re
        return _re.sub(r"\[[\w.]+\.png\]", "⚡", text)

    @staticmethod
    def _parse_card_values(card):
        """从卡牌description解析伤害和格挡数值。
        返回 (damage, block)。"""
        import re as _re
        desc = card.get("description", "")
        # 已有数值字段则直接用
        dmg = card.get("damage") or card.get("base_damage") or 0
        blk = card.get("block") or card.get("base_block") or 0
        if dmg or blk:
            return int(dmg), int(blk)
        # 从描述解析: "造成X点伤害" / "获得X点格挡"
        m_dmg = _re.search(r"造成(\d+)点伤害", desc)
        m_blk = _re.search(r"获得(\d+)点格挡", desc)
        return int(m_dmg.group(1)) if m_dmg else 0, int(m_blk.group(1)) if m_blk else 0

    def _fmt_intent(self, intents):
        """格式化敌人意图为纯文本（给AI prompt用）。
        复用 _parse_single_intent 的解析逻辑，并追加总伤计算。"""
        parts = []
        for i in intents:
            text, _ = self._parse_single_intent(i)
            if text is None:
                continue
            # AI prompt 版本额外显示总伤
            damage, hits = self._parse_intent_damage(i)
            if damage and hits > 1:
                text = f"攻击 {damage}×{hits} = {damage*hits}总伤"
            elif not damage:
                # 从 label 解析多段伤害以显示总伤
                label = (i.get("label") or "").strip()
                if label:
                    import re as _re
                    m_multi = _re.match(r"(\d+)\s*[×xX]\s*(\d+)", label)
                    if m_multi:
                        dmg, ht = int(m_multi.group(1)), int(m_multi.group(2))
                        text = f"攻击 {dmg}×{ht} = {dmg*ht}总伤"
                    elif any(c.isdigit() for c in label):
                        nums = [s.strip() for s in label.replace("，", ",").split(",") if s.strip().isdigit()]
                        if len(nums) > 1:
                            total = sum(int(n) for n in nums)
                            text = f"攻击 {'×'.join(nums)} = {total}总伤"
            parts.append(text)
        return "  ".join(parts) or "—"

    def _ai_combat(self, state):
        self._busy_combat = True
        self._js('app.setButtonState("btn-situation", "⏳ 分析中…", true)')
        self._js(f'app.updateAdvice({json.dumps("◌  正在分析战斗…")})')
        try:
            try:
                fresh = requests.get(API_URL, timeout=5).json()
                if fresh.get("state_type") in ("monster", "elite", "boss"):
                    state = fresh
            except Exception:
                pass

            battle = state.get("battle", {})
            player = battle.get("player", {})
            run    = state.get("run", {})
            enemies= battle.get("enemies", [])
            hand   = player.get("hand", [])
            rnd    = battle.get("round", "?")

            # Player buff/debuff — needed for hand card damage calc
            p_str = player.get("powers", [])
            p_strength = self._get_power_amount(p_str, "Strength", "力量")
            p_dexterity = self._get_power_amount(p_str, "Dexterity", "敏捷")
            p_weak = self._has_power(p_str, "Weak", "虚弱")
            p_vulnerable = self._has_power(p_str, "Vulnerable", "易伤")

            hand_lines = []
            for c in hand:
                ok = "✓" if c.get("can_play") else "✗"
                base_line = self._card_prompt_line(c)
                # Pre-calculate actual damage/block with all buffs applied
                actual_hint = ""
                base_dmg, base_blk = self._parse_card_values(c)
                ctype = (c.get("type") or "").lower()
                if ctype in ("attack", "攻击") and base_dmg:
                    actual = base_dmg + p_strength
                    if p_weak: actual = int(actual * 0.75)
                    hits = c.get("hits", 1)
                    total = actual * hits
                    actual_hint = f" →实际{total}伤" if hits == 1 else f" →实际{actual}×{hits}={total}伤"
                if base_blk:
                    actual_block = base_blk + p_dexterity
                    actual_hint += f" →实际{actual_block}挡"
                hand_lines.append(f"  [{c.get('index',0)}]{ok} {base_line}{actual_hint}")
            hand_str = "\n".join(hand_lines) or "  （手牌为空）"

            # 敌人区分：同名敌人加编号
            self._number_enemies(enemies)
            enemy_lines = []
            for e in enemies:
                display_name = e.get("_display_name", e.get("name", "?"))

                hp  = e.get("hp", 0); mhp = e.get("max_hp", 1)
                pct = int(hp/mhp*100)
                intent = self._fmt_intent(e.get("intents", []))
                powers = self._fmt_powers_text(e.get("powers", []))
                blk = e.get("block", 0)
                # Calculate enemy's actual attack with their strength
                e_str = self._get_power_amount(e.get("powers", []), "Strength", "力量")
                e_weak = self._has_power(e.get("powers", []), "Weak", "虚弱")
                actual_atk = ""
                for i_intent in e.get("intents", []):
                    base_dmg, hits = self._parse_intent_damage(i_intent)
                    if base_dmg:
                        real = base_dmg + e_str
                        if e_weak: real = int(real * 0.75)
                        if p_vulnerable: real = int(real * 1.5)
                        total = real * hits
                        actual_atk = f" →实际{real}×{hits}={total}伤" if hits > 1 else f" →实际{total}伤"
                line = f"  {display_name}  HP:{hp}/{mhp}({pct}%)" + (f"  格挡:{blk}" if blk else "")
                line += f"\n  意图：{intent}{actual_atk}"
                if powers:
                    line += f"\n  状态：{powers}"
                enemy_lines.append(line)
            enemy_str = "\n".join(enemy_lines)

            # 友方召唤物
            allies = [a for a in battle.get("allies", []) if a.get("name")]
            ally_lines = []
            for a in allies:
                ahp = a.get("hp", 0); amhp = a.get("max_hp", 1)
                aname = a.get("name", "?")
                ablk = a.get("block", 0)
                apowers = self._fmt_powers_text(a.get("powers", []))
                aline = f"  {aname}  HP:{ahp}/{amhp}" + (f"  格挡:{ablk}" if ablk else "")
                if apowers:
                    aline += f"  [{apowers}]"
                ally_lines.append(aline)
            ally_str = "\n".join(ally_lines) if ally_lines else ""

            # 检查敌人是否有易伤/虚弱
            for e in enemies:
                e_powers = e.get("powers", [])
                e["_vulnerable"] = self._has_power(e_powers, "Vulnerable", "易伤")
                e["_weak"] = self._has_power(e_powers, "Weak", "虚弱")

            # 构建伤害计算提示
            dmg_notes = []
            if p_strength: dmg_notes.append(f"力量{p_strength:+d}(每张攻击牌{p_strength:+d}伤害)")
            if p_dexterity: dmg_notes.append(f"敏捷{p_dexterity:+d}(每张技能牌{p_dexterity:+d}格挡)")
            if p_weak: dmg_notes.append("我方虚弱(攻击-25%)")
            if p_vulnerable: dmg_notes.append("我方易伤(受伤+50%)")
            vuln_enemies = [e["_display_name"] for e in enemies if e.get("_vulnerable")]
            weak_enemies = [e["_display_name"] for e in enemies if e.get("_weak")]
            if vuln_enemies: dmg_notes.append(f"{','.join(vuln_enemies)}易伤(受伤+50%)")
            if weak_enemies: dmg_notes.append(f"{','.join(weak_enemies)}虚弱(攻击-25%)")
            dmg_hint = "  ".join(dmg_notes) if dmg_notes else ""

            p_powers = self._fmt_powers_text(player.get("powers", []))
            relic_list = player.get("relics", [])
            relics = ", ".join(_cn_relic(r["name"]) for r in relic_list) or "无"
            potions = ", ".join(_cn_potion(p["name"]) for p in player.get("potions", [])) or "无"

            # ── 遗物/药水效果（数据驱动，查表） ──
            relic_combat_info = self._explain_relics(relic_list, context="combat")
            potion_info = self._explain_potions(player.get("potions", []))
            is_elite = state.get("state_type") in ("elite", "boss")
            current_round = int(rnd) if str(rnd).isdigit() else 1

            # ── 牌组追踪（统一：API有具体牌就用，否则推算）──
            draw_count = player.get("draw_pile_count", 0)
            disc_count = player.get("discard_pile_count", 0)
            draw_pile = player.get("draw_pile", [])
            disc_pile = player.get("discard_pile", [])

            draw_summary = self._pile_summary(draw_pile)
            disc_summary = self._pile_summary(disc_pile)

            # Fallback: if API doesn't give pile contents, estimate from deck
            if not draw_summary and self.deck_acquired and draw_count > 0:
                hand_names = [c["name"] for c in hand]
                remaining = list(self.deck_acquired)
                for h in hand_names:
                    if h in remaining: remaining.remove(h)
                if remaining:
                    remain_cnt = Counter(remaining)
                    key = [f"{n}({min(cnt/max(draw_count,1)*100,100):.0f}%)"
                           for n, cnt in remain_cnt.most_common(6)
                           if cnt/max(draw_count,1)*100 >= 15]
                    if key: draw_summary = " ".join(key)

            # ── 战术计算 ──
            my_hp = player.get("hp", 0)
            my_max_hp = player.get("max_hp", 1)
            hp_pct = int(my_hp / max(my_max_hp, 1) * 100)
            my_block = player.get("block", 0)
            my_energy = player.get("energy", 0)

            # 致命线：敌人本回合总输出 vs 我方HP+格挡
            total_incoming = 0
            for e in enemies:
                for intent in e.get("intents", []):
                    if intent.get("type") in ("attack", "Attack"):
                        base_dmg, hits = self._parse_intent_damage(intent)
                        # 敌人虚弱则 ×0.75
                        if e.get("_weak"):
                            base_dmg = int(base_dmg * 0.75)
                        # 我方易伤则 ×1.5
                        if p_vulnerable:
                            base_dmg = int(base_dmg * 1.5)
                        total_incoming += base_dmg * hits
            effective_hp = my_hp + my_block
            lethal_info = ""
            if total_incoming > 0:
                survival_need = max(total_incoming - my_block, 0)
                if total_incoming >= effective_hp:
                    lethal_info = f"⚠ 致命！敌人总伤{total_incoming}，你HP+格挡={effective_hp}，必须格挡≥{survival_need}才能活"
                elif total_incoming >= effective_hp * 0.5:
                    lethal_info = f"危险：敌人总伤{total_incoming}，需格挡{survival_need}点（否则掉到{my_hp - survival_need}HP）"

            # 击杀预估：手牌总输出 vs 敌人总HP
            total_hand_dmg = 0
            for c in hand:
                if c.get("can_play") and c.get("type") in ("Attack", "attack", "攻击"):
                    base, _ = self._parse_card_values(c)
                    actual = base + p_strength
                    if p_weak: actual = int(actual * 0.75)
                    hits = c.get("hits", 1)
                    total_hand_dmg += actual * hits
            total_enemy_hp = sum(e.get("hp", 0) for e in enemies)
            kill_info = ""
            if total_hand_dmg > 0 and total_enemy_hp > 0:
                if total_hand_dmg >= total_enemy_hp:
                    kill_info = f"★ 可击杀！手牌总输出≈{total_hand_dmg}，敌人总HP={total_enemy_hp}"
                else:
                    turns_est = max(1, round(total_enemy_hp / max(total_hand_dmg, 1)))
                    kill_info = f"预估{turns_est}回合击杀（本回合输出≈{total_hand_dmg}，敌人剩{total_enemy_hp}HP）"

            # 洗牌预判
            shuffle_info = ""
            if draw_count <= 3 and draw_count >= 0:
                shuffle_info = f"摸牌堆仅{draw_count}张，下回合将洗牌（弃牌堆{disc_count}张回来）"

            # ── 药水（数据驱动） ──
            facing_lethal = lethal_info.startswith("⚠ 致命")
            can_kill = kill_info.startswith("★ 可击杀")

            tactical_info = "\n".join(x for x in [lethal_info, kill_info, shuffle_info] if x)

            char = player.get('character', '?')
            char_mechanic = self._get_char_mechanic(char)

            # 智能上下文构建（0 token查表）
            smart_ctx = self._build_context("combat")

            # 获取怪物AI信息（保留，补充smart_ctx未覆盖的怪物）
            monster_hints = []
            for e in enemies:
                ename = e.get("name", "")
                for mid, mdata in self._monster_ai.items():
                    if mdata.get("name_cn") == ename or mid == ename:
                        pattern = mdata.get("ai_pattern", "")
                        if pattern:
                            monster_hints.append(f"{ename}: {pattern}")
                        break
            monster_info = "\n".join(monster_hints) if monster_hints else ""

            # Collect all battlefield powers and explain them
            all_battlefield_powers = list(player.get("powers", []))
            for e in enemies:
                all_battlefield_powers.extend(e.get("powers", []))
            for a in allies:
                all_battlefield_powers.extend(a.get("powers", []))
            power_explanations = self._explain_powers(all_battlefield_powers)

            prompt = f"""你是杀戮尖塔2战斗教练。纯文字，不用markdown符号。所有牌名遗物名用中文。

{smart_ctx}
{"怪物行为规律：" + chr(10) + monster_info if monster_info else ""}

角色：{player.get('character')}  HP：{player.get('hp')}/{player.get('max_hp')}  格挡：{player.get('block')}
{"角色机制：" + char_mechanic if char_mechanic else ""}
能量：{player.get('energy')}/{player.get('max_energy')}  幕{run.get('act')}层{run.get('floor')}  第{rnd}回合
{"增减益：" + dmg_hint if dmg_hint else ""}
遗物：{relics}
药水：{potions}

手牌：
{hand_str}

敌人：
{enemy_str}
{"友方召唤物：" + chr(10) + ally_str if ally_str else ""}
{"摸牌堆(" + str(draw_count) + "张)：" + draw_summary if draw_summary else "摸牌堆：" + str(draw_count) + "张"}
{"弃牌堆(" + str(disc_count) + "张)：" + disc_summary if disc_summary else "弃牌堆：" + str(disc_count) + "张"}
{"战术：" + tactical_info if tactical_info else ""}
{"遗物战斗效果：" + chr(10) + relic_combat_info if relic_combat_info else ""}
{"药水效果：" + chr(10) + potion_info if potion_info else ""}
{"当前战场效果说明：" + chr(10) + power_explanations if power_explanations else ""}

规则：
- 手牌"→实际X伤/X挡"已算好全部加成，直接用。敌人"→实际X伤"也已算好力量加成，直接用。
- 仔细阅读上方"战场效果说明"理解每个buff/debuff的实际效果，做出正确决策。
- 考虑击杀顺序：击杀一个敌人可能触发其他敌人的效果（如饥饿、狂食等）。
- 摸牌堆空→洗牌。考虑整场节奏。

请严格按以下简洁格式输出，每行一条，不要多余解释：

▶ 出牌（按顺序）
1. [序号]牌名 ⚔目标 — 实际效果数值（攻击牌用⚔，技能牌用🛡，能力牌用✦）
2. ...
（能量剩余：X）

⚠ 威胁分析（一句话：总伤害X，格挡Y后净受伤Z，是否致命）

💡 核心思路（一句话：为什么这样出牌）"""

            advice = self.llm.ask(prompt, timeout=90)

            # ── 极简排版 ──
            lines = [f"◆ 第{rnd}回合"]
            # 敌人（每个一行：名字 HP 意图 buff）
            for e in enemies:
                hp  = e.get("hp", 0); mhp = e.get("max_hp", 1)
                intent = self._fmt_intent(e.get("intents", []))
                blk = e.get("block", 0)
                dn = e.get("_display_name", e.get("name", "?"))
                pw_list = [f"{p['name']}{p['amount']}" for p in e.get("powers", [])]
                line = f"{dn} {hp}/{mhp}"
                if blk: line += f" 🛡{blk}"
                line += f" →{intent}"
                if pw_list: line += f" [{' '.join(pw_list)}]"
                lines.append(line)
            # 友方（同样一行）
            for a in allies:
                aname = a.get("name", "?")
                ahp = a.get("hp", 0); amhp = a.get("max_hp", 1)
                ablk = a.get("block", 0)
                apw = [f"{p['name']}{p['amount']}" for p in a.get("powers", [])]
                aline = f"🤝{aname} {ahp}/{amhp}"
                if ablk: aline += f" 🛡{ablk}"
                if apw: aline += f" [{' '.join(apw)}]"
                lines.append(aline)

            # 我方状态（一行）
            status_parts = []
            if p_strength: status_parts.append(f"力量{p_strength:+d}")
            if p_dexterity: status_parts.append(f"敏捷{p_dexterity:+d}")
            _STAT_POWERS = {"力量", "Strength", "敏捷", "Dexterity"}
            other_buffs = [f"{p['name']}{p['amount']}" for p in player.get("powers", [])
                          if p.get("name") not in _STAT_POWERS and p.get("id") not in _STAT_POWERS]
            status_parts.extend(other_buffs[:4])
            if status_parts:
                lines.append(f"我方: {' '.join(status_parts)}")

            # 手牌（一行紧凑）
            hand_compact = []
            for c in hand:
                name = c["name"]
                upg = "+" if c.get("is_upgraded") else ""
                cost = c.get("cost", "?")
                hand_compact.append(f"{name}{upg}({cost})")
            lines.append(f"⚡{player.get('energy')}/{player.get('max_energy')} 手牌：{' · '.join(hand_compact)}")
            lines.append(f"摸:{player.get('draw_pile_count')} 弃:{player.get('discard_pile_count')}")

            # 致命警告（仅危险时）
            if facing_lethal:
                lines.append(f"⚠ 致命！总伤{total_incoming} 格挡{my_block} 缺口{total_incoming - my_block}")
            elif total_incoming > 0 and my_block < total_incoming:
                gap = total_incoming - my_block
                hp_after = player.get("hp", 0) - gap
                if hp_after > 0:
                    lines.append(f"受伤：-{gap}HP→{hp_after}HP")

            formatted = advice.strip()

            if not self._analysis_stale():
                # Re-display card-based combat (don't replace with plain text)
                self._display_combat(state)
                # Parse play order from AI advice: "1. [idx]cardname" or "N. cardname"
                import re as _re_combat
                play_order = []  # list of card names in play order
                for m in _re_combat.finditer(r'(\d+)[.、]\s*(?:\[\d+\])?\s*[✓✗]?\s*(.+?)(?:\s*[—–\-→]|$)', formatted):
                    card_raw = m.group(2).strip()
                    # Strip [idx] prefix, target indicators, parenthetical notes
                    card_raw = _re_combat.sub(r'^\[\d+\]\s*', '', card_raw)
                    # Split at target markers: ⚔ ✦ 🛡 × ✦ → or spaces followed by known targets
                    card_name = _re_combat.split(r'\s*[⚔✦🛡×→]\s*|\s+(?:自身|敌方|全体)', card_raw)[0].strip()
                    card_name = card_name.split("（")[0].split("(")[0].rstrip("+ ")
                    if card_name and len(card_name) >= 2 and card_name not in ('出牌',):
                        play_order.append(card_name)
                # Highlight hand cards with play order badges
                for idx, cname in enumerate(play_order):
                    self._js(f'app.highlightChoice({json.dumps(cname)},{idx+1})')
                # Set advice title and push advice
                self._js('app.setAdviceTitle("AI 出牌建议")')
                self._push_advice(formatted, card_tooltips=False)
                self._js('app.setTab("situation")')
        except Exception as e:
            if not self._analysis_stale():
                self._js(f'app.updateAdvice({json.dumps(_html.escape(f"⚠ 战斗分析失败：{e}"))})')
        finally:
            self._busy_combat = False

    def _ai_map(self, state):
        self._busy_strat = True
        # Keep route options visible — reset old labels & only update advice area
        self._js('app.resetRouteLabels()')
        self._show_analyzing("◌  正在分析路线…")
        self._js('app.setAdviceTitle("AI 路线分析")')
        try:
            run    = state.get("run", {})
            player = self._get_player(state) or self.last_player or {}
            mdata  = state.get("map", {})
            hp_pct = int(player.get("hp",0)/max(player.get("max_hp",1),1)*100)
            # 地图场景player可能没有relics/potions，fallback到上次缓存
            p_relics = player.get('relics') or self.last_player.get('relics', [])
            p_potions = player.get('potions') or self.last_player.get('potions', [])
            relics = ', '.join(r['name'] for r in p_relics) or '无'

            # Build full route chains from nodes graph — trace ALL forks
            by_pos = self._build_map_by_pos(mdata)

            opts = mdata.get("next_options", [])
            route_lines = []
            route_idx = 0
            for o in opts:
                first = self._NODE_CN.get(o['type'], o['type'])
                branches = self._trace_all_routes(by_pos, o.get("col", 0), o.get("row", 0))
                if not branches:
                    branches = [[]]
                seen = set()
                for follow in branches:
                    key = tuple(follow)
                    if key in seen:
                        continue
                    seen.add(key)
                    route_idx += 1
                    chain = [first] + [self._NODE_CN.get(t, t) for t in follow]
                    route_lines.append(f"路线{route_idx}：{' → '.join(chain)}")
            opts_str = "\n".join(route_lines) or "（无路线信息）"

            boss_data = mdata.get("boss", {})
            boss = boss_data.get("name") or boss_data.get("type") or "未知"
            deck_info = f"已选牌：{', '.join(self.deck_acquired)}" if self.deck_acquired else ""
            removed   = f"已移除：{', '.join(self.deck_removed)}" if self.deck_removed else ""

            char = player.get('character', '?')
            smart_ctx = self._build_context("map")

            # 资源管理信息
            potions = p_potions
            potion_cnt = sum(1 for p in potions if p.get("name"))
            gold = player.get("gold", 0)
            act = run.get("act", 1)
            floor = run.get("floor", 0)
            archetype = self._deck_archetype or "未定型"

            # 计算路线中各节点类型数量
            route_summary = []
            for o in opts:
                types = [o.get("type", "")]
                types.extend(n.get("type", "") for n in o.get("leads_to", []))
                route_summary.append(types)


            # ── 遗物对路线的影响（数据驱动，只取路线相关遗物） ──
            relic_route_info = self._explain_relics(p_relics, context="map")

            prompt = f"""杀戮尖塔2路线规划。纯文字不用markdown。所有牌名遗物名用中文。极简。

{smart_ctx}

{char} HP{player.get('hp')}/{player.get('max_hp')}({hp_pct}%) 金{gold} 幕{act}层{floor}
遗物：{relics}  Boss：{boss}
药水：{potion_cnt}瓶
流派：{archetype}
{deck_info}  {removed}

可选路线：
{opts_str}

资源管理考量：
- HP{'充足(>70%)' if hp_pct > 70 else '偏低(<50%)需要回血机会' if hp_pct < 50 else '中等(50-70%)谨慎'}
- 金币{gold}{'，够买牌/删牌' if gold >= 75 else '，不够买牌需攒钱'}
- 药水{potion_cnt}瓶{'，精英/Boss战可用' if potion_cnt > 0 else '，没有保命手段要小心'}
- Boss准备：{'牌组'+archetype+'成型中' if archetype != '未定型' else '牌组未定型，需要尽快确定方向'}
{"遗物路线加成：" + chr(10) + relic_route_info if relic_route_info else ""}

严格按以下格式输出，不要输出任何多余标题或分隔：
推荐排名（按优先度从高到低，推荐2-3条最佳路线）：
推荐1=路线X
推荐2=路线Y
推荐3=路线Z

推荐路线X/Y/Z，理由如下：
• 要点1（4-5条，考虑HP预算、金币、药水、牌组完成度、遗物加成、与其他路线对比）
• 要点2
• 要点3
• 要点4
总结一句话"""

            advice = self.llm.ask(prompt)
            if not self._analysis_stale():
                import re as _re_map
                # Parse ranked recommendations: "推荐1=路线4", "推荐2=路线7"
                rankings = {}  # {route_num: priority}
                for m in _re_map.finditer(r'推荐\s*(\d+)\s*[=＝:：]\s*路线\s*(\d+)', advice):
                    priority = int(m.group(1))
                    rn = int(m.group(2))
                    rankings[rn] = priority

                # Update route blocks with priority badges
                for rn, priority in rankings.items():
                    self._js(f'app.updateRouteLabel({rn},{priority})')

                # Strip ranking lines and format noise from advice text
                analysis_lines = []
                for line in advice.split('\n'):
                    stripped = line.strip()
                    if _re_map.match(r'推荐\s*\d+\s*[=＝:：]\s*路线', stripped):
                        continue
                    if _re_map.match(r'路线\d+\s*[=＝]', stripped):
                        continue
                    if _re_map.match(r'^第[一二三四五六七八九十\d]+部分', stripped):
                        continue
                    if _re_map.match(r'^推荐排名', stripped):
                        continue
                    if stripped in ('...', '…'):
                        continue
                    if not stripped:
                        if analysis_lines:
                            analysis_lines.append('')
                        continue
                    analysis_lines.append(stripped)
                while analysis_lines and not analysis_lines[0]:
                    analysis_lines.pop(0)
                while analysis_lines and not analysis_lines[-1]:
                    analysis_lines.pop()
                clean_advice = '\n'.join(analysis_lines)

                self._push_advice(clean_advice, card_tooltips=False)
                self._js('app.setTab("situation")')
        except Exception as e:
            if not self._analysis_stale():
                self._js(f'app.updateAdvice({json.dumps(_html.escape(f"⚠ {e}"))})')
        finally:
            self._busy_strat = False

    def _ai_card(self, state):
        self._busy_strat = True
        stype = state.get("state_type", "")
        is_removal = stype == "card_select"
        self._show_analyzing("⏳  分析移除中…" if is_removal else "⏳  分析选牌中…")
        # Re-render scene to clear old highlights
        self._display_card_reward(state)
        try:
            player  = self._get_player(state) or self.last_player or {}
            cr      = state.get("card_reward") or state.get("card_select") or {}
            rewards = cr.get("cards", [])
            run     = state.get("run", {}) or self.last_run or {}
            # Relics may not be in current scene's player — fallback to cached
            p_relics = player.get('relics') or self.last_player.get('relics', [])
            relics  = ', '.join(r['name'] for r in p_relics) or '无'
            deck_info = f"已选牌：{', '.join(self.deck_acquired)}" if self.deck_acquired else "初始牌组"
            removed   = f"已移除：{', '.join(self.deck_removed)}" if self.deck_removed else ""
            arch_hint = f"期望流派：{self._deck_archetype}" if self._deck_archetype else ""

            # Build card descriptions — source + desc_cn for accuracy
            card_lines = []
            for i, c in enumerate(rewards):
                card_lines.append(f"  [{i}] {self._card_prompt_line(c)}")
            cards_str = "\n".join(card_lines) or "  （无可选牌，可跳过）"

            char = player.get('character', '?')
            char_mechanic = self._get_char_mechanic(char)
            smart_ctx = self._build_context("card_reward")

            if is_removal:
                event_ctx = getattr(self, '_card_select_from_event', None)
                event_hint = ""
                if event_ctx:
                    event_hint = f"\n触发来源：事件「{event_ctx.get('event_name', '?')}」的移除卡牌选项。"

                # Detect how many cards to remove
                remove_count = cr.get("remove_count", cr.get("num_cards",
                               cr.get("max_cards", cr.get("count", 2))))
                # If we can't detect, default to 2 for events (most common), 1 for shops
                if remove_count <= 1 and event_ctx:
                    remove_count = 2

                prompt = f"""杀戮尖塔2移除卡牌。只能删{remove_count}张。直接说删哪{remove_count}张。纯文字，中文牌名。
{event_hint}
{char} 幕{run.get('act')}层{run.get('floor')}  {arch_hint}

可移除的牌：
{cards_str}

只输出{remove_count}行，每行一张要删的牌：
★ 牌名 — 一句话理由
💡 一句话总结"""
            else:
                # Build full deck info for archetype-aware card selection
                full_deck = []
                api_deck = player.get("deck", [])
                if api_deck:
                    from collections import Counter as _Ctr
                    deck_names = _Ctr(c.get("name", "?") for c in api_deck)
                    full_deck_str = " ".join(f"{n}×{cnt}" if cnt > 1 else n for n, cnt in deck_names.most_common())
                elif self.deck_acquired:
                    full_deck_str = " ".join(self.deck_acquired)
                else:
                    full_deck_str = "初始牌组（打击×4 防御×4 出击）"

                prompt = f"""杀戮尖塔2选牌建议。纯文字，不用markdown。所有牌名遗物名用中文。极简输出。

{smart_ctx}

{char} HP{player.get('hp')}/{player.get('max_hp')} 幕{run.get('act')}层{run.get('floor')}
遗物：{relics}
当前牌组({len(api_deck) or '?'}张)：{full_deck_str}
{removed}
{f"流派方向：{self._deck_archetype}" if self._deck_archetype else "尚未定型，根据奖励牌判断最优方向"}

奖励牌：
{cards_str}

{"角色机制：" + char_mechanic if char_mechanic else ""}

重要：
- 必须结合当前牌组构成和流派方向来选牌，不只看单张牌强度，要看它和现有牌组的配合。
- 仔细阅读上方牌组列表，确认牌组中已有哪些牌。
- 阅读每张奖励牌的完整描述来判断，不要凭牌名猜测效果。
- 可以跳过不选牌。如果所有奖励牌都不适合当前构建，建议跳过。
格式（每行一条，不要多余解释）：
★ 牌名 — 理由（结合流派和牌组构成分析，为什么这张最适合当前构建）
○ 牌名 — 理由（可以考虑的备选）
✗ 牌名 — 理由（为什么不适合当前构建）
如果都不值得选，输出：⊘ 建议跳过 — 理由
方向：一句话当前流派+缺什么"""

            advice = self.llm.ask(prompt)

            if not self._analysis_stale():
                full_text = advice
                self._push_advice(full_text)

                # 同步更新卡组构建区方向摘要
                self._display_deck_list()

            for line in advice.split("\n"):
                if line.startswith("期望方向："):
                    self._deck_archetype = line.replace("期望方向：", "").strip()
                    self._save_archetype()
                    break

        except Exception as e:
            self._push_scene(_html.escape(f"⚠ 选牌分析失败：{e}"), tab=None)
        finally:
            self._busy_strat = False
            self._card_analyzed = True

    def _ai_node(self, state):
        self._busy_strat = True
        stype = state.get("state_type", "")
        print(f"[AI Node] analyzing {stype}", flush=True)
        self._show_analyzing("◌  正在分析…")
        try:
            # 重新抓最新状态确保数据完整
            try:
                fresh = requests.get(API_URL, timeout=5).json()
                if fresh.get("state_type") == stype:
                    state = fresh
            except Exception:
                pass
            player = self._get_player(state)
            run    = state.get("run", {})
            relics = ', '.join(r['name'] for r in player.get('relics',[])) or '无'
            hp_pct = int(player.get('hp',0)/max(player.get('max_hp',1),1)*100)

            scene_cn = {"event":"随机事件","rest":"休息点","rest_site":"休息点","shop":"商店","treasure":"宝箱"}
            scene = scene_cn.get(stype, stype)

            # Context-aware relic info for each scene type
            relic_ctx = {"event": "combat", "rest": "map_rest", "rest_site": "map_rest",
                         "shop": "map_shop"}.get(stype, "combat")
            relic_info = self._explain_relics(player.get('relics', []), context=relic_ctx)

            extra = ""
            if stype == "event":
                ev   = state.get("event", {})
                name = ev.get("event_name","")
                opts = "\n".join(
                    f"[{o['index']}] {o['title']}：{o['description']}"
                    for o in ev.get("options",[]) if not o.get("is_locked"))
                extra = f"事件：{name}\n选项：\n{opts}"
                prompt = f"""杀戮尖塔2事件建议，纯文字不用markdown，所有牌名遗物名用中文，按格式输出每个选项。

幕{run.get('act')}·层{run.get('floor')}  {player.get('character','?')}  HP：{player.get('hp')}/{player.get('max_hp')}（{hp_pct}%）  金币：{player.get('gold')}
遗物：{relics}
{extra}

格式（每个选项独立分析）：
★ [选项名] — 推荐理由（获得什么，值不值）
○ [选项名] — 可选理由（利弊分析）
✗ [选项名] — 不推荐理由（风险是什么）

💡 最佳选择 — 综合当前HP/金币/牌组方向给出结论"""
            elif stype in ("rest", "rest_site"):
                prompt = f"""杀戮尖塔2休息点建议，纯文字不用markdown。所有牌名遗物名用中文。

{player.get('character','?')} HP：{player.get('hp')}/{player.get('max_hp')}（{hp_pct}%）  幕{run.get('act')}·层{run.get('floor')}
遗物：{relics}
{'已选牌组：'+', '.join(self.deck_acquired) if self.deck_acquired else '初始牌组'}
{'流派：'+self._deck_archetype if self._deck_archetype else ''}
{"休息点相关遗物效果：" + chr(10) + relic_info if relic_info else ""}

格式：
★ 推荐：补血 或 锻造[牌名]
理由：一句话（考虑HP百分比、遗物效果、接下来的路线、升级哪张牌收益最大）
💡 如果锻造，说明升级后的效果变化"""
            elif stype == "shop":
                shop  = state.get("shop", {})
                shop_items = shop.get("items", [])
                items = []
                for si in shop_items:
                    if not si.get("is_stocked"):
                        continue
                    cat = si.get("category", "")
                    cost = si.get("cost", "?")
                    if cat == "card":
                        sale = " 折扣" if si.get("on_sale") else ""
                        card_desc = self._card_prompt_line({"name": si.get("card_name", "?")})
                        items.append(f"  牌·{card_desc}（{cost}金{sale}）")
                    elif cat == "relic":
                        items.append(f"  遗物·{si.get('relic_name','?')}（{cost}金）：{si.get('relic_description','')[:30]}")
                    elif cat == "potion":
                        items.append(f"  药水·{si.get('potion_name','?')}（{cost}金）")
                    elif cat == "purge":
                        items.append(f"  删牌服务（{cost}金）")
                items_str = chr(10).join(items) or '（无物品）'
                deck_info = f"已选牌：{', '.join(self.deck_acquired)}" if self.deck_acquired else "初始牌组"
                removed = f"已移除：{', '.join(self.deck_removed)}" if self.deck_removed else ""
                arch_hint = f"流派方向：{self._deck_archetype}" if self._deck_archetype else ""

                prompt = f"""杀戮尖塔2商店购买建议。纯文字，不用markdown。所有牌名遗物名用中文。极简输出。

金币：{player.get('gold')}  HP：{player.get('hp')}/{player.get('max_hp')}（{hp_pct}%）  幕{run.get('act')}·层{run.get('floor')}
遗物：{relics}
{deck_info}
{removed}
{arch_hint}

商店物品：
{items_str}
{"商店相关遗物效果：" + chr(10) + relic_info if relic_info else ""}

重要：
- 结合当前牌组构成、流派方向和金币预算来决定买什么。
- 商店有删牌服务，考虑是否需要删牌来精简牌组。
格式（每行一条，按优先级排序，不要多余解释）：
★ 物品名 — 理由（为什么值得买，和当前构建的配合）
○ 物品名 — 理由（可以考虑，性价比分析）
✗ 物品名 — 理由（为什么不值得）
💡 购买策略 — 综合金币预算和后续需求给出购买顺序建议"""
                advice = self.llm.ask(prompt)
                if not self._analysis_stale():
                    self._push_advice(advice)
                    self._js('app.setTab("situation")')
                return
            else:  # treasure
                prompt = f"杀戮尖塔2宝箱，直接拿。HP：{player.get('hp')}/{player.get('max_hp')}，幕{run.get('act')}·层{run.get('floor')}。一句话说说拿到宝箱对当前局面的影响。"

            advice = self.llm.ask(prompt)
            if not self._analysis_stale():
                self._push_advice(advice)
                self._js('app.setTab("situation")')
        except Exception as e:
            print(f"[AI Node] error: {e}", flush=True)
            if not self._analysis_stale():
                self._js(f'app.updateAdvice({json.dumps(_html.escape(f"⚠ {e}"))})')
        finally:
            self._busy_strat = False

    def _initial_analysis(self, state):
        """首次连接时自动分析角色和流派方向。"""
        self._busy_strat = True
        try:
            # 等 API 稳定再重新抓完整状态
            time.sleep(2)
            try:
                fresh = requests.get(API_URL, timeout=5).json()
                if fresh.get("state_type") not in ("unknown", "menu", None):
                    state = fresh
            except Exception:
                pass

            player = self._get_player(state)
            run    = state.get("run", {})
            # 如果仍然没有 player 数据，跳过分析
            if not player or not player.get("character"):
                self._js(f'app.updateDeckAnalysis({json.dumps("  等待游戏数据…")})')
                return
            relics  = ", ".join(r["name"] for r in player.get("relics", [])) or "无"
            potions = ", ".join(p["name"] for p in player.get("potions", [])) or "无"
            deck_info = f"已选牌：{', '.join(self.deck_acquired)}" if self.deck_acquired else "初始牌组"
            removed   = f"已移除：{', '.join(self.deck_removed)}" if self.deck_removed else ""
            arch      = f"上次流派：{self._deck_archetype}" if self._deck_archetype else ""

            # 遗物详细描述
            relic_details = "\n".join(
                f"  · {r['name']}：{r.get('description','')[:50]}"
                for r in player.get("relics", [])) or "  无"

            char = player.get('character', '?')
            # 角色知识库
            char_info = {
                "静默猎手": "核心机制：毒素叠加+弃牌流+灵活性。常见流派：毒素流（恶毒+催化剂+致死毒药）、弃牌流（暗器+专注+工具箱）、小刀/旋转流（无限刀+剑柄打击循环）、灵活过牌流。初始牌组含打击×5/防御×5/幸存者×1/中和×1。",
                "铁甲战士": "核心机制：力量叠加+重击+自伤流。常见流派：力量流（恶魔形态+重击）、格挡流（铁壁+金属化）、消耗流（感染+燃烧）。初始含打击×5/防御×4/猛击×1。",
                "缺陷体": "核心机制：充能球（闪电/冰霜/黑暗/等离子）+专注力。常见流派：闪电流、冰霜堆叠流、黑暗流、全球混合流。",
            }
            char_desc = char_info.get(char, f"未知角色（{char}），请根据遗物和已选牌推断流派。")

            # 获取历史教训 + 玩家趋势
            lessons = self._get_relevant_lessons(char)
            trend = self._get_player_trend()

            prompt = f"""你是杀戮尖塔2（Slay the Spire 2）专家教练。纯文字，不用markdown。所有牌名遗物名用中文。

这是一款roguelike卡牌游戏，玩家每局随机构建卡组，通过3幕关卡击败Boss通关。

角色知识：{char_desc}
{lessons}
{trend}

当前状态：
角色：{char}  HP：{player.get('hp')}/{player.get('max_hp')}  金币：{player.get('gold', 0)}
幕{run.get('act')}·层{run.get('floor')}  飞升：{run.get('ascension', 0)}

遗物（每个遗物都有被动效果）：
{relic_details}

药水：{potions}
{deck_info}  {removed}
{arch}

请给出开局方向分析（每项一行）：
角色优势：（这个角色最强的机制是什么）
遗物协同：（现有遗物配合什么流派最好）
期望成型：（最优流派目标）
核心需求：（接下来最需要找什么牌/遗物）
风险提示：（当前需要注意什么）"""

            result = self.llm.ask(prompt)
            result_html = self._render_formatted_html(result, header="── 开局分析 ──────────────────────────")
            result_html = self._add_card_tooltips(result_html)
            self._js(f'app.updateDeckAnalysis({json.dumps(result_html)})')

            # 提取流派
            for line in result.split("\n"):
                if "期望成型" in line:
                    self._deck_archetype = line.split("：", 1)[-1].strip() if "：" in line else ""
                    if self._deck_archetype:
                        self._save_archetype()
                    break
        except Exception as e:
            self._js(f'app.updateDeckAnalysis({json.dumps(_html.escape(f"⚠ 开局分析失败：{e}"))})')
        finally:
            self._busy_strat = False

    def _refresh_deck_box(self):
        """Update deck building box with current archetype assessment."""
        if not self.deck_acquired and not self.deck_removed:
            return
        if self._busy_deck:
            return
        self._busy_deck = True
        def run():
            try:
                p   = self.last_player
                run = self.last_run
                deck = ', '.join(self.deck_acquired) or '初始牌组'
                rmv  = ', '.join(self.deck_removed)  or '无'
                prompt = f"""杀戮尖塔2卡组方向分析，纯文字不用markdown，所有牌名遗物名用中文，按格式输出。

{p.get('character','?')}  幕{run.get('act','?')}  遗物：{', '.join(r['name'] for r in p.get('relics',[]))}
已选牌（本局新增）：{deck}
已移除：{rmv}

格式：
流派判断：（当前最接近哪种流派）
最优方向：（继续发展这个方向需要什么）
次优方向：（备用路线）
当前缺口：（最需要哪类牌/遗物）"""
                result = self.llm.ask(prompt)
                full_text = (f"── 已选牌 ────────────────────────────\n"
                             f"{', '.join(self.deck_acquired)}\n\n"
                             f"── 方向分析 ──────────────────────────\n"
                             + result)
                result_html = self._render_formatted_html(full_text)
                result_html = self._add_card_tooltips(result_html)
                self._js(f'app.updateDeckAnalysis({json.dumps(result_html)})')
            except Exception:
                pass
            finally:
                self._busy_deck = False
        threading.Thread(target=run, daemon=True).start()

    def _do_deck_strategy(self):
        """分析当前牌组的流派方向、强度、未来选牌策略。"""
        try:
            state = self.last_state or {}
            player = self._get_player(state) or self.last_player
            run = state.get("run") or self.last_run or {}
            char = player.get("character", "?")

            relics = ", ".join(r["name"] for r in player.get("relics", [])) or "无"
            deck_info = ", ".join(self.deck_acquired) if self.deck_acquired else "初始牌组"
            removed = ", ".join(self.deck_removed) if self.deck_removed else "无"
            current_arch = self._deck_archetype or "未确定"

            smart_ctx = self._build_context("deck")
            lessons = self._get_relevant_lessons(char)
            trend = ""  # Skip trend to save tokens

            # 本局路线摘要
            route_summary = []
            for entry in self._run_replay[-10:]:  # 最近10个事件
                if entry.get("type") in ("card_reward", "card_select"):
                    opts = ", ".join(entry.get("options", []))
                    chosen = entry.get("chosen", "?")
                    route_summary.append(f"第{entry.get('floor','')}层选牌: [{opts}] → {chosen}")
                elif entry.get("type") == "combat":
                    enemies = ", ".join(entry.get("enemies", []))
                    hp_loss = entry.get("start_hp",0) - entry.get("end_hp",0)
                    route_summary.append(f"第{entry.get('floor','')}层战斗 vs {enemies} (损{hp_loss}HP)")
            route_text = "\n".join(route_summary) if route_summary else "刚开局"

            char_cards_ref = ""

            prompt = f"""你是杀戮尖塔2卡组构建顾问。纯文字，不用markdown符号。简洁扼要。
【严禁英文】所有牌名必须用中文。只使用下方牌名列表中的名字，不要自己编造牌名。
{char_cards_ref}

{smart_ctx}
{lessons}
{trend}

{char} HP{player.get('hp')}/{player.get('max_hp')} 金{player.get('gold',0)} 幕{run.get('act')}层{run.get('floor')} A{run.get('ascension',0)}
遗物：{relics}
已选牌：{deck_info}
已移除：{removed}
当前流派：{current_arch}
路线：{route_text}

简洁输出，每项1-2句。牌名后标✓已有 ✗缺少：

流派：走什么方向
核心牌：该流派的核心牌清单（每张标✓或✗）
辅助牌：协同辅助牌清单（每张标✓或✗），简述与核心牌的联动效果
过渡牌：当前牌组中不属于流派但暂时有用的牌，以及何时该替换
组合技：目前已有的或即将成型的关键combo，简述机制
强度：当前完成度（X/Y核心到位），缺什么关键拼图
找牌：下次优先拿什么（按优先级排序）
避雷：不拿什么，为什么
打法：当前牌组怎么打（简述回合套路）"""

            result = self.llm.ask(prompt)
            result_html = self._render_formatted_html(result)
            result_html = self._add_card_tooltips(result_html)
            self._js(f'app.updateDeckAnalysis({json.dumps(result_html)})')

            # 保存分析文本到实例变量（供 session 持久化使用）
            self._deck_analysis_text = result

            # 更新流派判断（从AI回复中提取）
            if "流派" in result and not self._deck_archetype:
                # 从 archetype_matrix 获取当前角色的流派列表
                _char_archetypes = []
                if hasattr(self, '_matrix') and self._matrix:
                    _char_data = self._matrix.get("characters", {}).get(char, {})
                    _char_archetypes = [{"name": k} for k in _char_data.get("archetypes", {}).keys()]
                for a in _char_archetypes:
                    if a["name"] in result:
                        self._deck_archetype = a["name"]
                        self._save_archetype()
                        break

            # 保存 session（用户主动分析后持久化）
            self._save_session()

        except Exception as e:
            self._js(f'app.updateDeckAnalysis({json.dumps(_html.escape(f"⚠ 分析失败：{e}"))})')
        finally:
            self._js('app.setButtonState("btn-deck", "◆  求策·卡组  ◆", false)')

    def _do_freeform_ask(self, question):
        """自由提问：带上当前完整游戏状态，让 AI 回答玩家的任何问题。"""
        try:
            # 重新抓最新状态
            try:
                state = requests.get(API_URL, timeout=5).json()
            except Exception:
                state = self.last_state or {}

            player = self._get_player(state)
            run    = state.get("run", {})
            stype  = state.get("state_type", "")

            # 构建状态摘要
            ctx_parts = [
                f"角色：{player.get('character','?')}  HP：{player.get('hp','?')}/{player.get('max_hp','?')}  金币：{player.get('gold','?')}",
                f"幕{run.get('act','?')}·层{run.get('floor','?')}  当前状态：{stype}",
                f"遗物：{', '.join(r['name'] for r in player.get('relics', [])) or '无'}",
                f"药水：{', '.join(p['name'] for p in player.get('potions', [])) or '无'}",
            ]
            if self.deck_acquired:
                ctx_parts.append(f"已选牌：{', '.join(self.deck_acquired)}")
            if self._deck_archetype:
                ctx_parts.append(f"流派方向：{self._deck_archetype}")

            # 战斗中额外加手牌和敌人信息
            if stype in ("monster", "elite", "boss"):
                battle = state.get("battle", {})
                hand = battle.get("player", {}).get("hand", [])
                enemies = battle.get("enemies", [])
                if hand:
                    hand_str = ", ".join(f"{c['name']}(费{c.get('cost','?')})" for c in hand)
                    ctx_parts.append(f"手牌：{hand_str}")
                    ctx_parts.append(f"能量：{battle.get('player',{}).get('energy','?')}/{battle.get('player',{}).get('max_energy','?')}")
                if enemies:
                    for e in enemies:
                        intent = self._fmt_intent(e.get("intents", []))
                        ctx_parts.append(f"敌人：{e['name']} HP:{e.get('hp','?')}/{e.get('max_hp','?')} 意图:{intent}")

            ctx = "\n".join(ctx_parts)

            # 获取角色策略知识
            char = player.get('character', '?')
            char_db = STRATEGY_DB.get(char, {})
            all_strat = "\n".join(v for v in char_db.values())

            prompt = f"""你是杀戮尖塔2专家教练。纯文字回答，不用markdown符号。

角色策略知识：
{all_strat or COMBAT_BASICS}

当前游戏状态：
{ctx}

玩家的问题：{question}

请结合策略知识和当前游戏状态给出针对性的回答。简洁实用。"""

            answer = self.llm.ask(prompt)
            full_text = f"❓ {question}\n\n{answer}"
            answer_html = self._render_formatted_html(full_text)
            answer_html = self._add_card_tooltips(answer_html)
            self._push_scene(answer_html)
        except Exception as e:
            self._push_scene(_html.escape(f"⚠ 提问失败：{e}"), tab=None)
        finally:
            self._js('app.setButtonState("btn-situation", "◆  求策·当前形势  ◆", false)')
