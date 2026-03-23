"""GameState — 游戏状态的单一数据源。

集中管理所有 self.last_* 散落属性，提供清晰的读写接口。
其他模块通过 self.gs 访问，不再直接读写 last_state / last_player 等。
"""


class CombatState:
    """当前战斗的临时状态。"""
    __slots__ = ("start_hp", "start_floor", "rounds", "log")

    def __init__(self):
        self.start_hp = 0
        self.start_floor = 0
        self.rounds = 0
        self.log = []       # 每回合快照

    def reset(self):
        self.start_hp = 0
        self.start_floor = 0
        self.rounds = 0
        self.log.clear()


class DeckState:
    """本局牌组变动追踪。"""
    __slots__ = ("acquired", "removed", "archetype", "analysis_text")

    def __init__(self):
        self.acquired = []
        self.removed = []
        self.archetype = ""
        self.analysis_text = ""

    def reset(self):
        self.acquired.clear()
        self.removed.clear()
        self.archetype = ""
        self.analysis_text = ""


class GameState:
    """集中管理游戏状态，替代散落在 self 上的 last_* 属性。

    用法：
        self.gs = GameState()
        self.gs.update(api_state)     # 轮询时更新
        self.gs.player                # 等价于旧 self.last_player
        self.gs.run                   # 等价于旧 self.last_run
        self.gs.combat.start_hp       # 等价于旧 self._combat_start_hp
        self.gs.deck.acquired         # 等价于旧 self.deck_acquired
    """

    def __init__(self):
        # ── 原始 API 状态 ──
        self.raw = None          # last_state
        self.state_type = None   # last_type
        self.round = -1          # last_round

        # ── 解析后的快捷引用 ──
        self.player = {}         # last_player
        self.run = {}            # last_run

        # ── 子状态 ──
        self.combat = CombatState()
        self.deck = DeckState()

        # ── 连接/分析 ──
        self.first_connect = True
        self.card_analyzed = False
        self.prev_floor = 0
        self.fail_count = 0
        self.analyze_state_type = None   # 用于 stale 检测

    def update(self, state: dict):
        """用最新 API 响应更新状态。"""
        self.raw = state
        self.state_type = state.get("state_type") or state.get("type")

        # 提取 player（兼容不同 API 结构）
        p = state.get("battle", {}).get("player") or state.get("player") or {}
        if p:
            self.player = p

        # 提取 run
        r = state.get("run") or {}
        if r:
            self.run = r

    def get_player(self, state: dict = None) -> dict:
        """从指定 state 或缓存获取 player dict。"""
        s = state or self.raw or {}
        return (s.get("battle", {}).get("player")
                or s.get("player")
                or self.player
                or {})

    @property
    def character(self) -> str:
        return self.player.get("character", "")

    @property
    def hp(self) -> int:
        return self.player.get("hp", 0)

    @property
    def max_hp(self) -> int:
        return self.player.get("max_hp", 0)

    @property
    def floor(self) -> int:
        return self.run.get("floor", 0)

    @property
    def act(self) -> int:
        return self.run.get("act", 0)

    @property
    def ascension(self) -> int:
        return self.run.get("ascension", 0)

    @property
    def gold(self) -> int:
        return self.player.get("gold", 0)

    def new_run(self):
        """重置本局状态（新局开始时调用）。"""
        self.combat.reset()
        self.deck.reset()
        self.round = -1
        self.card_analyzed = False
        self.prev_floor = 0
