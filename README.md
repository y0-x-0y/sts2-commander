<h1 align="center">
  STS2 AI Advisor
  <br>
  <sub>Slay the Spire 2 — Real-time Strategy Overlay</sub>
</h1>

<p align="center">
  A real-time decision engine for Slay the Spire 2.
  <br>
  Reads game state via MCP API. Analyzes every decision point. Covers every scene.
</p>

<p align="center">
  杀戮尖塔2 实时AI策略顾问 — 通过 MCP API 读取游戏状态，覆盖全场景的策略分析浮窗。
</p>

---

## Features

| Scene | EN | 中文 |
|:------|:---|:-----|
| **Combat** | Play order with numbered badges, pre-calculated damage with all modifiers, draw/discard pile awareness, cross-turn planning | 出牌顺序标注，伤害已算好全部加成，分析牌堆，跨回合规划 |
| **Map** | All forking paths visualized, top routes ranked with priority badges, relic-aware scoring | 展示所有分叉路线，推荐最优路径，考虑遗物加成 |
| **Card Reward** | Selection based on deck composition and archetype direction | 基于牌组构成和流派方向分析选牌 |
| **Shop** | Purchase priority with budget and relic synergy | 购买优先级，结合预算和遗物效果 |
| **Event** | Pros/cons for every option | 每个选项利弊分析 |
| **Rest** | Heal vs upgrade with relic awareness | 补血/锻造决策，考虑遗物加成 |
| **Deck** | Grouped by type, hover for full info | 按类型分组，hover显示完整信息 |

---

## Setup

### Step 1 — Install the game mod

The overlay reads game state through a mod that runs a local API server. Download the mod files from [STS2 MCP](https://github.com/Gennadiyev/STS2MCP).

<details>
<summary><b>macOS</b></summary>

1. Open Steam, right-click **Slay the Spire 2** → Manage → Browse Local Files
2. Right-click `SlayTheSpire2.app` → Show Package Contents
3. Navigate to `Contents/MacOS/`
4. Create a folder called `mods` if it doesn't exist
5. Drop `STS2_MCP.dll` and `STS2_MCP.pck` into the `mods` folder
6. Launch the game — it will detect the mod and ask to restart in modded mode
</details>

<details>
<summary><b>Windows</b></summary>

1. Open Steam, right-click **Slay the Spire 2** → Manage → Browse Local Files
2. Create a folder called `mods` if it doesn't exist
3. Drop `STS2_MCP.dll` and `STS2_MCP.pck` into the `mods` folder
4. Launch the game — it will detect the mod and ask to restart in modded mode
</details>

> Modded and unmodded use separate save files. If you want to carry over your progress, copy your save folder before the first modded launch.

### Step 2 — Connect an LLM

The overlay uses a large language model for strategy analysis. Two connection methods are supported.

<details>
<summary><b>Option A — Claude CLI (recommended)</b></summary>

1. Install [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code)
2. Verify it works: `claude --help`
3. Edit `config.json`:

```json
{
  "api_url": "http://localhost:15526/api/v1/singleplayer",
  "llm_cli": "claude"
}
```

The CLI path is usually just `claude` if installed globally. If you installed it elsewhere, use the full path (e.g. `/usr/local/bin/claude`).
</details>

<details>
<summary><b>Option B — API key (Anthropic / OpenAI / any compatible provider)</b></summary>

1. Get an API key from your provider ([Anthropic](https://console.anthropic.com/), [OpenAI](https://platform.openai.com/), etc.)

2. Set the key as an environment variable (the key is never stored in any project file):

```bash
# macOS / Linux — add to ~/.zshrc or ~/.bashrc
export LLM_API_KEY="your-api-key-here"

# Windows — run in PowerShell
$env:LLM_API_KEY="your-api-key-here"
```

3. Edit `config.json` with your provider's endpoint:

```json
{
  "api_url": "http://localhost:15526/api/v1/singleplayer",
  "llm_api_base": "https://api.anthropic.com/v1",
  "llm_model": "claude-sonnet-4-20250514"
}
```

Other providers — just change the base URL and model name:

| Provider | `llm_api_base` | `llm_model` |
|----------|---------------|-------------|
| Anthropic | `https://api.anthropic.com/v1` | `claude-sonnet-4-20250514` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` |
| Local (Ollama) | `http://localhost:11434/v1` | `llama3` |
| Any OpenAI-compatible | your endpoint | your model |

</details>

### Step 3 — Launch

```bash
# Make sure the game is running with the mod active
python3 -m overlay
```

The overlay window will appear and automatically connect to the game.

---

## Knowledge System

Built from **full decompilation of the game source** — not wiki pages, not guesswork. The C# game logic is parsed, structured into queryable databases, and injected into a multi-layer prompt system that only sends what's relevant to each decision.

知识库基于**游戏源代码的完整反编译** — 不是wiki抄录。C#游戏逻辑被解析、结构化为可查询数据库，通过多层prompt系统按需注入。

### Source Extraction Pipeline

```
Decompiled C# (577 cards, 260 powers, 290 relics, 88 monsters, 68 events)
        |
        v  automated parsing
Structured JSON databases
  card_tooltip_db       569 cards — cost, type, rarity, mechanics tags, full description
                        + source field with extracted damage/block/keywords from C#
  power_effects         60 buff/debuff — compact hybrid descriptions from source logic
  relic_effects         289 relics — effects + scene context tags
  potion_effects        61 potions
  character_mechanics   per-character innate abilities (e.g. Necrobinder auto-summons Osty)
  monster_ai            111 monster behavior patterns
  source_extracted      raw extraction: numeric values, mechanic flags per card
        |
        v  context-filtered injection
AI Prompt (only relevant slice per scene)
```

### Multi-layer Prompt Architecture

The prompt isn't a flat text dump. It's assembled from 5 layers, each querying different knowledge bases. Only information relevant to the current decision point is injected.

Prompt不是平铺文本。它从5层知识库按需组装，每层只注入与当前决策相关的信息。

**Layer 1 — Character + Archetype**

Matches player's relics against the archetype matrix. Scores viability by ascension tier. Detects relic-triggered pivots. Injects top viable archetypes with core cards and combos.

匹配遗物→流派矩阵，按进阶分级评分，检测遗物触发的流派转型，注入可行流派+核心牌+combo。

```
[亡灵契约师 A0 流派参考]
  灵魂虚无流(S) 核心牌:虚空之唤、灰烬之灵、纠缠
    combo: 虚空之唤→每回合塞虚无牌+书页风暴消耗获取价值
  灾厄流(A) 核心牌:瘟疫、死亡之门
角色机制：每场自动带奥斯提(独立友方)。为你而死:重定向未格挡攻击→奥斯提(per hit)
```

**Layer 2 — Pre-calculated Combat State**

Every number the AI sees is already computed. Strength, weakness, vulnerability applied to both hand cards and enemy intents. No math required from the LLM.

AI看到的每个数值都已预算完毕。力量/虚弱/易伤已应用到手牌和敌人意图。LLM不需要做数学。

```
Hand:
  [0]✓ 抓取 1费 7伤 [保留/Osty攻击] [攻击] 奥斯提造成7点伤害 →实际5伤
  [2]✓ 防御 1费 5挡 [技能] 获得5点格挡 →实际5挡

Enemy:
  蜈蚣#2  攻击 3×2 →实际7×2=14伤  (str 4 applied)
```

**Layer 3 — Effect Semantics (from source code)**

Every active buff/debuff is looked up in the power effects database (built from decompiled C#) and explained in compact hybrid format. The AI knows exactly what each effect does mechanically, not just its name.

每个活跃buff/debuff从源码提取的效果数据库中查询，用紧凑hybrid格式解释。AI知道每个效果的精确机制。

```
力量(4): 攻击牌+N伤
饥饿(4): 同伴死→+力量+击晕1回合
为你而死: 重定向未格挡攻击→自身(per hit)。死后停止但可复活。多段攻击只挡当前hit
```

**Layer 4 — Tactical Computation**

Lethal check, kill estimation, shuffle prediction, draw pile contents — all computed before the prompt is built.

致命检测、击杀预估、洗牌预判、牌堆内容 — 全部在prompt构建前计算完毕。

```
危险：敌人总伤14，需格挡8点
预估3回合击杀（本回合≈13，敌人剩26HP）
摸牌堆(3张): 防御 打击 出击
```

**Layer 5 — Scene-filtered Knowledge**

Relics, potions, and character mechanics are tagged with context labels. Each scene type gets only its relevant slice.

遗物、药水、角色机制按场景标签过滤。每个场景只获取相关切片。

| Scene | Injected context |
|-------|-----------------|
| Combat | Active buffs explained, relic combat effects, pre-calc damage, draw/discard pile, lethal/kill/shuffle |
| Map | Healing/elite/shop/rest/gold relic bonuses |
| Card Reward | Full deck list, archetype direction, character mechanics |
| Shop | Budget, discount relics, deck gaps |
| Rest | Rest-specific relics, HP%, upgrade value |
| Event | 67 pre-analyzed events, option-by-option risk/reward |

Everything is **data-driven**. New cards, powers, relics = edit JSON. Zero code changes.

---

## Project Structure

```
overlay/                    Core (11 modules)
  ai_advisor_app.py           Controller — polling, scene routing, UI bridge
  display.py                  Rendering — atomic building blocks, layered composition
  ai_advisor.py               AI — multi-layer prompt construction, knowledge injection
  data.py                     Data — saves, deck tracking, card collection
  history.py                  History — combat log, post-run review
  card_db.py                  Card DB — single source (569 cards from decompiled source)
  knowledge_db.py             Strategy KB loader
  llm_client.py               LLM interface
  constants.py                Constants, paths
  ui.html                     Frontend (pywebview)

data/                       Game data (extracted from source)
  cards/                      569 cards with source-extracted fields
  relics/                     289 relics, 61 potions
  meta/                       Progress

knowledge/                  Strategy + effects (all JSON, data-driven)
  source_extracted.json         Raw C# extraction (554 cards, 260 powers, 290 relics)
  power_effects.json            60 buff/debuff — compact hybrid from source
  relic_effects.json            289 relics — effects + scene context tags
  potion_effects.json           61 potions
  character_mechanics.json      Per-character innate abilities
  archetype_matrix.json         Archetype strategies per character
  monster_ai.json               111 monster behavior patterns
  event_guide.json              67 event analyses
  boss_counter_guide.json       Boss strategies
  card_tier_list.json           Card ratings
  card_synergy_index.json       112 card combos

tests/reference/            UI reference HTML (11 scenes)
```

### Layered Rendering Architecture

```
JSON Data           → edit to extend
Utilities           → _get_power_amount / _has_power / _pile_summary
Knowledge Lookup    → _explain_powers / _explain_relics / _explain_potions / _get_char_mechanic
Card Prompt         → _card_prompt_line (unified: combat + reward + shop)
Render Blocks       → _render_card → _render_card_grid → _render_grouped_cards
Scene Renderers     → _display_combat / _display_map / _display_shop ...
AI Analysis         → _ai_combat / _ai_map / _ai_card / _ai_node
AI Advisor          → State polling → scene routing → UI bridge
```

Single `_render_card` for all card displays. Single `_card_prompt_line` for all AI prompts. Single `_render_entity_block` for all entities. Change one method, every scene updates.

---

## Extending

<details>
<summary><b>Add a card</b></summary>

`data/cards/card_tooltip_db.json`:
```json
"CardName": {"id":"Id","name_cn":"CardName","cost":1,"type":"attack","rarity":"common","desc_cn":"Deal 10 damage."}
```
</details>

<details>
<summary><b>Add a buff/debuff</b></summary>

`knowledge/power_effects.json`:
```json
"PowerId": {"name_cn":"Name","type":"buff","effect":"攻击牌+N伤"}
```
</details>

<details>
<summary><b>Add a relic</b></summary>

`knowledge/relic_effects.json` — set `context` tags:
`combat` / `map_heal` / `map_elite` / `map_shop` / `map_rest` / `potion` / `card_reward`
</details>

<details>
<summary><b>Add a character</b></summary>

`knowledge/character_mechanics.json`:
```json
"CharName": {"innate":"...","resources":"...","note":"..."}
```
</details>
