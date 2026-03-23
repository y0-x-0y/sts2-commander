#!/usr/bin/env python3
"""
STS2 常量与配置 — 从 ai_advisor_app.py 提取的所有顶层定义
"""

import os
import json
import shutil
import platform as _platform

# ───── 路径自动检测（基于脚本位置）─────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)

def _proj(*parts):
    """相对于项目根目录构建路径"""
    return os.path.join(_PROJECT_DIR, *parts)

# 读取config.json（如果有）
_CONFIG = {}
_config_path = _proj("config.json")
if os.path.exists(_config_path):
    try:
        with open(_config_path) as f:
            _CONFIG = json.load(f)
    except: pass

# ───── 配置（可通过config.json覆盖）─────
API_URL      = _CONFIG.get("api_url", "http://localhost:15526/api/v1/singleplayer")
LLM_CLI      = _CONFIG.get("llm_cli") or shutil.which("claude") or "claude"
POLL_SECS    = _CONFIG.get("poll_interval_seconds", 0.8)

# 数据文件
CARD_DB_FILE   = _proj("runtime", "runtime_collected.json")
EPOCHS_FILE    = _proj("data", "meta", "epochs.json")

# 知识库文件
ARCHETYPES_FILE = _proj("knowledge", "archetype_matrix.json")
MONSTER_AI_FILE = _proj("knowledge", "monster_ai.json")
EVENT_GUIDE_FILE = _proj("knowledge", "event_guide.json")
CARD_TIER_FILE  = _proj("knowledge", "card_tier_list.json")
MATRIX_FILE     = _proj("knowledge", "archetype_matrix.json")
SYNERGY_FILE    = _proj("knowledge", "card_synergy_index.json")
PIVOT_FILE      = _proj("knowledge", "relic_pivot_rules.json")
BOSS_FILE       = _proj("knowledge", "boss_counter_guide.json")

# 运行时文件
HISTORY_FILE   = _proj("runtime", "run_history.json")
SESSION_FILE   = _proj("runtime", "session.json")

# 存档路径自动检测
def _find_save_base():
    """自动检测STS2存档路径"""
    system = _platform.system()
    if system == "Darwin":
        base = os.path.expanduser("~/Library/Application Support/SlayTheSpire2/steam")
    elif system == "Windows":
        base = os.path.join(os.environ.get("APPDATA", ""), "SlayTheSpire2", "steam")
    else:  # Linux
        base = os.path.expanduser("~/.local/share/SlayTheSpire2/steam")

    if os.path.exists(base):
        for d in os.listdir(base):
            if d.isdigit() and os.path.isdir(os.path.join(base, d)):
                return os.path.join(base, d)
    return None

_SAVE_BASE = _find_save_base() or ""
if _SAVE_BASE:
    PROGRESS_FILE_MOD = os.path.join(_SAVE_BASE, "modded/profile1/saves/progress.save")
    PROGRESS_FILE_VANILLA = os.path.join(_SAVE_BASE, "profile1/saves/progress.save")
    PROGRESS_FILE = PROGRESS_FILE_MOD if os.path.exists(PROGRESS_FILE_MOD) else PROGRESS_FILE_VANILLA
else:
    PROGRESS_FILE = ""

# ───── Power / Buff / Debuff 中文名 ─────
POWER_CN = {
    "Strength": "力量", "Dexterity": "敏捷", "Weak": "虚弱",
    "Vulnerable": "易伤", "Frail": "脆弱", "Poison": "中毒",
    "Thorns": "荆棘", "Metallicize": "金属化", "Artifact": "神器",
    "Intangible": "无实体", "Ritual": "仪式", "Rage": "暴怒",
    "Plated Armor": "层叠铠甲", "Barricade": "铁壁", "Demon Form": "恶魔形态",
    "Noxious Fumes": "恶毒", "Envenom": "淬毒", "Accuracy": "精准",
    "After Image": "残影", "A Thousand Cuts": "千刀万剐",
    "Well-Laid Plans": "冥想", "Pen Nib": "笔尖", "Buffer": "缓冲",
    "Focus": "专注", "Loop": "循环", "Electro": "电磁",
    "Heatsink": "散热器", "Defragment": "碎片整理", "Creative AI": "创意AI",
    "Echo Form": "回音", "Static Discharge": "静电释放", "Storm": "风暴",
    "MinionPower": "随从", "Block": "格挡", "Vigor": "活力",
    "Mantra": "真言", "Divinity": "超凡", "Combust": "自燃",
    "DarkEmbrace": "暗之拥抱", "Evolve": "进化", "FeelNoPain": "无痛",
    "FireBreathing": "吐火", "Rupture": "裂伤", "Brutality": "残暴",
    "Corruption": "腐化", "Juggernaut": "势不可挡", "Berserk": "狂暴",
    "Regeneration": "再生", "Entangled": "缠绕", "No Draw": "禁止抽牌",
    "Draw Reduction": "抽牌减少", "Choked": "窒息", "Constricted": "收缩",
    "Hex": "诅咒", "Lock On": "锁定", "Nightmare": "噩梦",
    "Confusion": "困惑", "Blasphemer": "亵渎者", "Corpse Explosion": "尸爆",
    "Fading": "消逝", "Invincible": "无敌", "Sharp Hide": "尖锐皮肤",
    "Reactive": "反击", "Angry": "愤怒", "Curl Up": "蜷缩",
    "Spore Cloud": "孢子云", "Time Warp": "时间扭曲", "Shifting": "变换",
    "Flight": "飞行", "Explosive": "爆炸", "DoubleDamage": "双倍伤害",
    # 额外常见
    "Inflame": "点燃", "Shrug It Off": "坚毅", "Warcry": "战吼",
    "Limit Break": "极限突破", "Heavy Blade": "重刃", "Offering": "供奉",
    "Blur": "模糊", "Backflip": "后空翻", "Footwork": "步法",
    "Catalyst": "催化剂", "Predator": "掠食者", "Finesse": "精妙",
    "Cold Snap": "冷冻一击", "Glacier": "冰川", "Coolheaded": "理性",
    "Ball Lightning": "球形闪电", "Biased Cognition": "偏置认知",
    "Consume": "吞噬", "Hologram": "全息图", "Skim": "略读",
    "Compile Driver": "编译驱动", "Sunder": "裂解", "White Noise": "白噪声",
    "Darkness": "黑暗", "Rainbow": "彩虹",
}

# ───── 遗物中文名 ─────
RELIC_CN = {
    "Burning Blood": "燃烧之血", "Ring of the Snake": "蛇环", "Cracked Core": "碎裂核心",
    "Pure Water": "纯净之水", "Akabeko": "赤牛", "Anchor": "铁锚",
    "Ancient Tea Set": "古代茶具", "Art of War": "孙子兵法",
    "Bag of Marbles": "弹珠袋", "Bag of Preparation": "准备袋",
    "Blood Vial": "血药瓶", "Bronze Scales": "铜鳞甲",
    "Centennial Puzzle": "百年谜题", "Ceramic Fish": "陶瓷鱼",
    "Cloak Clasp": "披风扣", "Dream Catcher": "捕梦网",
    "Ectoplasm": "外质", "Eternal Feather": "永恒之羽",
    "Fossilized Helix": "化石螺旋", "Gambling Chip": "赌筹",
    "Ginger": "生姜", "Girya": "铁壶铃", "Green Louse": "绿虱",
    "Happy Flower": "快乐花", "Hornclad": "角甲", "Hovering Kite": "飞风筝",
    "Ice Cream": "冰淇淋", "Incense Burner": "香炉",
    "Juzu Bracelet": "念珠手链", "Lantern": "灯笼",
    "Lees": "酒糟", "Letter Opener": "拆信刀", "Magical Flower": "魔法花",
    "Mango": "芒果", "Mark of Pain": "痛苦印记",
    "Mercury Hourglass": "水银沙漏", "Molten Egg": "熔融蛋",
    "Meat on the Bone": "骨上之肉", "Nunchaku": "双截棍",
    "Oddly Smooth Stone": "奇怪光石", "Omamori": "御守",
    "Orichalcum": "山铜", "Ornamental Fan": "折扇",
    "Paper Frog": "纸蛙", "Paper Krane": "纸鹤",
    "Pear": "梨子", "Pen Nib": "笔尖", "Phantasmal Killer": "幻影杀手",
    "Preserved Insect": "保存的昆虫", "Potion Belt": "药水腰带",
    "Prayer Wheel": "祈祷轮", "Shovel": "铲子",
    "Singing Bowl": "颂钵", "Smiling Mask": "笑脸面具",
    "Snake Ring": "蛇环", "Snecko Eye": "蛇眼", "Snecko Skull": "蛇颅",
    "Sozu": "苦无", "Spirit Poop": "精灵便便", "Strawberry": "草莓",
    "Strike Dummy": "攻击靶", "Sundial": "日晷",
    "Symbiotic Virus": "共生病毒", "The Specimen": "标本",
    "Thread and Needle": "针线", "Tingsha": "铃铛",
    "Toxic Egg": "毒蛋", "Toy Ornithopter": "玩具扑翼机",
    "Tungsten Rod": "钨棒", "Turnip": "萝卜",
    "Twisted Funnel": "扭曲漏斗", "Unceasing Top": "不停的陀螺",
    "Vajra": "金刚杵", "War Paint": "战争涂料", "Whetstone": "磨刀石",
    "White Beast Statue": "白兽雕像", "Bird-Faced Urn": "鸟脸瓮",
    "Black Star": "黑星", "Boss's Crown": "首领皇冠",
    "Busted Crown": "破损皇冠", "Calling Bell": "召唤之铃",
    "Champion Belt": "冠军腰带", "Charons Ashes": "卡戎之灰",
    "Cloak And Dagger": "斗篷与匕首", "Coffee Dripper": "咖啡滴漏",
    "Courier": "信使", "Dead Branch": "枯枝", "Du Vu Doll": "巫毒娃娃",
    "Ectoplasm": "外质", "Empty Cage": "空笼", "Enchiridion": "手册",
    "Eternal Feather": "永恒之羽", "Face Of Cleric": "僧侣之面",
    "Frozen Core": "冰冻核心", "Fusion Hammer": "聚变锤",
    "Gambling Chip": "赌筹", "Gremlin Horn": "格雷姆林号角",
    "Holy Water": "圣水", "Horn Cleat": "角形锚耳",
    "Inserter": "插入器", "Lizard Tail": "蜥蜴尾巴",
    "Magic Flower": "魔法花", "Maw Bank": "血盆大口银行",
    "Medical Kit": "急救箱", "Membership Card": "会员卡",
    "Melange": "混合物", "Mutagenic Strength": "变异力量",
    "Necronomicon": "死灵之书", "Nilrys Codex": "奈尔瑞典籍",
    "Nloth's Gift": "恩洛斯的礼物", "Odd Mushroom": "奇怪蘑菇",
    "Orange Pellets": "橙色颗粒", "Orrery": "太阳系仪",
    "Pandoras Box": "潘多拉魔盒", "Pantograph": "缩放仪",
    "Peace Pipe": "和平烟斗", "Pocketwatch": "怀表",
    "Portrait from Jekyll": "杰基尔的画像", "Preserved Insect": "保存的昆虫",
    "Prismatic Shard": "棱镜碎片", "Red Skull": "红色骷髅",
    "Ring of the Serpent": "蛇戒指", "Runic Cube": "符文方块",
    "Runic Dome": "符文圆顶", "Runic Pyramid": "符文金字塔",
    "Sacred Bark": "神圣树皮", "Self Forming Clay": "自成形泥",
    "Shuriken": "手里剑", "Slavers Collar": "奴隶项圈",
    "Sling": "弹弓", "Slaving Collar": "奴役项圈",
    "Smiling Mask": "笑面面具", "Snecko Eye": "蛇眼",
    "Sozu": "苦无", "Spiker": "刺针",
    "Stone Calendar": "石历", "Strange Spoon": "奇怪的勺子",
    "The Abacus": "算盘", "The Boot": "靴子",
    "The Courier": "信使", "Thread and Needle": "针线",
    "Torii": "鸟居", "Tough Bandages": "坚韧绷带",
    "Toxic Egg": "毒蛋", "Unceasing Top": "不停的陀螺",
    "Velvet Choker": "丝绒项圈", "Violet Lotus": "紫莲",
    "Void": "虚空", "War Paint": "战争涂料", "Whetstone": "磨刀石",
    "Wrist Blade": "腕刃",
}

# ───── 药水中文名 ─────
POTION_CN = {
    "Blood Potion": "血量药水", "Elixir Potion": "灵药",
    "Heart of Iron": "铁心", "Fire Potion": "火焰药水",
    "Colorless Potion": "无色药水", "Block Potion": "格挡药水",
    "Dexterity Potion": "敏捷药水", "Energy Potion": "能量药水",
    "Explosive Potion": "爆炸药水", "Fear Potion": "恐惧药水",
    "Flex Potion": "爆发药水", "Frost Potion": "冰霜药水",
    "Ghost In A Jar": "瓶中幽灵", "Liquid Bronze": "液态青铜",
    "Liquid Memories": "液态记忆", "Poison Potion": "毒药药水",
    "Power Potion": "能力药水", "Regen Potion": "再生药水",
    "Skill Potion": "技能药水", "Speed Potion": "速度药水",
    "Strength Potion": "力量药水", "Swift Potion": "迅捷药水",
    "Weak Potion": "虚弱药水", "Ancient Potion": "古代药水",
    "Attack Potion": "攻击药水", "Blessing of the Forge": "锻造祝福",
    "Bottled Miracle": "瓶装奇迹", "Cultist Potion": "邪教药水",
    "Distilled Chaos": "蒸馏混沌", "Duplication Potion": "复制药水",
    "Elusive Potion": "难以捉摸的药水", "Essence of Darkness": "黑暗精华",
    "Essence of Steel": "钢铁精华", "Ethereal Potion": "虚空药水",
    "Fairy In A Bottle": "瓶中仙女", "Gambler's Brew": "赌徒酿造",
    "Heart of Iron": "铁心药水", "Lens-Maker's Elixir": "镜片师灵药",
    "Liquid Memories": "液态记忆", "Megalith Elixir": "巨石灵药",
    "Mystical Water": "神秘之水", "Poison Potion": "毒药药水",
    "Smoke Bomb": "烟雾弹", "Snecko Oil": "蛇油",
    "Stance Potion": "姿态药水", "Tiger King Potion": "虎王药水",
    "Tome of the Mind": "思维之书", "Void Potion": "虚空药水",
    "Voltcatch": "电捕手", "Wind Potion": "风之药水",
}

def _cn_power(p):
    """翻译一个 power dict 的名字为中文。"""
    name = p.get("name", "")
    pid  = p.get("id", name)
    return POWER_CN.get(name) or POWER_CN.get(pid) or name

_RELIC_DATA_CACHE = None
def _cn_relic(name):
    r = RELIC_CN.get(name)
    if r:
        return r
    # 从数据文件查找
    global _RELIC_DATA_CACHE
    if _RELIC_DATA_CACHE is None:
        try:
            with open(RELIC_DATA_FILE) as f:
                _RELIC_DATA_CACHE = json.load(f)
        except Exception:
            _RELIC_DATA_CACHE = {}
    entry = _RELIC_DATA_CACHE.get(name, {})
    cn = entry.get("name_cn")
    if cn:
        RELIC_CN[name] = cn  # 缓存
        return cn
    return name

_POTION_DATA_CACHE = None
def _cn_potion(name):
    r = POTION_CN.get(name)
    if r:
        return r
    global _POTION_DATA_CACHE
    if _POTION_DATA_CACHE is None:
        try:
            with open(POTION_DATA_FILE) as f:
                _POTION_DATA_CACHE = json.load(f)
        except Exception:
            _POTION_DATA_CACHE = {}
    entry = _POTION_DATA_CACHE.get(name, {})
    cn = entry.get("name_cn")
    if cn:
        POTION_CN[name] = cn
        return cn
    return name

# ───── 意图翻译 ─────
INTENT_CN = {
    # 攻击类
    "Attack":            "攻击",
    "AttackBuff":        "攻击+自强",
    "AttackDefend":      "攻击+防御",
    "AttackDebuff":      "攻击+施弱",
    "HeavyAttack":       "重击",
    # 防御类
    "Defend":            "防御",
    "DefendBuff":        "防御+增益",
    # 增益类
    "Buff":              "强化自身",
    "BuffDebuff":        "强化并施弱",
    # 减益类
    "Debuff":            "施加减益",
    "DebuffStrong":      "施加强力减益（弱化/易伤）",
    # 特殊
    "Escape":            "逃跑",
    "Sleep":             "休眠",
    "Stun":              "被晕眩",
    "Unknown":           "意图不明",
    "None":              "—",
    "Summon":            "召唤增援",
    "Spawn":             "生成小怪",
    "Magic":             "魔法攻击",
    "Charging":          "蓄力",
    "Cowardly":          "懦缩",
    "Spore":             "孢子",
    "StatusCard":        "塞状态牌",
    "CurseCard":         "塞诅咒牌",
    "CardDebuff":        "污染手牌",
    "Ritual":            "仪式",
    "Split":             "分裂",
}

# ───── 常用牌功能字典 ─────
CARD_DICT = {
    "打击": "6伤害", "防御": "获5格挡", "中和": "0费·3伤+1弱",
    "幸存者": "获8格挡+弃1牌", "毒刺": "2伤+2毒", "飞刀": "3×1伤·消耗",
    "连击": "连打直到2费用完", "冲刺": "10伤+10格挡", "毒雾": "全场+3毒",
    "预判": "0费·获3敏捷", "尖啸": "全敌-3力量·消耗", "闪避": "4格挡+摸1",
    "毒刃": "5伤·追毒伤", "暗器": "0费·弃牌造成等量伤害", "恶毒": "被动·每回合+1毒",
    "缠绕": "施1虚弱", "集中": "0费·+2敏捷", "烟雾炸弹": "全敌1虚弱·消耗",
    "引诱": "下次受击后格挡等量", "幽灵形态": "无敌1回合", "感知": "摸3弃2",
    "冥想": "保留1牌到下回合", "完美技巧": "摸1张0费牌", "蛇眼": "弃牌摸牌",
    "回音": "每回合第一张牌额外打一次", "死神": "每3毒叠加翻倍",
    "蛇形一击": "6伤+弃1摸1", "无限刀": "循环机制牌",
}

# ───── 策略知识库（按角色）─────
# ───── 旧版策略注入（legacy fallback，新架构用 _build_context 查表）─────
STRATEGY_DB = {
    "静默猎手": {
        "combat": """静默猎手出牌要点：
1. 0费牌优先（中和、预判、逃跑计划）——不浪费能量
2. 施虚弱减伤25%，施易伤增伤50%——优先控制
3. 毒流：堆毒 + 高格挡撑到毒发，Accelerant加速毒伤
4. 飞刀流：Accuracy(+4伤/刀)+Infinite Blades+Knife Trap终极杀招
5. 多敌人时：毒雾/恶毒/Fan of Knives全体输出
6. 防御配套：Blur(格挡保留)+Backflip(格挡+抽)+Mirage(格挡=毒量)""",

        "card_select": """静默猎手选牌优先级：
毒流核心：恶毒(Noxious Fumes)>催化剂(Accelerant)>腐蚀波(Corrosive Wave)>蛇咬>致死毒药>泡泡泡
飞刀流核心：精准(Accuracy)>无限飞刃(Infinite Blades)>飞刀陷阱(Knife Trap)>袖中利刃>墨刃(Blade of Ink)>刀扇
防御：模糊(Blur)>扫腿(Legsweep)>后空翻(Backflip)>逃跑计划>残影(Afterimage)
抽牌：准备(Prepared)>感知>暗器
删牌优先：基础打击>基础防御
牌组25-35张最佳。不要什么都拿，聚焦一个流派。""",

        "map": """静默猎手路线规划：
第1幕：优先普通怪攒牌+钱，HP>60%可打精英
第2幕：走精英拿遗物（手里剑/苦无对飞刀流极强），商店删基础牌
第3幕：精准构建，Boss前休息升级关键牌
飞刀流关键遗物：手里剑(3攻+1力)/苦无(3攻+1敏)/笔尖(第10攻翻倍)
毒流关键遗物：纸蛙(易伤+75%伤)/红头骨(HP<50%+3力量)""",
    },

    "铁甲战士": {
        "combat": """铁甲战士出牌要点：
1. 力量对多段攻击效果最好——每一击+力量值伤害
2. Body Slam流：堆格挡→Body Slam输出，Barricade保留格挡跨回合
3. 猛击(Bash)施易伤→后续攻击+50%伤害
4. Burning Blood每场回6HP，可以激进交换血量
5. 消耗流：Fiend Fire消耗手牌每张造伤，Feel No Pain每消耗+格挡""",

        "card_select": """铁甲战士选牌优先级：
Body Slam流：Body Slam>Barricade>Juggernaut>格挡牌(Shrug It Off/True Grit)
力量流：Demon Form>Heavy Blade>Limit Break>Inflame
消耗流：Fiend Fire>Feel No Pain>Corruption
通用强牌：Offering(抽3+2能量)>Battle Trance>Shrug It Off
升级优先：Body Slam(变0费)>Offering>Demon Form""",

        "map": """铁甲战士路线规划：
Burning Blood回血能力允许更激进路线
优先打精英拿遗物，血量可承受更多战斗
第1幕确定流派方向（Body Slam还是力量）
商店删基础打击牌""",
    },

    "缺陷体": {
        "combat": """缺陷体出牌要点：
1. 充能球管理：闪电=被动伤害，冰霜=被动格挡，黑暗=蓄力，等离子=能量
2. Focus(专注力)增强所有球的被动和唤出效果
3. Dualcast唤出最右球两次——黑暗球蓄够力再唤出最强
4. 球槽位有限，新球会把最左的挤出去（触发唤出效果）""",

        "card_select": """缺陷体选牌优先级：
闪电流：Ball Lightning>Electrodynamics>Storm>Tempest
冰霜流：Glacier>Coolheaded>Cold Snap>Buffer
通用：Defragment(+1 Focus)>Consume>Biased Cognition(+4 Focus但每回合-1)
抽牌：Hologram>Skim>Compile""",

        "map": "缺陷体路线：专注力和球是核心，早期找Defragment/Glacier。中期开始挑战精英。",
    },
}

# 通用战斗策略
COMBAT_BASICS = """通用出牌原则：
1. 看意图→大伤害先防御，能击杀优先击杀减少受伤
2. 0费牌先打→不浪费能量
3. 虚弱减敌方攻击25%，易伤增我方伤害50%
4. 药水别存着——Boss/精英战大方使用"""

# ───── 皇室紫配色 ─────
BG        = "#0a0610"
PANEL     = "#15102a"
CARD      = "#1c1535"
BORDER    = "#3d2d60"
GOLD      = "#d4a840"
GOLD_DIM  = "#a89ab8"
PARCH     = "#ddd0e8"
PARCH_DIM = "#a89ab8"
RED       = "#e74c3c"
GREEN     = "#45c480"
BLUE      = "#5dade2"
SHADOW    = "#080510"

