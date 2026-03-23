"""DataMixin — 数据加载、卡牌DB、知识库、存档读取、session管理。

修改数据加载逻辑只需编辑此文件。
"""
import json
import os
import threading
from datetime import datetime

from overlay.constants import (
    CARD_DB_FILE,
    EPOCHS_FILE, ARCHETYPES_FILE, MONSTER_AI_FILE, EVENT_GUIDE_FILE,
    CARD_TIER_FILE, MATRIX_FILE,
    SYNERGY_FILE, PIVOT_FILE, BOSS_FILE, HISTORY_FILE, SESSION_FILE,
    PROGRESS_FILE, _proj,
)


class DataMixin:

    # ══════════════════════════════════════════
    #  SESSION PERSISTENCE（同局恢复）
    # ══════════════════════════════════════════
    def _make_run_id(self):
        """生成当前局的唯一标识符。"""
        p    = self.last_player or {}
        run  = self.last_run or {}
        char = p.get("character", "?")
        act  = run.get("act", "?")
        # 用角色名 + 已选牌前3张 组合作为稳定 ID（不依赖楼层，避免进度误判）
        deck_sig = "|".join(sorted(self.deck_acquired[:5])) if self.deck_acquired else "init"
        return f"{char}::{deck_sig}"

    def _save_session(self):
        """保存当前局状态到 session.json。"""
        try:
            os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
            p    = self.last_player or {}
            run  = self.last_run or {}
            data = {
                "run_id":            self._make_run_id(),
                "character":         p.get("character", ""),
                "act":               run.get("act", ""),
                "floor":             run.get("floor", ""),
                "archetype":         self._deck_archetype,
                "deck_acquired":     list(self.deck_acquired),
                "deck_removed":      list(self.deck_removed),
                "deck_analysis_text": self._deck_analysis_text,
                "run_log":           list(self.run_log),
                "run_replay":        list(self._run_replay),
                "battle_log":        list(self._battle_log),
                "saved_at":          datetime.now().isoformat(),
            }
            with open(SESSION_FILE, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Session] Save failed: {e}")

    def _load_session(self):
        """启动时尝试恢复同局 session。只在同一局游戏内恢复。"""
        try:
            if not os.path.exists(SESSION_FILE):
                return
            with open(SESSION_FILE) as f:
                data = json.load(f)
            if not data:
                return

            saved_char     = data.get("character", "")
            saved_floor    = data.get("floor", 0)
            saved_act      = data.get("act", 1)
            saved_acquired = data.get("deck_acquired", [])

            # 尝试从游戏 API 获取当前状态来判断是否同一局
            try:
                import requests as _req
                r = _req.get(API_URL, timeout=2)
                cur = r.json()
                cur_char = cur.get("run", {}).get("character",
                           cur.get("battle", {}).get("player", {}).get("character", ""))
                if not cur_char:
                    for key in ("player", "battle"):
                        p = cur.get(key, {})
                        if isinstance(p, dict):
                            cur_char = p.get("character", "")
                            if cur_char:
                                break
                cur_floor = cur.get("run", {}).get("floor", 0)
                cur_act   = cur.get("run", {}).get("act", 1)

                # 新局检测：楼层回到1、角色变了、或幕数变小
                if cur_floor <= 1 and saved_floor > 1:
                    print(f"[Session] New run detected (floor {saved_floor}→{cur_floor}), starting fresh")
                    return
                if cur_char and saved_char and cur_char != saved_char:
                    print(f"[Session] Different character ({saved_char}→{cur_char}), starting fresh")
                    return
                if cur_act < saved_act:
                    print(f"[Session] Act went backwards ({saved_act}→{cur_act}), starting fresh")
                    return
            except Exception:
                # Can't reach API, skip restore to be safe
                print("[Session] API not reachable, starting fresh")
                return

            # Same run — restore state
            self.deck_acquired       = saved_acquired
            self.deck_removed        = data.get("deck_removed", [])
            self._deck_archetype     = data.get("archetype", "") if saved_acquired else ""
            self._deck_analysis_text = data.get("deck_analysis_text", "")
            self.run_log             = data.get("run_log", [])
            self._run_replay         = data.get("run_replay", [])
            self._battle_log         = data.get("battle_log", [])

            print(f"[Session] Restored: {saved_char}, floor {saved_floor}, "
                  f"{len(self.deck_acquired)} cards, "
                  f"{len(self.run_log)} log entries")

            # 恢复 UI（延迟执行，等窗口 ready）
            def _restore_ui():
                if self.deck_acquired or self.deck_removed:
                    self._display_deck_list()
                if self._deck_analysis_text:
                    result_html = self._render_formatted_html(self._deck_analysis_text)
                    result_html = self._add_card_tooltips(result_html)
                    self._js(f'app.updateDeckAnalysis({json.dumps(result_html)})')
                else:
                    self._js(f'app.updateDeckAnalysis({json.dumps("  点击「求策·卡组」获取AI分析")})')
                if self.run_log:
                    self._refresh_log()

            threading.Timer(0.5, _restore_ui).start()

        except Exception as e:
            print(f"[Session] Load failed: {e}")

    def _load_history(self):
        """加载历史，在日志标签页底部展示最近几局（timeline-item 格式）。"""
        try:
            if not os.path.exists(HISTORY_FILE):
                return
            with open(HISTORY_FILE) as f:
                history = json.load(f)
            if not history:
                return
            import html as _html
            tl_parts = []
            tl_parts.append(
                '<div class="timeline-item">'
                '<span class="tl-turn"></span>'
                '<span class="tl-dot" style="background:var(--gold);"></span>'
                '<span class="tl-text" style="color:var(--gold);font-weight:600;">历史对局</span>'
                '</div>'
            )
            for rec in reversed(history[-5:]):
                hp = rec.get("hp", "?")
                gold = rec.get("gold", "?")
                char = _html.escape(str(rec.get("character", "?")))
                act = rec.get("act", "?")
                floor = rec.get("floor", "?")
                date = _html.escape(str(rec.get("date", "")))
                deck_str = ""
                if rec.get("deck"):
                    cards = ", ".join(_html.escape(c) for c in rec["deck"][:8])
                    deck_str = f' <span class="dim">&middot; 新增: {cards}</span>'
                tl_parts.append(
                    f'<div class="timeline-item">'
                    f'<span class="tl-turn">楼层 {floor}</span>'
                    f'<span class="tl-dot" style="background:var(--accent);"></span>'
                    f'<span class="tl-text">{char} 幕{act} '
                    f'<span class="dim">HP:{hp} 金:{gold}</span> '
                    f'<span class="dim">{date}</span>{deck_str}</span>'
                    f'</div>'
                )
            # Don't push past sessions to timeline — it should show current run only
            # log_html = "".join(tl_parts)
            # threading.Timer(0.1, lambda: self._js(f'app.updateLogTimeline({json.dumps(log_html)})')).start()
            pass
        except Exception:
            pass

    # ══════════════════════════════════════════
    #  HELPERS
    # ══════════════════════════════════════════
    def _display_deck_list(self):
        """deck-grid 卡牌网格显示（匹配 royal_purple 参考 HTML）。"""
        import html as _html

        # 优先从 API 获取完整牌组
        api_deck = []
        state = self.last_state or {}
        player = self._get_player(state) or self.last_player or {}
        api_deck = player.get("deck", [])

        # 如果 API 无 deck，从存档读取
        if not api_deck:
            _, save_deck = self._load_save_data()
            api_deck = save_deck or []

        from overlay.card_db import TYPE_CN, RARITY_CN

        if api_deck:
            total = len(api_deck)
            arch_label = ""
            if self._deck_archetype and self.deck_acquired:
                arch_label = _html.escape(self._deck_archetype)
            title = f'卡组一览 — {arch_label} ({total}张)' if arch_label else f'卡组一览 ({total}张)'

            html_parts = [f'<div class="section-title">{title}</div>']
            # Normalize cards so _render_card can read them
            normalized = []
            for c in api_deck:
                nc = dict(c)
                nc["name"] = self.cards.fmt_name(c)
                nc["rarity"] = self.cards.get_rarity(c)
                nc["type"] = self.cards.get_type(c)
                normalized.append(nc)
            html_parts.append(self._render_grouped_cards(normalized))
            self._js(f'app.updateDeckList({json.dumps("".join(html_parts))})')
            return

        # 无牌组数据时，显示 deck_acquired/removed 摘要
        if self.deck_acquired or self.deck_removed:
            total = len(self.deck_acquired)
            arch_label = _html.escape(self._deck_archetype) if self._deck_archetype else ""
            title = f'卡组一览 — {arch_label} ({total}张新增)' if arch_label else f'卡组一览 ({total}张新增)'
            html_parts = [f'<div class="section-title">{title}</div>']
            cards = [{"name": n} for n in self.deck_acquired]
            if cards:
                html_parts.append(self._render_card_grid(cards))
            for card_name in self.deck_removed:
                html_parts.append(
                    f'<div style="font-size:11px;color:var(--hp);text-decoration:line-through;margin:2px 0;">'
                    f'{_html.escape(card_name)} (已移除)</div>'
                )
            self._js(f'app.updateDeckList({json.dumps("".join(html_parts))})')
        else:
            self._js(f'app.updateDeckList({json.dumps("  等待游戏数据…")})')

    # Card data is now handled entirely by CardDB (self.cards).
    # All lookups go through self.cards.detail(name).

    def _load_unlock_state(self):
        """从存档读取解锁状态。"""
        self._unlocked_cards = set()
        self._unlocked_relics = set()
        self._unlocked_epochs = set()
        self._locked_epoch_cards = set()
        self._char_ascension = {}
        try:
            if os.path.exists(PROGRESS_FILE):
                with open(PROGRESS_FILE) as f:
                    prog = json.load(f)
                self._unlocked_cards = set(prog.get("discovered_cards", []))
                self._unlocked_relics = set(prog.get("discovered_relics", []))
                self._unlocked_epochs = {e["id"] for e in prog.get("epochs", []) if e["state"] == "revealed"}
                for cs in prog.get("character_stats", []):
                    self._char_ascension[cs["id"]] = cs.get("max_ascension", 0)
                # 解析锁定纪元的牌
                if os.path.exists(EPOCHS_FILE):
                    with open(EPOCHS_FILE) as f:
                        epochs = json.load(f)
                    for eid, data in epochs.items():
                        if eid not in self._unlocked_epochs:
                            for c in data.get("cards", []):
                                self._locked_epoch_cards.add(c["id"])
                print(f"[Unlock] {len(self._unlocked_cards)} cards, {len(self._unlocked_relics)} relics, asc={self._char_ascension}")
        except Exception as e:
            print(f"[Unlock] Failed: {e}")

    def _load_knowledge(self):
        """从 KnowledgeDB 同步属性（兼容旧代码，逐步移除）。"""
        # 委托给 self.kb（KnowledgeDB，已在 ai_advisor_app.__init__ 中创建）
        self._matrix = self.kb.matrix
        self._boss_guide = self.kb.boss_guide
        self._monster_ai = self.kb.monster_ai
        self._event_guide = self.kb.event_guide
        # Relic/potion effects now data-driven via _explain_relics/_explain_potions (JSON lookup)
        self._card_tiers = self.kb.card_tiers
        self._synergy_index = self.kb.synergy_index
        self._pivot_rules = self.kb.pivot_rules
        self._archetypes = self.kb.archetypes
        # 加载历史教训（KnowledgeDB 不管这个，留在这里）
        self._lessons = []
        import os
        lessons_file = os.path.expanduser("~/Projects/sts2/knowledge/lessons.json")
        try:
            if os.path.exists(lessons_file):
                with open(lessons_file) as f:
                    self._lessons = json.load(f)
                print(f"[Knowledge] {len(self._lessons)} post-run lessons loaded")
        except Exception:
            pass

    def _get_relevant_lessons(self, char, max_lessons=3):
        """获取与当前角色相关的最近教训。"""
        relevant = [l for l in self._lessons if l.get("character") == char]
        # 最近的优先
        recent = relevant[-max_lessons:] if relevant else []
        if not recent:
            return ""
        parts = ["历史教训（过往局复盘）："]
        for l in recent:
            if l.get('result') and l.get('review'):
                parts.append(f"  {l['result']} ({l.get('archetype','')}) → {l['review'][:80]}")
            elif l.get('lesson'):
                parts.append(f"  {l['lesson'][:100]}")
        return "\n".join(parts)

    def _get_player_trend(self):
        """获取最新的跨局趋势分析。"""
        profile_file = os.path.expanduser("~/Projects/sts2/knowledge/player_profile.json")
        try:
            if os.path.exists(profile_file):
                with open(profile_file) as f:
                    profile = json.load(f)
                trend = profile.get("latest_trend", "")
                if trend:
                    return f"玩家近期趋势：{trend[:120]}"
        except Exception:
            pass
        return ""

    def _collect_cards(self, state):
        """从 API 状态中收集卡牌信息 — 委托给 CardDB。"""
        if hasattr(self, 'cards'):
            self.cards.collect(state)

    def _load_save_data(self):
        """从存档文件读取玩家数据（character, HP, gold, deck）。
        返回 (player_dict, deck_list) 其中 deck_list 是 [{id, floor}, ...] 格式。
        """
        from overlay.constants import _SAVE_BASE
        save_paths = []
        if _SAVE_BASE:
            save_paths.append(os.path.join(_SAVE_BASE, "modded/profile1/saves/current_run.save"))
            save_paths.append(os.path.join(_SAVE_BASE, "profile1/saves/current_run.save"))
        for path in save_paths:
            if not os.path.exists(path):
                continue
            try:
                with open(path) as f:
                    data = json.load(f)
                players = data.get("players", [])
                if not players:
                    continue
                p = players[0]
                char_id = p.get("character_id", "")
                from overlay.display import DisplayMixin
                char_name = DisplayMixin._CHAR_CN.get(char_id, char_id.replace("CHARACTER.", "")) if char_id else "—"
                player_dict = {
                    "character": char_name,
                    "hp":        p.get("current_hp", 0),
                    "max_hp":    p.get("max_hp", 80),
                    "gold":      p.get("gold", 0),
                    "energy":    p.get("max_energy", 3),
                    "max_energy": p.get("max_energy", 3),
                    "block":     0,
                    "relics":    [{"name": r.get("id", "?").replace("RELIC.", "")} for r in p.get("relics", [])],
                }
                deck_list = p.get("deck", [])
                return player_dict, deck_list
            except Exception as e:
                print(f"[SaveLoad] {e}")
        return {}, []

    def _get_relics_from_save(self):
        """Read current relics from save file — reuses _load_save_data."""
        player, _ = self._load_save_data()
        return player.get("relics", [])

    def _get_player(self, state):
        return (state.get("battle", {}).get("player") or
                state.get("event", {}).get("player") or
                state.get("map", {}).get("player") or
                state.get("rest_site", state.get("rest", {})).get("player") or
                state.get("shop", {}).get("player") or
                state.get("rewards", {}).get("player") or
                state.get("card_reward", {}).get("player") or
                state.get("card_select", {}).get("player") or
                state.get("treasure", {}).get("player") or
                state.get("player") or {})
