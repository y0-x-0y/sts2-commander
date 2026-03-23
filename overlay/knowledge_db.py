"""KnowledgeDB — 策略知识库加载器。

集中加载所有策略知识库JSON文件，提供查询接口。
"""

import json
import os
from overlay.constants import (
    ARCHETYPES_FILE, MONSTER_AI_FILE, EVENT_GUIDE_FILE,
    CARD_TIER_FILE, MATRIX_FILE, SYNERGY_FILE, PIVOT_FILE, BOSS_FILE,
)


class KnowledgeDB:
    """策略知识库 — 启动时加载一次，运行时只读。"""

    def __init__(self):
        self.matrix = self._load(MATRIX_FILE, {})
        self.boss_guide = self._load(BOSS_FILE, {})
        self.monster_ai = self._load(MONSTER_AI_FILE, {})
        self.event_guide = self._load(EVENT_GUIDE_FILE, {})
        self.card_tiers = self._load(CARD_TIER_FILE, {})
        self.synergy_index = self._load(SYNERGY_FILE, {})
        self.pivot_rules = self._load(PIVOT_FILE, {})
        self.archetypes = self._load(ARCHETYPES_FILE, {})

        loaded = sum(1 for v in [
            self.matrix, self.boss_guide, self.monster_ai,
            self.event_guide, self.card_tiers, self.synergy_index, self.pivot_rules,
        ] if v)
        print(f"[KnowledgeDB] Loaded {loaded}/7 knowledge bases")

    def get_char_archetypes(self, character: str) -> dict:
        char_data = self.matrix.get("characters", {}).get(character, {})
        return char_data.get("archetypes", {})

    def get_boss_info(self, boss_name: str) -> dict:
        return self.boss_guide.get(boss_name, {})

    def get_monster_behavior(self, monster_name: str) -> dict:
        return self.monster_ai.get(monster_name, {})

    def get_event_guide(self, event_name: str) -> dict:
        return self.event_guide.get(event_name, {})

    def get_card_synergies(self, card_name: str) -> dict:
        return self.synergy_index.get(card_name, {})

    def get_card_tier(self, character: str, card_name: str) -> str:
        return self.card_tiers.get(character, {}).get(card_name, "")

    @staticmethod
    def _load(path, default=None):
        try:
            if path and os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
        except Exception as e:
            print(f"[KnowledgeDB] Failed to load {path}: {e}")
        return default if default is not None else {}
