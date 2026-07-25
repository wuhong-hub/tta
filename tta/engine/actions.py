"""动作类型: 扁平、可序列化(官方规则 P1)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TakeCard:
    """从卡牌列拿牌(奇迹牌拿取即入场, 置 wonder_progress, 不入队手牌)."""

    row_index: int


@dataclass(frozen=True)
class DevelopTech:
    """研发手牌中的科技/特殊科技/兵种卡: 1 白点(兵种 1 红点) + 科技费."""

    card_id: str


@dataclass(frozen=True)
class DevelopGovernment:
    """变更政体: 和平 1 白点 + 高费; 革命全部剩余白点 + 低费."""

    card_id: str
    revolution: bool


@dataclass(frozen=True)
class Build:
    """从空闲池向已研发建筑/兵种卡放 1 工人: 1 白点(兵种 1 红点) + 全额造价."""

    card_id: str


@dataclass(frozen=True)
class Upgrade:
    """移 1 工人到同类别高等级卡: 1 白点(兵种 1 红点) + 造价差值."""

    from_card_id: str
    to_card_id: str


@dataclass(frozen=True)
class Destroy:
    """摧毁农场/矿场/城市建筑: 1 白点, 1 工人回空闲池."""

    card_id: str


@dataclass(frozen=True)
class Disband:
    """解散军事单位: 1 红点, 1 工人回空闲池."""

    card_id: str


@dataclass(frozen=True)
class PlayLeader:
    """打出领袖: 1 白点; 替换旧领袖(弃置)并拿回 1 白点(净耗 0)."""

    card_id: str


@dataclass(frozen=True)
class BuildWonderStage:
    """建奇迹下一阶段: 1 白点 + 左起下一未付阶段费, 蓝点从供给区盖上."""


@dataclass(frozen=True)
class PlayActionCard:
    """打出手牌中的行动卡: 1 白点, 结算见 effects.ACTION_HANDLERS.

    option: 选择类行动卡(如 reserves_i "+2 资源或 +2 食物")的选项,
    合法取值由 effects.ACTION_OPTIONS 声明; 非选择类恒为 ""。
    """

    card_id: str
    option: str = ""


@dataclass(frozen=True)
class IncreasePopulation:
    """增加人口: 1 白点 + 黄点轨道人口费(moses -1 食物), 黄点银行 -1, 空闲工人 +1."""


@dataclass(frozen=True)
class PassTurn:
    """结束本回合行动阶段(回合推进见 Task 8)."""


Action = (
    TakeCard | DevelopTech | DevelopGovernment | Build | Upgrade | Destroy
    | Disband | PlayLeader | BuildWonderStage | PlayActionCard
    | IncreasePopulation | PassTurn
)

_ACTION_TYPES: dict[str, type] = {
    "take_card": TakeCard,
    "develop_tech": DevelopTech,
    "develop_government": DevelopGovernment,
    "build": Build,
    "upgrade": Upgrade,
    "destroy": Destroy,
    "disband": Disband,
    "play_leader": PlayLeader,
    "build_wonder_stage": BuildWonderStage,
    "play_action_card": PlayActionCard,
    "increase_population": IncreasePopulation,
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
