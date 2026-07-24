"""游戏状态: 纯数据树, 可完整 JSON 序列化.

不可变约定: 所有 dataclass frozen; 嵌套 dict(buildings)修改前整体复制,
由 tests/engine/test_apply.py 的不可变性测试守护.
"""

import hashlib
import json
from dataclasses import dataclass, field, replace

from tta.engine.constants import ROW_SLOTS
from tta.engine.enums import Age


@dataclass(frozen=True)
class PlayerState:
    """单个玩家状态.

    buildings: {BuildingType.value: {card_id: 工人数}}.
    developed: 已研发(置于场上)的建筑/兵种卡 id, 可重复(每张即一个建筑槽).
    """

    name: str
    culture: int = 0
    science: int = 0
    materials: int = 0
    food: int = 0
    yellow_bank: int = 0
    worker_pool: int = 0
    buildings: dict[str, dict[str, int]] = field(default_factory=dict)
    developed: tuple[str, ...] = ()
    hand_civil: tuple[str, ...] = ()
    government: str = ""
    civil_actions: int = 0
    military_actions: int = 0


@dataclass(frozen=True)
class GameState:
    """整局状态. card_row 中 None 表示空格; civil_deck 顶部为索引 0."""

    round: int
    age: Age
    current_player: int
    card_row: tuple[str | None, ...]
    civil_deck: tuple[str, ...]
    future_decks: dict[str, tuple[str, ...]]   # Age.value -> 牌堆
    discard: tuple[str, ...]
    removed: tuple[str, ...]
    players: tuple[PlayerState, ...]
    rng_state: int
    last_round: bool = False
    terminal: bool = False
    final_scores: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if len(self.card_row) != ROW_SLOTS:
            raise ValueError(f"card_row must have {ROW_SLOTS} slots")


def workers_total(p: PlayerState) -> int:
    """玩家工人总数 = 空闲 + 各建筑上的工人."""
    placed = sum(n for slots in p.buildings.values() for n in slots.values())
    return p.worker_pool + placed


def replace_player(state: GameState, index: int, player: PlayerState) -> GameState:
    """替换指定位置玩家, 返回新 GameState."""
    players = list(state.players)
    players[index] = player
    return replace(state, players=tuple(players))


def _player_to_dict(p: PlayerState) -> dict:
    return {
        "name": p.name,
        "culture": p.culture,
        "science": p.science,
        "materials": p.materials,
        "food": p.food,
        "yellow_bank": p.yellow_bank,
        "worker_pool": p.worker_pool,
        "buildings": {k: dict(v) for k, v in sorted(p.buildings.items())},
        "developed": list(p.developed),
        "hand_civil": list(p.hand_civil),
        "government": p.government,
        "civil_actions": p.civil_actions,
        "military_actions": p.military_actions,
    }


def _player_from_dict(d: dict) -> PlayerState:
    return PlayerState(
        name=d["name"],
        culture=d["culture"],
        science=d["science"],
        materials=d["materials"],
        food=d["food"],
        yellow_bank=d["yellow_bank"],
        worker_pool=d["worker_pool"],
        buildings={k: dict(v) for k, v in d["buildings"].items()},
        developed=tuple(d["developed"]),
        hand_civil=tuple(d["hand_civil"]),
        government=d["government"],
        civil_actions=d["civil_actions"],
        military_actions=d["military_actions"],
    )


def to_dict(state: GameState) -> dict:
    """序列化为 JSON 可编码 dict."""
    return {
        "round": state.round,
        "age": state.age.value,
        "current_player": state.current_player,
        "card_row": list(state.card_row),
        "civil_deck": list(state.civil_deck),
        "future_decks": {k: list(v) for k, v in sorted(state.future_decks.items())},
        "discard": list(state.discard),
        "removed": list(state.removed),
        "players": [_player_to_dict(p) for p in state.players],
        "rng_state": state.rng_state,
        "last_round": state.last_round,
        "terminal": state.terminal,
        "final_scores": list(state.final_scores) if state.final_scores else None,
    }


def from_dict(data: dict) -> GameState:
    """从 to_dict 产物还原 GameState."""
    return GameState(
        round=data["round"],
        age=Age(data["age"]),
        current_player=data["current_player"],
        card_row=tuple(data["card_row"]),
        civil_deck=tuple(data["civil_deck"]),
        future_decks={k: tuple(v) for k, v in data["future_decks"].items()},
        discard=tuple(data["discard"]),
        removed=tuple(data["removed"]),
        players=tuple(_player_from_dict(d) for d in data["players"]),
        rng_state=data["rng_state"],
        last_round=data["last_round"],
        terminal=data["terminal"],
        final_scores=tuple(data["final_scores"]) if data["final_scores"] else None,
    )


def state_hash(state: GameState) -> str:
    """规范化 JSON 的 sha256, 用于棋谱链式校验."""
    blob = json.dumps(to_dict(state), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
