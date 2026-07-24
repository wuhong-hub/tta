"""动作类型: 扁平、可序列化."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TakeCard:
    """从卡牌列拿牌."""

    row_index: int


@dataclass(frozen=True)
class Develop:
    """研发手牌中的科技/政体/兵种卡(付科技点)."""

    card_id: str


@dataclass(frozen=True)
class Build:
    """在已研发建筑/兵种卡上放置 1 个工人(付资源)."""

    card_id: str


@dataclass(frozen=True)
class IncreasePopulation:
    """增加 1 个人口(付食物)."""


@dataclass(frozen=True)
class PlayActionCard:
    """打出手牌中的行动卡."""

    card_id: str


@dataclass(frozen=True)
class PassTurn:
    """结束本回合行动阶段."""


Action = TakeCard | Develop | Build | IncreasePopulation | PlayActionCard | PassTurn

_ACTION_TYPES: dict[str, type] = {
    "take_card": TakeCard,
    "develop": Develop,
    "build": Build,
    "increase_population": IncreasePopulation,
    "play_action_card": PlayActionCard,
    "pass": PassTurn,
}
_TYPE_NAMES: dict[type, str] = {v: k for k, v in _ACTION_TYPES.items()}


class IllegalActionError(Exception):
    """动作不合法或时机错误."""


def action_to_dict(action: Action) -> dict:
    """序列化动作."""
    data = {"type": _TYPE_NAMES[type(action)]}
    data.update(vars(action))
    return data


def action_from_dict(data: dict) -> Action:
    """反序列化动作."""
    cls = _ACTION_TYPES[data["type"]]
    kwargs = {k: v for k, v in data.items() if k != "type"}
    return cls(**kwargs)  # type: ignore[call-arg]
