"""游戏状态: 纯数据树, 可完整 JSON 序列化.

不可变约定: 所有 dataclass frozen; 嵌套 dict(buildings/card_tokens/turn_discounts)
修改前整体复制.
"""

import hashlib
import json
from dataclasses import dataclass, field, replace

from tta.engine.enums import Age, Phase

ROW_SLOTS = 13
"""卡牌行槽位数(原 constants.py 职责已由 tracks.py 取代, 直接定义于此)."""


@dataclass(frozen=True)
class PendingEffect:
    """等待结算的子行动/响应队列项.

    kind "develop_tech"(breakthrough)时: discount 恒 0(全价研发),
    science_gain 为研发完成后获得的科技点数。
    responder: 响应者座位; None = 由 current_player 结算(P1 行动卡
    子行动)。responder 非 None 且 ≠ current_player 时, legal/apply
    以 responder 为行动者(见 legal.legal_actions)。
    context: 响应上下文(卡片 id、攻击者座位等), 机制 P2 后续任务填充。
    """

    kind: str        # "build_farm_mine" | "build_urban" | "wonder_stage" | "develop_tech" | ...
    discount: int    # 资源费折扣
    science_gain: int = 0  # develop_tech 子行动完成后的科技点收益
    responder: int | None = None
    context: dict[str, str | int] = field(default_factory=dict)


@dataclass(frozen=True)
class PlayerState:
    """单个玩家状态.

    buildings: {category.value: {card_id: 工人数}}; card_tokens: 农场/矿场卡上蓝点;
    developed: 已研发(置于场上)的科技卡 id; wonder_progress: (card_id, 已完成阶段数).
    """

    name: str
    culture: int = 0
    science: int = 0
    yellow_bank: int = 18
    blue_bank: int = 16
    worker_pool: int = 1
    buildings: dict[str, dict[str, int]] = field(default_factory=dict)
    card_tokens: dict[str, int] = field(default_factory=dict)
    developed: tuple[str, ...] = ()
    hand_civil: tuple[str, ...] = ()
    hand_military: tuple[str, ...] = ()      # 军事手牌(回合末抓取, 见 turn)
    government: str = "despotism"
    leader: str | None = None
    leader_ages: tuple[str, ...] = ()
    wonder_progress: tuple[str, int] | None = None
    wonders: tuple[str, ...] = ()
    civil_actions: int = 0
    military_actions: int = 0
    turn_discounts: dict[str, int] = field(default_factory=dict)
    # --- P2 军事/政治字段(机制后续任务填充, 本任务仅建模与序列化) ---
    tactics: str | None = None               # 当前专属阵型
    tactics_public: bool = False             # 已公开(可被复制)
    tactics_this_turn: bool = False          # 本回合已打出/复制阵型(限 1)
    tactics_copied: bool = False             # 当前阵型为复制引用(无实体卡, 替换时不入弃牌堆)
    colonies: tuple[str, ...] = ()
    declared_wars: tuple[str, ...] = ()      # 已宣告待结算的战争牌
    pacts: tuple[str, ...] = ()              # 生效中的条约(卡 id, 3-4 人)
    caesar_used: bool = False                # Julius Caesar 双政治一次性
    civil_action_debt: int = 0               # 下回合白点扣减(rebellion 事件;
                                             # 回合末行动点恢复时生效并清零)


@dataclass(frozen=True)
class GameState:
    """整局状态. card_row 中 None 表示空格; civil_deck 顶部为索引 0."""

    round: int
    age: Age
    current_player: int          # 0 号位 = 起始玩家
    card_row: tuple[str | None, ...]
    civil_deck: tuple[str, ...]
    future_decks: dict[str, tuple[str, ...]]
    discard: tuple[str, ...]
    removed: tuple[str, ...]
    players: tuple[PlayerState, ...]
    rng_state: int
    pending: tuple[PendingEffect, ...] = ()
    last_round: bool = False
    terminal: bool = False
    final_scores: tuple[int, ...] | None = None
    phase: Phase = Phase.ACTION
    # --- P2 军事/事件牌堆(机制后续任务填充, 本任务仅建模与序列化) ---
    military_deck: tuple[str, ...] = ()
    future_military_decks: dict[str, tuple[str, ...]] = field(
        default_factory=dict)
    military_discard: tuple[str, ...] = ()
    current_events: tuple[str, ...] = ()
    future_events: tuple[str, ...] = ()
    past_events: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.card_row) != ROW_SLOTS:
            raise ValueError(f"card_row must have {ROW_SLOTS} slots")


def workers_total(p: PlayerState) -> int:
    """玩家工人总数 = 空闲 + 各建筑上的工人."""
    placed = sum(n for slots in p.buildings.values() for n in slots.values())
    return p.worker_pool + placed


def acting_index(state: GameState) -> int:
    """当前行动者座位: 首个 pending 指定 responder 时为其响应, 否则当前玩家."""
    if state.pending and state.pending[0].responder is not None:
        return state.pending[0].responder
    return state.current_player


def replace_player(state: GameState, index: int, player: PlayerState) -> GameState:
    """替换指定位置玩家, 返回新 GameState."""
    players = list(state.players)
    players[index] = player
    return replace(state, players=tuple(players))


def _pending_to_dict(e: PendingEffect) -> dict:
    # science_gain 缺省 0 / responder None / context 空 时不落盘,
    # 保持旧格式逐字节兼容(棋谱哈希不变)
    data = {"kind": e.kind, "discount": e.discount}
    if e.science_gain:
        data["science_gain"] = e.science_gain
    if e.responder is not None:
        data["responder"] = e.responder
    if e.context:
        data["context"] = dict(sorted(e.context.items()))
    return data


def _pending_from_dict(d: dict) -> PendingEffect:
    return PendingEffect(
        kind=d["kind"], discount=d["discount"],
        science_gain=d.get("science_gain", 0),
        responder=d.get("responder"),
        context=dict(d.get("context", {})))


def _player_to_dict(p: PlayerState) -> dict:
    data = {
        "name": p.name,
        "culture": p.culture,
        "science": p.science,
        "yellow_bank": p.yellow_bank,
        "blue_bank": p.blue_bank,
        "worker_pool": p.worker_pool,
        "buildings": {k: dict(v) for k, v in sorted(p.buildings.items())},
        "card_tokens": dict(sorted(p.card_tokens.items())),
        "developed": list(p.developed),
        "hand_civil": list(p.hand_civil),
        "hand_military": list(p.hand_military),
        "government": p.government,
        "leader": p.leader,
        "leader_ages": list(p.leader_ages),
        "wonder_progress": list(p.wonder_progress) if p.wonder_progress else None,
        "wonders": list(p.wonders),
        "civil_actions": p.civil_actions,
        "military_actions": p.military_actions,
        "turn_discounts": dict(sorted(p.turn_discounts.items())),
        "tactics": p.tactics,
        "tactics_public": p.tactics_public,
        "tactics_this_turn": p.tactics_this_turn,
        "tactics_copied": p.tactics_copied,
        "colonies": list(p.colonies),
        "declared_wars": list(p.declared_wars),
        "pacts": list(p.pacts),
        "caesar_used": p.caesar_used,
    }
    if p.civil_action_debt:
        # rebellion 下回合白点扣减; 非 0 才落盘(旧格式逐字节兼容)
        data["civil_action_debt"] = p.civil_action_debt
    return data


def _player_from_dict(d: dict) -> PlayerState:
    wonder_progress = d["wonder_progress"]
    return PlayerState(
        name=d["name"],
        culture=d["culture"],
        science=d["science"],
        yellow_bank=d["yellow_bank"],
        blue_bank=d["blue_bank"],
        worker_pool=d["worker_pool"],
        buildings={k: dict(v) for k, v in d["buildings"].items()},
        card_tokens=dict(d["card_tokens"]),
        developed=tuple(d["developed"]),
        hand_civil=tuple(d["hand_civil"]),
        hand_military=tuple(d["hand_military"]),
        government=d["government"],
        leader=d["leader"],
        leader_ages=tuple(d["leader_ages"]),
        wonder_progress=tuple(wonder_progress) if wonder_progress else None,
        wonders=tuple(d["wonders"]),
        civil_actions=d["civil_actions"],
        military_actions=d["military_actions"],
        turn_discounts=dict(d["turn_discounts"]),
        # P2 字段: 旧格式缺省落默认值(向后兼容)
        tactics=d.get("tactics"),
        tactics_public=d.get("tactics_public", False),
        tactics_this_turn=d.get("tactics_this_turn", False),
        tactics_copied=d.get("tactics_copied", False),
        colonies=tuple(d.get("colonies", ())),
        declared_wars=tuple(d.get("declared_wars", ())),
        pacts=tuple(d.get("pacts", ())),
        caesar_used=d.get("caesar_used", False),
        civil_action_debt=d.get("civil_action_debt", 0),
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
        "pending": [_pending_to_dict(e) for e in state.pending],
        "last_round": state.last_round,
        "terminal": state.terminal,
        "final_scores": list(state.final_scores) if state.final_scores else None,
        "phase": state.phase.value,
        "military_deck": list(state.military_deck),
        "future_military_decks": {
            k: list(v) for k, v in sorted(state.future_military_decks.items())},
        "military_discard": list(state.military_discard),
        "current_events": list(state.current_events),
        "future_events": list(state.future_events),
        "past_events": list(state.past_events),
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
        pending=tuple(_pending_from_dict(d) for d in data["pending"]),
        last_round=data["last_round"],
        terminal=data["terminal"],
        final_scores=tuple(data["final_scores"]) if data["final_scores"] else None,
        # P2 字段: 旧格式缺省落默认值(向后兼容)
        phase=Phase(data.get("phase", Phase.ACTION.value)),
        military_deck=tuple(data.get("military_deck", ())),
        future_military_decks={
            k: tuple(v)
            for k, v in data.get("future_military_decks", {}).items()},
        military_discard=tuple(data.get("military_discard", ())),
        current_events=tuple(data.get("current_events", ())),
        future_events=tuple(data.get("future_events", ())),
        past_events=tuple(data.get("past_events", ())),
    )


def state_hash(state: GameState) -> str:
    """规范化 JSON 的 sha256, 用于棋谱链式校验."""
    blob = json.dumps(to_dict(state), sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
