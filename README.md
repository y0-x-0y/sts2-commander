<h1 align="center">
  STS2 Commander
  <br>
  <sub>Slay the Spire 2 — Real-time Strategy Overlay</sub>
</h1>

<p align="center">
  A real-time decision engine for Slay the Spire 2.
  <br>
  Reads game state via MCP API. Analyzes every decision point. Covers every scene.
</p>

<p align="center">
  杀戮尖塔2 实时策略指挥官 — 通过 MCP API 读取游戏状态，覆盖全场景的策略分析浮窗。
</p>

---

## Features

| Scene | What it does |
|:------|:-------------|
| **Combat** | Play order with numbered badges, damage/block pre-calculated with strength/weakness/vulnerability, draw pile & discard pile awareness, cross-turn tempo planning |
| **Map** | All forking paths visualized with node icons, top 2-3 routes ranked by priority, relic-aware path scoring (healing/elite/shop/rest) |
| **Card Reward** | Selection based on full deck composition and archetype direction, not just individual card strength |
| **Shop** | Purchase priority with budget awareness and relic synergy |
| **Event** | Pros/cons for every option |
| **Rest** | Heal vs upgrade decision with relic awareness |
| **Deck View** | Grouped by attack/skill/power, hover for type, rarity, full description |

| 场景 | 说明 |
|:-----|:-----|
| **战斗** | 出牌顺序标注，伤害/格挡已算好力量/虚弱/易伤加成，分析摸牌堆和弃牌堆，跨回合节奏规划 |
| **地图** | 展示所有分叉路线，推荐最优2-3条路径并标注优先级，考虑遗物加成 |
| **选牌** | 基于当前牌组构成和流派方向分析，不只看单卡强度 |
| **商店** | 购买优先级分析，结合金币预算和遗物效果 |
| **事件** | 每个选项利弊分析 |
| **休息** | 补血 vs 锻造决策，考虑遗物加成 |
| **卡组** | 按攻击/技能/能力分组，hover 显示类型、稀有度、完整描述 |

---

## Quick Start

```bash
# Slay the Spire 2 must be running with MCP API enabled
python3 -m overlay
```

---

## Knowledge System

Built on **full decompilation of the game's source code** — not wiki scraping, not guesswork. The entire game logic (card mechanics, monster AI patterns, relic interactions, power calculations) is extracted from the decompiled C# source, structured into queryable JSON databases, and fed into a multi-layered prompt system.

知识库基于**游戏源代码的完整反编译** — 不是wiki抄录，不是猜测。所有游戏逻辑（卡牌机制、怪物AI行为、遗物交互、增减益计算）都从反编译的C#源码中提取，结构化为可查询的JSON数据库，注入多层prompt系统。

### Data Pipeline

```
Game Source (decompiled C#, 3000+ classes)
        |
        v
  Structured Extraction
  |-- 569 cards         full mechanics: cost, type, rarity, keywords, effects
  |-- 289 relics        effects + scene context tags (combat/map/shop/rest/...)
  |-- 61 potions        effects + optimal usage timing
  |-- 111 monsters      AI behavior patterns, attack sequences, trigger conditions
  |-- 60 powers         buff/debuff calculation rules (multiplicative/additive/flag)
        |
        v
  Strategy Knowledge Base
  |-- archetype_matrix         per-character archetypes, tiered by ascension level
  |-- card_synergy_index       112 card combo patterns with trigger conditions
  |-- card_tier_list           card ratings contextualized per character + ascension
  |-- boss_counter_guide       boss-specific strategies and danger thresholds
  |-- event_guide              67 events with option analysis and edge cases
  |-- relic_pivot_rules        relic-triggered archetype transitions
  '-- monster_ai               attack pattern prediction for AI sequencing
```

### Multi-layer Prompt Construction

Each AI query is assembled from multiple context layers. Only relevant information is injected — the system doesn't dump everything, it queries what matters for the specific decision.

每次AI查询从多个上下文层组装。只注入相关信息 — 系统不会全量灌入，而是针对具体决策点查询所需内容。

**Layer 1 — Archetype Awareness**

The system matches the player's current relics against the archetype matrix, scores archetype viability by ascension tier, detects relic-triggered archetype pivots, and injects the top 2-3 viable archetypes with their core cards and win conditions.

```
[亡灵契约师 A0 流派参考]
  灵魂虚无流(S) 核心牌:虚空之唤、灰烬之灵、纠缠
    combo: 虚空之唤→每回合塞虚无牌+书页风暴/亡魂牵引消耗获取价值
  灾厄流(A) 核心牌:瘟疫、腐蚀之触、死亡之门
    遗物协同: 松动羊毛剪(削弱灾厄牌的虚无副作用)
```

**Layer 2 — Battlefield State Processing**

Every number the AI sees is pre-calculated. Strength, weakness, vulnerability, dexterity — all applied before the prompt is built. The AI doesn't need to do math.

```
Hand (all modifiers applied):
  [0] 出击  cost:1  base 8 → actual 6 dmg  (weakness: ×0.75)
  [3] 护卫  cost:1  [技能 基础] 召唤奥斯提（5HP）

Enemy (strength applied to attack intent):
  蜈蚣#2  HP:26/26  intent: 攻击 3×2 → actual 7×2=14 dmg  (str 4)
  status: 饥饿×4
```

**Layer 3 — Effect Semantics**

Raw buff names are meaningless to an LLM. The system looks up every active power, relic, and potion from the effects database and injects human-readable explanations of what they actually do in combat.

```
Battlefield effects:
  虚弱(1): 攻击伤害×0.75
  饥饿(4): 同伴死亡时获得力量但被击晕一回合（跳过攻击）
  为你而死: 主人受到未格挡伤害时此召唤物替主人承受，永久能力，可复活

Relic combat effects:
  赤牛: 每场战斗开始时获得活力（首次攻击额外伤害）
  松动羊毛剪: 每回合开始时移除手牌中1张状态/诅咒牌
```

**Layer 4 — Tactical Computation**

Lethal detection, kill estimation, shuffle prediction, draw pile probability — all computed before the LLM sees anything.

```
Tactical:
  危险：敌人总伤14，需格挡8点（否则掉到49HP）
  预估3回合击杀（本回合输出≈13，敌人剩26HP）
  摸牌堆仅3张，下回合将洗牌（弃牌堆5张回来）

Draw pile: 防御 打击 出击
Discard pile: 防御×2 护卫 打击
```

**Layer 5 — Scene-specific Context Filtering**

Each scene type gets a different slice of the knowledge base. The system doesn't dump everything — it queries what's relevant.

每个场景类型获取不同的知识切片。系统不会全量灌入，而是按场景查询相关内容。

| Scene | What gets injected |
|-------|-------------------|
| **Combat** | Active buffs/debuffs explained, relic combat effects, pre-calculated damage for hand + enemies, draw/discard pile contents, lethal detection, kill estimation, shuffle prediction |
| **Map** | Healing relics (e.g. Burning Blood: +6 HP per fight), elite incentive relics (e.g. Black Star: double elite relic drops), shop/rest/event relics, gold earning relics |
| **Card Reward** | Full deck composition, archetype direction, card synergy index lookup, tier rating for current character + ascension |
| **Shop** | Budget analysis, shop discount relics (e.g. Membership Card: 50% off), current deck gaps |
| **Rest** | Rest-specific relics (e.g. Dream Catcher: pick a card when resting, Peace Pipe: remove a card), HP percentage calculation, upgrade value analysis |
| **Event** | Event guide lookup from 67 pre-analyzed events, option-by-option risk/reward with edge cases |

All of this is **data-driven**. Adding a new card, power, or relic means editing a JSON file. No code changes.

全部**数据驱动**。添加新卡牌、效果或遗物只需编辑JSON文件，不改代码。

---

## Architecture

Layered building-block design. Bottom layers are reused by everything above.

```
  JSON Data               Edit to extend, no code changes
  Utilities               _get_power_amount / _has_power / _pile_summary
  Knowledge Lookup        _explain_powers / _explain_relics / _explain_potions
  Render Blocks           _render_card -> _render_card_grid -> _render_grouped_cards
  Scene Renderers         _display_combat / _display_map / _display_shop ...
  AI Analysis             _ai_combat / _ai_map / _ai_card / _ai_node
  Commander               State polling -> scene routing -> UI bridge
```

Design principles:
- **Single source of truth** — one `_render_card` for all card displays, one `_render_entity_block` for all entities
- **Data-driven** — buff/relic/potion effects live in JSON, AI queries what's relevant per scene
- **Zero duplication** — change one method, every scene updates automatically

---

## Project Structure

```
overlay/                    Core (11 modules, ~5000 lines)
  commander.py                Controller: polling, scene routing
  display.py                  Rendering: all UI building blocks
  ai_advisor.py               AI: strategy analysis, prompt construction
  data.py                     Data: saves, deck tracking
  history.py                  History: combat log, post-run review
  card_db.py                  Card database (single source, 569 cards)
  knowledge_db.py             Knowledge base loader
  llm_client.py               LLM interface
  constants.py                Constants, paths
  ui.html                     Frontend (pywebview)

data/                       Game data (extracted from source)
  cards/                      Card info (569 entries)
  relics/                     Relics (289), Potions (61)
  meta/                       Progress data

knowledge/                  Strategy knowledge base
  power_effects.json            60 buff/debuff mechanics
  relic_effects.json            289 relic effects with context tags
  potion_effects.json           61 potion effects
  archetype_matrix.json         Archetype strategies
  monster_ai.json               111 monster behavior patterns
  event_guide.json              67 event analyses
  boss_counter_guide.json       Boss counter strategies
  card_tier_list.json           Card ratings
  card_synergy_index.json       112 card combo patterns

tests/reference/            UI reference HTML (11 scenes)
```

---

## Extending

<details>
<summary><b>Add a new card</b></summary>

Edit `data/cards/card_tooltip_db.json`:

```json
"CardName": {
  "id": "CardId", "name_cn": "CardName",
  "cost": 1, "type": "attack", "rarity": "common",
  "keywords": "", "desc_cn": "Deal 10 damage."
}
```
</details>

<details>
<summary><b>Add a new buff/debuff</b></summary>

Edit `knowledge/power_effects.json`:

```json
"PowerId": {
  "name_cn": "PowerName", "type": "buff",
  "effect": "Gain 1 strength per turn"
}
```
</details>

<details>
<summary><b>Add a relic effect</b></summary>

Edit `knowledge/relic_effects.json` with context tags:

`combat` / `map_heal` / `map_elite` / `map_shop` / `map_rest` / `potion` / `card_reward`
</details>

