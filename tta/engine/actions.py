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
class SkipPolitics:
    """跳过政治阶段: phase POLITICS -> ACTION."""


@dataclass(frozen=True)
class DeclineResponse:
    """放弃当前可选 pending(仅"可放弃"白名单 kind, 见 effects/events 的
    DECLINABLE_PENDING_KINDS); 效果 = 丢弃 pending[0](P2-T1 审查交接).

    用于"响应方无合法响应"场景防卡死; 强制类 pending(如 discard_military,
    恒有可执行动作)不可放弃。
    """


@dataclass(frozen=True)
class SeedEvent:
    """筹划事件(政治行动, 每回合限 1): 军事手牌中的 EVENT 卡面朝下压入
    future_events 顶, 并揭示 current_events 顶牌结算(见 politics.seed_event)."""

    card_id: str


@dataclass(frozen=True)
class PlayAggression:
    """打出侵略牌(政治行动, 结算见 politics.play_aggression): 付军事行动费,
    压 aggression_defense pending 由目标响应(规则书 p4 发动侵略)。"""

    card_id: str
    target: int


@dataclass(frozen=True)
class PlayDefenseBonus:
    """防御响应: 打出手中军事奖励牌, 防御数值临时加入军力(可多张).

    打出与弃置的牌总数不能超过防御方总军事行动点数(规则书 p4 限制)。
    """

    card_id: str


@dataclass(frozen=True)
class DiscardForStrength:
    """防御响应: 面朝下弃 1 张军事牌, 临时 +1 军力(可多张, 上限同上)."""

    card_id: str


@dataclass(frozen=True)
class PassResponse:
    """防御响应结束(侵略判定)/无合格建筑时跳过本次 raid 摧毁."""


@dataclass(frozen=True)
class DeclareWar:
    """宣告战争(政治行动, 结算见 politics.declare_war): 付军事行动费,
    战争牌入 declared_wars, 宣告者下个回合开始阶段结算(规则书 p4)。
    最后的游戏轮不可宣告; 与侵略不同, 可向军力更强者宣战。"""

    card_id: str
    target: int


@dataclass(frozen=True)
class ProposePact:
    """提议条约(政治行动, 3-4 人; 结算见 politics.propose_pact): 展示条约牌,
    宣告目标与自己扮演的侧(side: "A"/"B", 对称条约恒 "A"), 压 pact_offer
    pending 由对方接受/拒绝(规则书 p4 提出条约)。"""

    card_id: str
    target: int
    side: str = "A"


@dataclass(frozen=True)
class PactAccept:
    """接受条约提议(pact_offer pending 响应): 双方既有条约失效, 新条约生效."""


@dataclass(frozen=True)
class PactReject:
    """拒绝条约提议(pact_offer pending 响应): 牌回提出者手, 其本回合政治结束."""


@dataclass(frozen=True)
class CancelPact:
    """退出条约(政治行动, 3-4 人; 结算见 politics.cancel_pact): 将你为当事人
    的一项条约从游戏中移除(规则书 p4 取缔条约)。"""

    card_id: str


@dataclass(frozen=True)
class Resign:
    """体面退出(政治行动, 时代 IV 不可用; 结算见 politics.resign): 文明退出
    游戏, 只剩 1 人时其直接判胜(规则书 p4 体面退出)。"""


@dataclass(frozen=True)
class ChooseEventOption:
    """事件选择 pending 的决策(如 development_of_markets 的 food/resource).

    option 合法取值由 pending kind 决定(见 legal._pending_actions)。
    """

    option: str


@dataclass(frozen=True)
class ChooseTurnStart:
    """回合开始选择 pending(turn_start_choice)的决策(如 churchill 二选一).

    option 合法取值由 pending context 的来源卡决定(见
    choices.turn_start_options); 该 pending 为强制选择, 不可 DeclineResponse。
    """

    option: str


@dataclass(frozen=True)
class ColonizeBid:
    """殖民竞拍出价: 须高于当前最高出价, 且不超过可承诺殖民军力上限
    (见 politics.colonization_cap; 规则书 p7 殖民节)。"""

    amount: int


@dataclass(frozen=True)
class ColonizePass:
    """退出殖民竞拍(bidders 移除); 全员退出则地区牌入 past_events."""


@dataclass(frozen=True)
class ColonizePlayBonus:
    """胜者牺牲结算中打出手中军事奖励牌: 殖民数值累加进已出奖励,
    卡入军事弃牌堆(可打出多张, 见 politics.colonize_play_bonus)。"""

    card_id: str


@dataclass(frozen=True)
class ColonizeSacrifice:
    """胜者提交牺牲的军事单位元组(卡 id 可重复表多张, 各牺牲 1 工人).

    组合枚举爆炸, legal 仅提供"全选"锚点动作; apply 独立校验(非法抛
    IllegalActionError): 所选单位军力(按当前阵型组军, 见
    military.units_strength) + 殖民修正 + 已出奖励 >= 出价, 且至少 1 个
    单位(规则书 p7)。成功后工人回黄点银行并获得殖民地。
    """

    units: tuple[str, ...]

    def __post_init__(self) -> None:
        # 反序列化产物(list)归一为 tuple, 保证可哈希与相等性
        object.__setattr__(self, "units", tuple(self.units))


@dataclass(frozen=True)
class DiscardMilitary:
    """弃 1 张军事手牌入军事弃牌堆(响应回合末 discard_military pending)."""

    card_id: str


@dataclass(frozen=True)
class PlayTactics:
    """打出手牌中的阵型牌: 1 红点, 成为专属阵型; 旧阵型入军事弃牌堆."""

    card_id: str


@dataclass(frozen=True)
class CopyTactics:
    """复制任一对手已公开的阵型: 2 红点, 不消耗手牌; 与打出合计每回合限 1."""

    card_id: str


@dataclass(frozen=True)
class PassTurn:
    """结束本回合行动阶段(回合推进见 Task 8)."""


Action = (
    TakeCard | DevelopTech | DevelopGovernment | Build | Upgrade | Destroy
    | Disband | PlayLeader | BuildWonderStage | PlayActionCard
    | IncreasePopulation | SkipPolitics | DiscardMilitary
    | PlayTactics | CopyTactics | PassTurn
    | DeclineResponse | SeedEvent | PlayAggression | DeclareWar
    | ProposePact | PactAccept | PactReject | CancelPact | Resign
    | ChooseEventOption | ChooseTurnStart
    | ColonizeBid | ColonizePass | ColonizePlayBonus | ColonizeSacrifice
    | PlayDefenseBonus | DiscardForStrength | PassResponse
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
    "skip_politics": SkipPolitics,
    "discard_military": DiscardMilitary,
    "play_tactics": PlayTactics,
    "copy_tactics": CopyTactics,
    "pass": PassTurn,
    "decline_response": DeclineResponse,
    "seed_event": SeedEvent,
    "play_aggression": PlayAggression,
    "declare_war": DeclareWar,
    "propose_pact": ProposePact,
    "pact_accept": PactAccept,
    "pact_reject": PactReject,
    "cancel_pact": CancelPact,
    "resign": Resign,
    "choose_event_option": ChooseEventOption,
    "choose_turn_start": ChooseTurnStart,
    "colonize_bid": ColonizeBid,
    "colonize_pass": ColonizePass,
    "colonize_play_bonus": ColonizePlayBonus,
    "colonize_sacrifice": ColonizeSacrifice,
    "play_defense_bonus": PlayDefenseBonus,
    "discard_for_strength": DiscardForStrength,
    "pass_response": PassResponse,
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
