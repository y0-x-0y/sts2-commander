"""HistoryMixin — 日志记录、回放、复盘分析。

修改历史记录和复盘逻辑只需编辑此文件。
pywebview v6.0 — pushes HTML via _js() calls.
"""
import html as _html
import json
import os
import threading
from datetime import datetime

from overlay.constants import (
    HISTORY_FILE, SESSION_FILE, _proj,
    _cn_power, _cn_relic, _cn_potion,
)


class HistoryMixin:

    # ══════════════════════════════════════════
    #  DETAILED REPLAY RECORDING (0 token)
    # ══════════════════════════════════════════
    def _record_combat_snapshot(self, state, cur_round, is_new_round):
        """记录战斗中的每个关键状态快照。"""
        if not is_new_round:
            return
        battle = state.get("battle", {})
        player = battle.get("player", {})
        if not player:
            return
        snapshot = {
            "round": cur_round,
            "timestamp": datetime.now().isoformat(),
            "hp": player.get("hp", 0),
            "block": player.get("block", 0),
            "energy": player.get("energy", 0),
            "hand": [
                {"name": c.get("name",""), "cost": c.get("cost","?"),
                 "can_play": c.get("can_play", False), "index": c.get("index",-1)}
                for c in player.get("hand", [])
            ],
            "draw_pile": player.get("draw_pile_count", 0),
            "discard_pile": player.get("discard_pile_count", 0),
            "powers": [{"name": p.get("name",""), "amount": p.get("amount",0)}
                       for p in player.get("powers", [])],
            "enemies": [
                {"name": e.get("name",""), "hp": e.get("hp",0), "max_hp": e.get("max_hp",1),
                 "block": e.get("block",0),
                 "intents": [i.get("type","") + (":" + str(i.get("label",""))) if i.get("label") else i.get("type","")
                             for i in e.get("intents", [])],
                 "powers": [{"name": p.get("name",""), "amount": p.get("amount",0)}
                            for p in e.get("powers", [])]}
                for e in battle.get("enemies", [])
            ]
        }
        self._battle_log.append(snapshot)

    def _record_decision(self, state, stype):
        """记录选牌/商店/事件/休息决策。"""
        run = state.get("run", {})
        player = self._get_player(state)
        entry = {
            "type": stype,
            "floor": run.get("floor", 0),
            "timestamp": datetime.now().isoformat(),
        }
        if stype in ("card_reward", "card_select"):
            cr = state.get("card_reward") or state.get("card_select") or {}
            entry["options"] = [c.get("name","") for c in cr.get("cards", [])]
            # 选了什么在 deck_acquired 最后一条
            entry["chosen"] = self.deck_acquired[-1] if self.deck_acquired else "跳过"
        elif stype == "shop":
            shop = state.get("shop", {})
            entry["available_cards"] = [c.get("name","") for c in shop.get("cards", [])]
            entry["available_relics"] = [r.get("name","") for r in shop.get("relics", [])]
            entry["gold"] = (player or {}).get("gold", 0)
        elif stype == "event":
            ev = state.get("event", {})
            entry["event_name"] = ev.get("event_name") or ev.get("name", "")
            entry["options"] = [o.get("title","") for o in ev.get("options", [])]
        elif stype in ("rest", "rest_site"):
            entry["options"] = [o.get("name","") for o in state.get("rest_site", state.get("rest", {})).get("options", [])]
        self._run_replay.append(entry)

    def _save_run_replay(self):
        """保存当前局的完整回放到文件。"""
        if not self._run_replay:
            return
        replay_dir = os.path.expanduser("~/Projects/games/sts2/replays")
        os.makedirs(replay_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        char = self.last_player.get("character", "unknown")
        fname = f"{ts}_{char}.json"
        replay = {
            "character": char,
            "ascension": self._char_ascension.get(f"CHARACTER.{char.upper()}", 0),
            "timestamp": datetime.now().isoformat(),
            "total_floors": self.last_run.get("floor", 0),
            "deck_acquired": list(self.deck_acquired),
            "deck_removed": list(self.deck_removed),
            "archetype": self._deck_archetype,
            "events": self._run_replay,
            "run_log": list(self.run_log),
        }
        path = os.path.join(replay_dir, fname)
        try:
            with open(path, "w") as f:
                json.dump(replay, f, ensure_ascii=False, indent=2)
            print(f"[Replay] Saved {path} ({len(self._run_replay)} events)")
        except Exception as e:
            print(f"[Replay] Save failed: {e}")

    def _trigger_post_run_review(self, replay_path):
        """局后复盘 — 一次性调用AI分析整局。"""
        threading.Thread(target=self._do_post_run_review, args=(replay_path,), daemon=True).start()

    def _do_post_run_review(self, replay_path):
        """读取回放文件，让AI分析整局表现。"""
        try:
            with open(replay_path) as f:
                replay = json.load(f)

            # 构建精简的回放摘要（不发全部快照，节约token）
            summary_parts = []
            summary_parts.append(f"角色：{replay['character']}  进阶：{replay['ascension']}")
            summary_parts.append(f"总楼层：{replay['total_floors']}  流派：{replay.get('archetype','未定')}")
            summary_parts.append(f"已选牌：{', '.join(replay.get('deck_acquired',[]))}")
            summary_parts.append(f"已移除：{', '.join(replay.get('deck_removed',[]))}")
            summary_parts.append("")

            for ev in replay.get("events", []):
                if ev["type"] == "combat":
                    enemies = ", ".join(ev.get("enemies",[]))
                    hp_loss = ev.get("start_hp",0) - ev.get("end_hp",0)
                    rounds = ev.get("rounds", 0)
                    summary_parts.append(f"第{ev['floor']}层 战斗 vs {enemies}: {rounds}回合, 损HP:{hp_loss}")
                    # 加入关键回合的手牌信息
                    for turn in ev.get("turns", [])[:2]:  # 前2回合详情
                        hand = ", ".join(c["name"] for c in turn.get("hand",[]))
                        enames = " / ".join(f"{e['name']}({e['hp']}HP)" for e in turn.get("enemies",[]))
                        summary_parts.append(f"  R{turn['round']}: 手牌[{hand}] 敌人[{enames}]")
                elif ev["type"] in ("card_reward", "card_select"):
                    opts = ", ".join(ev.get("options",[]))
                    chosen = ev.get("chosen", "?")
                    summary_parts.append(f"第{ev['floor']}层 选牌: 可选[{opts}] → 选了{chosen}")
                elif ev["type"] == "event":
                    summary_parts.append(f"第{ev['floor']}层 事件: {ev.get('event_name','')}")
                elif ev["type"] == "shop":
                    summary_parts.append(f"第{ev['floor']}层 商店: 金币{ev.get('gold',0)}")

            summary = "\n".join(summary_parts)

            # 获取角色流派知识
            char = replay.get("character", "")
            char_archetypes = self._archetypes.get(char, {}).get("archetypes", [])
            arch_names = ", ".join(a["name"] for a in char_archetypes[:5])

            prompt = f"""杀戮尖塔2局后复盘。纯文字不用markdown。所有牌名遗物名用中文。极简。

流派参考：{arch_names}

{summary}

格式（每行一条）：
构筑：一句话评价选牌路线
操作：一句话评价出牌
运气：一句话
转折点：哪个决策最影响结果
建议：下次怎么改

总共不超过150字。"""

            review = self.llm.ask(prompt)

            # 保存复盘结果
            lessons_file = os.path.expanduser("~/Projects/sts2/knowledge/lessons.json")
            lessons = []
            try:
                if os.path.exists(lessons_file):
                    with open(lessons_file) as f:
                        lessons = json.load(f)
            except Exception:
                pass

            lessons.append({
                "timestamp": datetime.now().isoformat(),
                "character": replay["character"],
                "ascension": replay["ascension"],
                "floors": replay["total_floors"],
                "archetype": replay.get("archetype", ""),
                "result": "通关" if replay["total_floors"] >= 40 else f"第{replay['total_floors']}层阵亡",
                "review": review
            })
            with open(lessons_file, "w") as f:
                json.dump(lessons, f, ensure_ascii=False, indent=2)

            # 显示在历史标签
            review_html = self._render_formatted_html(f"── 局后复盘 ─────────────────────\n\n{review}")
            self._js(f'app.updateLogTimeline({json.dumps(review_html)})')
            self._js('app.setTab("log")')
            print(f"[Review] Post-run review saved to lessons.json")

            # 每3局触发跨局趋势分析
            if len(lessons) >= 3 and len(lessons) % 3 == 0:
                self._do_cross_run_analysis(lessons)

        except Exception as e:
            print(f"[Review] Failed: {e}")

    def _do_cross_run_analysis(self, lessons):
        """每3局做一次跨局趋势分析，写入 player_profile.json。"""
        try:
            # 取最近的一批（最多9局，3次趋势周期）
            recent = lessons[-9:]

            # 本地统计（0 token）
            by_char = {}
            for l in recent:
                char = l.get("character", "?")
                if char not in by_char:
                    by_char[char] = {"runs": 0, "wins": 0, "floors": [], "archetypes": [], "reviews": []}
                by_char[char]["runs"] += 1
                by_char[char]["floors"].append(l.get("floors", 0))
                if l.get("result", "").startswith("通关"):
                    by_char[char]["wins"] += 1
                by_char[char]["archetypes"].append(l.get("archetype", ""))
                by_char[char]["reviews"].append(l.get("review", "")[:100])

            # 构建精简摘要
            parts = []
            for char, data in by_char.items():
                avg_floor = sum(data["floors"]) / len(data["floors"])
                win_rate = data["wins"] / data["runs"] * 100
                arch_counts = {}
                for a in data["archetypes"]:
                    if a:
                        arch_counts[a] = arch_counts.get(a, 0) + 1
                parts.append(f"{char}: {data['runs']}局 胜率{win_rate:.0f}% 均层{avg_floor:.0f}")
                parts.append(f"  流派: {arch_counts}")
                for i, r in enumerate(data["reviews"]):
                    parts.append(f"  第{i+1}局教训: {r}")

            summary = "\n".join(parts)

            prompt = f"""你是杀戮尖塔2教练，分析玩家最近{len(recent)}局的整体趋势。纯文字不用markdown。所有牌名遗物名用中文。

数据：
{summary}

请分析（每项1-2句，总共不超过150字）：
1. 模式性问题：反复出现的失误是什么？
2. 进步趋势：有没有在改善？
3. 下一步建议：最该优先改进什么？"""

            analysis = self.llm.ask(prompt)

            # 保存到 player_profile.json
            profile_file = os.path.expanduser("~/Projects/sts2/knowledge/player_profile.json")
            profile = {}
            try:
                if os.path.exists(profile_file):
                    with open(profile_file) as f:
                        profile = json.load(f)
            except Exception:
                pass

            profile["last_updated"] = datetime.now().isoformat()
            profile["total_runs_analyzed"] = len(lessons)
            if "trend_history" not in profile:
                profile["trend_history"] = []
            profile["trend_history"].append({
                "timestamp": datetime.now().isoformat(),
                "runs_covered": len(recent),
                "analysis": analysis
            })
            # 保留最近的趋势（不让文件无限增长）
            profile["trend_history"] = profile["trend_history"][-10:]
            profile["latest_trend"] = analysis

            with open(profile_file, "w") as f:
                json.dump(profile, f, ensure_ascii=False, indent=2)

            # 追加显示
            trend_html = self._render_formatted_html(f"\n\n── 跨局趋势（最近{len(recent)}局）────────\n\n{analysis}")
            # Append by getting current + adding new
            self._js(f'document.getElementById("log-timeline").innerHTML += {json.dumps(trend_html)}')
            print(f"[Review] Cross-run trend analysis saved to player_profile.json")

        except Exception as e:
            print(f"[Review] Cross-run analysis failed: {e}")

    def _log_transition(self, leaving_state, leaving_type, next_state):
        run   = leaving_state.get("run") or next_state.get("run") or {}
        ts    = datetime.now().strftime("%H:%M")
        floor = run.get("floor", 0)
        act   = run.get("act", "?")

        if leaving_type in ("unknown", "map") or floor == 0:
            return

        entry = None

        if leaving_type in ("monster", "elite", "boss"):
            battle  = leaving_state.get("battle", {})
            enemies = battle.get("enemies", [])
            prev_hp = self._combat_start_hp if self._combat_start_hp > 0 else battle.get("player", {}).get("hp", 0)
            next_hp = self._get_player(next_state).get("hp", prev_hp)
            lost    = max(0, prev_hp - next_hp)
            rounds  = self._combat_rounds if self._combat_rounds > 0 else battle.get("round", "?")
            names   = "、".join(e.get("name","?") for e in enemies)
            damage  = f"损失 {lost} HP" if lost else "零伤"
            entry   = f"[{ts}]  幕{act}·层{floor}  ⚔ 击败 {names}（{rounds}回合  {damage}）"
            self._combat_start_hp = 0
            self._combat_rounds   = 0

        elif leaving_type == "event":
            ev     = leaving_state.get("event", {})
            name   = ev.get("event_name", "事件")
            chosen = next((o["title"] for o in ev.get("options",[]) if o.get("was_chosen")), None)
            choice = f" → 选「{chosen}」" if chosen else ""
            entry  = f"[{ts}]  幕{act}·层{floor}  ✧ {name}{choice}"

        elif leaving_type in ("card_reward", "card_select"):
            cr     = leaving_state.get("card_reward") or leaving_state.get("card_select") or {}
            cards  = cr.get("cards", [])
            chosen = next((c for c in cards if c.get("was_chosen")), None)
            if chosen:
                cname = chosen["name"] + ("+" if chosen.get("is_upgraded") else "")
                entry = f"[{ts}]  幕{act}·层{floor}  ✦ 选牌：{cname}"
                if cname not in self.deck_acquired:
                    self.deck_acquired.append(cname)
                    self._display_deck_list()
            else:
                entry = f"[{ts}]  幕{act}·层{floor}  ✦ 选牌（跳过）"

        elif leaving_type in ("rest", "rest_site"):
            rest   = leaving_state.get("rest_site", state.get("rest", {}))
            opts   = rest.get("options", [])
            chosen = next((o.get("label", o.get("type","")) for o in opts if o.get("was_chosen")), None)
            action = self._REST_LABELS[chosen][0] if chosen and chosen in self._REST_LABELS else (chosen or "离开")
            entry  = f"[{ts}]  幕{act}·层{floor}  ⌂ 休息点：{action}"

        elif leaving_type == "shop":
            shop   = leaving_state.get("shop", {})
            bought = [c["name"] for c in shop.get("cards",[]) if c.get("was_purchased")]
            bought+= [r["name"] for r in shop.get("relics",[]) if r.get("was_purchased")]
            # purge 可能是 dict (单个) 或 list
            purge_data = shop.get("purge", {})
            purge = []
            if isinstance(purge_data, dict) and purge_data.get("was_chosen"):
                purge = [purge_data.get("card_name", "基础牌")]
            elif isinstance(purge_data, list):
                purge = [c.get("name", "基础牌") for c in purge_data if c.get("was_chosen")]
            if purge:
                self.deck_removed.extend(purge)
                self._display_deck_list()
            parts = []
            if bought: parts.append("购：" + "、".join(bought))
            if purge:  parts.append("删：" + "、".join(purge))
            entry  = f"[{ts}]  幕{act}·层{floor}  ⊕ 商店：{' '.join(parts) or '未购买'}"

        elif leaving_type == "treasure":
            chest  = leaving_state.get("treasure", {})
            relics = [r["name"] for r in chest.get("relics",[]) if r.get("was_obtained")]
            gold   = chest.get("gold", 0)
            parts  = relics + ([f"{gold}金"] if gold else [])
            detail = "、".join(parts) if parts else "已领取"
            entry  = f"[{ts}]  幕{act}·层{floor}  ◇ 宝箱：{detail}"

        if entry:
            self.run_log.append(entry)
            self._refresh_log()
            # 关键状态变化时保存 session
            if leaving_type in ("monster", "card_reward", "card_select", "shop", "event", "rest", "rest_site"):
                threading.Thread(target=self._save_session, daemon=True).start()

    def _refresh_log(self):
        import re

        # ── Timeline items (newest on top, 楼层 labels, <span> elements) ──
        log_lines = list(reversed(self.run_log[-80:]))
        if log_lines:
            tl_parts = []
            for line in log_lines:
                # Extract floor from "幕N·层M" pattern
                floor_match = re.search(r'层(\d+)', line)
                floor_num = int(floor_match.group(1)) if floor_match else 0

                # Determine event type, dot color, and build tl-text
                if "⚔" in line:
                    # Combat: 击败 enemies（rounds回合  损失 N HP）
                    dot_color = "var(--hp)"
                    # Check for boss
                    is_boss = "BOSS" in line or "boss" in line.lower()
                    # Extract enemy names
                    enemy_match = re.search(r'击败\s+(.+?)（', line)
                    enemy_name = enemy_match.group(1).strip() if enemy_match else "未知"
                    # Extract damage
                    dmg_match = re.search(r'损失\s+(\d+)\s*HP', line)
                    damage = int(dmg_match.group(1)) if dmg_match else 0
                    # Extract rounds
                    round_match = re.search(r'(\d+)回合', line)
                    rounds = int(round_match.group(1)) if round_match else 0
                    # Extract gold from log if present
                    gold_match = re.search(r'获得\s*(\d+)\s*金', line)

                    escaped_enemy = _html.escape(enemy_name)
                    dim_parts = []
                    if damage > 0:
                        dim_parts.append(f'受到 {damage} 伤害')
                    else:
                        dim_parts.append('完美战斗 (0伤害)')
                    if gold_match:
                        dim_parts.append(f'获得 {gold_match.group(1)} 金')

                    dim_str = f' <span class="dim">&middot; {" &middot; ".join(dim_parts)}</span>' if dim_parts else ''

                    if is_boss:
                        tl_text = (f'<span style="color:var(--gold);font-weight:600;">BOSS — 击败 '
                                   f'<span style="color:var(--hp);">{escaped_enemy}</span>'
                                   f'{dim_str}</span>')
                    elif "精英" in line or "elite" in line.lower():
                        tl_text = (f'精英战斗 — 击败 <span style="color:var(--hp);">{escaped_enemy}</span>'
                                   f'{dim_str}')
                    else:
                        tl_text = (f'战斗 — 击败 <span style="color:var(--hp);">{escaped_enemy}</span>'
                                   f'{dim_str}')

                elif "✦" in line:
                    # Card pick
                    dot_color = "var(--accent2)"
                    if "跳过" in line:
                        tl_text = '选牌 — 跳过'
                    else:
                        card_match = re.search(r'选牌[：:]\s*(.+)', line)
                        card_name = card_match.group(1).strip() if card_match else "?"
                        tl_text = f'选牌 — 获得 <span style="color:var(--accent2);">{_html.escape(card_name)}</span>'

                elif "⊕" in line:
                    # Shop
                    dot_color = "var(--gold)"
                    # Extract purchase/purge details
                    detail_match = re.search(r'商店[：:]\s*(.+)', line)
                    detail = detail_match.group(1).strip() if detail_match else "浏览"
                    if "购" in detail or "删" in detail:
                        # Parse bought and purged items
                        parts = []
                        buy_match = re.search(r'购[：:]\s*([^删]+)', detail)
                        if buy_match:
                            items = [s.strip() for s in buy_match.group(1).split('、') if s.strip()]
                            item_spans = ', '.join(f'<span style="color:var(--accent2);">{_html.escape(i)}</span>' for i in items)
                            parts.append(f'购买 {item_spans}')
                        purge_match = re.search(r'删[：:]\s*(.+)', detail)
                        if purge_match:
                            purged = [s.strip() for s in purge_match.group(1).split('、') if s.strip()]
                            purge_spans = ', '.join(f'<span style="color:var(--hp);">{_html.escape(p)}</span>' for p in purged)
                            parts.append(f'移除 {purge_spans}')
                        tl_text = '商店 — ' + ' &middot; '.join(parts) if parts else '商店 — 浏览'
                    else:
                        tl_text = f'商店 — {_html.escape(detail)}'

                elif "⌂" in line:
                    # Rest / campfire
                    dot_color = "var(--buff)"
                    action_match = re.search(r'休息点[：:]\s*(.+)', line)
                    action = action_match.group(1).strip() if action_match else "休息"
                    # Check for upgrade action
                    if "锻造" in action or "升级" in action:
                        upgrade_match = re.search(r'(?:锻造升级|升级)\s*(.+)', action)
                        if upgrade_match:
                            card_name = upgrade_match.group(1).strip()
                            tl_text = f'篝火 — 升级 <span style="color:var(--gold);">{_html.escape(card_name)}</span>'
                        else:
                            tl_text = f'篝火 — {_html.escape(action)}'
                    else:
                        tl_text = f'篝火 — {_html.escape(action)}'

                elif "✧" in line:
                    # Event
                    dot_color = "var(--accent)"
                    event_match = re.search(r'✧\s+(.+?)(?:\s*→\s*选「(.+?)」)?$', line)
                    if event_match:
                        event_name = event_match.group(1).strip()
                        choice = event_match.group(2)
                        escaped_name = _html.escape(event_name)
                        if choice:
                            tl_text = (f'遭遇事件 <span style="color:var(--accent2);">「{escaped_name}」</span>'
                                       f' — 选择「{_html.escape(choice)}」')
                        else:
                            tl_text = f'遭遇事件 <span style="color:var(--accent2);">「{escaped_name}」</span> — 等待决策'
                    else:
                        rest_text = line.split("✧")[-1].strip() if "✧" in line else line
                        tl_text = f'事件 — <span style="color:var(--accent2);">{_html.escape(rest_text)}</span>'

                elif "◇" in line:
                    # Treasure
                    dot_color = "var(--gold)"
                    detail_match = re.search(r'宝箱[：:]\s*(.+)', line)
                    detail = detail_match.group(1).strip() if detail_match else "已领取"
                    tl_text = f'宝箱 — {_html.escape(detail)}'

                elif "新局开始" in line or "──" in line:
                    dot_color = "var(--gold)"
                    tl_text = '<span style="color:var(--gold);font-weight:600;">新局开始</span>'
                    floor_num = 0

                else:
                    dot_color = "var(--accent)"
                    rest_text = line.split("]")[-1].strip() if "]" in line else line
                    tl_text = _html.escape(rest_text)

                floor_label = f'楼层 {floor_num}' if floor_num > 0 else ''

                tl_parts.append(
                    f'<div class="timeline-item">'
                    f'<span class="tl-turn">{floor_label}</span>'
                    f'<span class="tl-dot" style="background:{dot_color};"></span>'
                    f'<span class="tl-text">{tl_text}</span>'
                    f'</div>'
                )
            log_html = "".join(tl_parts)
            self._js(f'app.updateLogTimeline({json.dumps(log_html)})')
        elif not self.run_log:
            empty_msg = '<span class="dim">本局尚无记录，开始游戏后自动记录</span>'
            self._js(f'app.updateLogTimeline({json.dumps(empty_msg)})')

        # ── Stats section (stats-grid with stat-box elements) ──
        fights = 0; total_hp_lost = 0; cards_picked = 0; cards_skipped = 0
        shops = 0; rests = 0; events = 0; purges = 0; total_gold = 0
        for entry in self.run_log:
            if "⚔" in entry:
                fights += 1
                m = re.search(r"损失 (\d+) HP", entry)
                if m: total_hp_lost += int(m.group(1))
                g = re.search(r"获得\s*(\d+)\s*金", entry)
                if g: total_gold += int(g.group(1))
            elif "✦ 选牌：" in entry and "跳过" not in entry:
                cards_picked += 1
            elif "✦ 选牌（跳过）" in entry:
                cards_skipped += 1
            elif "⊕ 商店" in entry:
                shops += 1
                if "删：" in entry: purges += 1
            elif "⌂ 休息点" in entry:
                rests += 1
            elif "✧" in entry:
                events += 1

        deck_size = len(self.deck_acquired) if self.deck_acquired else 0
        removed = len(self.deck_removed) if self.deck_removed else 0

        stats_html = (
            '<div class="section-title">运行数据</div>'
            '<div class="stats-grid">'
            f'<div class="stat-box">'
            f'<div class="sb-val" style="color:var(--hp);">{total_hp_lost}</div>'
            f'<div class="sb-label">总受伤</div>'
            f'</div>'
            f'<div class="stat-box">'
            f'<div class="sb-val" style="color:var(--gold);">{total_gold}</div>'
            f'<div class="sb-label">金币获得</div>'
            f'</div>'
            f'<div class="stat-box">'
            f'<div class="sb-val" style="color:var(--buff);">{fights}</div>'
            f'<div class="sb-label">战斗胜利</div>'
            f'</div>'
            f'<div class="stat-box">'
            f'<div class="sb-val" style="color:var(--accent2);">{cards_picked}</div>'
            f'<div class="sb-label">选牌次数</div>'
            f'</div>'
            f'<div class="stat-box">'
            f'<div class="sb-val" style="color:var(--gold);">{shops}</div>'
            f'<div class="sb-label">商店访问</div>'
            f'</div>'
            f'<div class="stat-box">'
            f'<div class="sb-val" style="color:var(--accent);">{events}</div>'
            f'<div class="sb-label">事件遭遇</div>'
            f'</div>'
            '</div>'
        )
        self._js(f'app.updateLogStats({json.dumps(stats_html)})')

    def _on_new_run(self):
        """保存当局历史，重置状态，开始新局。"""
        if self.run_log:
            self._save_run()
        # 保存详细回放并触发复盘
        if self._run_replay:
            self._save_run_replay()
            replay_dir = os.path.expanduser("~/Projects/games/sts2/replays")
            # 找最新的回放文件
            files = sorted(os.listdir(replay_dir))
            if files:
                latest = os.path.join(replay_dir, files[-1])
                self._trigger_post_run_review(latest)
        # 重置本局数据
        self.run_log.clear()
        self.deck_acquired.clear()
        self.deck_removed.clear()
        self._run_replay = []
        self._battle_log = []
        self._deck_analysis_text = ""
        self._deck_archetype = ""
        self.last_round = -1
        # 清空 session（新局开始）
        try:
            os.makedirs(os.path.dirname(SESSION_FILE), exist_ok=True)
            with open(SESSION_FILE, "w") as f:
                json.dump({}, f)
        except Exception:
            pass
        ts = datetime.now().strftime("%m/%d %H:%M")
        self.run_log.append(f"[{ts}]  ── 新局开始 ────────────────────────")
        self._refresh_log()
        self._js(f'app.updateDeckAnalysis({json.dumps("  点击「求策·卡组」获取AI分析")})')
        self._js(f'app.updateDeckList({json.dumps("  新局开始…")})')
        self._push_scene("◌  新局，等待首个事件…", tab=None)
        self._clear_advice()

    def _save_run(self):
        """追加保存本局记录到 JSON 历史文件。"""
        try:
            p   = self.last_player
            run = self.last_run
            # 无有效数据时不保存垃圾记录
            if not p.get("character") or p.get("character") == "?":
                return
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            history = []
            if os.path.exists(HISTORY_FILE):
                with open(HISTORY_FILE) as f:
                    history = json.load(f)
            record = {
                "date":      datetime.now().strftime("%Y-%m-%d %H:%M"),
                "character": p.get("character", "?"),
                "act":       run.get("act", "?"),
                "floor":     run.get("floor", "?"),
                "ascension": run.get("ascension", 0),
                "hp":        f"{p.get('hp', '?')}/{p.get('max_hp', '?')}",
                "gold":      p.get("gold", 0),
                "deck":      self.deck_acquired[:],
                "removed":   self.deck_removed[:],
                "log":       self.run_log[:],
            }
            history.append(record)
            with open(HISTORY_FILE, "w") as f:
                json.dump(history[-50:], f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    ARCHETYPE_FILE = os.path.expanduser("~/Projects/sts2/archetype.json")

    def _save_archetype(self):
        try:
            data = {
                "archetype": self._deck_archetype,
                "deck":      self.deck_acquired[:],
                "removed":   self.deck_removed[:],
                "updated":   datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
            with open(self.ARCHETYPE_FILE, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_archetype(self):
        try:
            if not os.path.exists(self.ARCHETYPE_FILE):
                return
            with open(self.ARCHETYPE_FILE) as f:
                data = json.load(f)
            self._deck_archetype = data.get("archetype", "")
            saved_deck = data.get("deck", [])
            if saved_deck and not self.deck_acquired:
                self.deck_acquired = saved_deck
                self.deck_removed  = data.get("removed", [])
            # 注：不自动填充 box_deck，等玩家点击「求策·卡组」再显示AI分析
        except Exception:
            pass
