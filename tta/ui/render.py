"""棋盘渲染器: GameState / Action -> 人类可读文本(纯函数, 无 IO).

隐藏信息过滤(官方规则信息集, seat 视角):
- 对手军事手牌只显示数量(卡名绝不入渲染), 自己军事手牌卡名可见;
- 当前事件堆(暗置)/未来事件堆/军事牌堆只显示数量。

本包仅依赖 tta.engine 公开接口; engine/agents/orchestrator 不依赖本包。
描述中的费用为卡面静态费用(无 state 口径), 回合修饰/折扣不在此呈现。
"""

from tta.engine import (
    ROW_COSTS,
    UNIT_CATEGORIES,
    WORKER_CATEGORIES,
    Action,
    Build,
    BuildWonderStage,
    CancelPact,
    CardCategory,
    CardDB,
    ChooseEventOption,
    ChooseTurnStart,
    ColonizeBid,
    ColonizePass,
    ColonizePlayBonus,
    ColonizeSacrifice,
    CopyTactics,
    DeclareWar,
    DeclineResponse,
    Destroy,
    DevelopGovernment,
    DevelopTech,
    Disband,
    DiscardForStrength,
    DiscardMilitary,
    GameState,
    IncreasePopulation,
    PactAccept,
    PactReject,
    PassResponse,
    PassTurn,
    PlayActionCard,
    PlayAggression,
    PlayDefenseBonus,
    PlayerState,
    PlayLeader,
    PlayTactics,
    ProposePact,
    Resign,
    SeedEvent,
    SkipPolitics,
    TakeCard,
    Upgrade,
    civ_values,
    consumption_value,
    corruption_value,
    discontent,
    food_total,
    happiness_required,
    population_cost,
    resource_total,
    workers_total,
)

_PHASE_NAMES = {
    "turn_start": "回合开始",
    "politics": "政治阶段",
    "action": "行动阶段",
}

_CATEGORY_LABELS = {
    "farm": "农场",
    "mine": "矿场",
    "lab": "实验室",
    "temple": "寺庙",
    "library": "图书馆",
    "theater": "剧院",
    "arena": "竞技场",
    "infantry": "步兵",
    "cavalry": "骑兵",
    "artillery": "炮兵",
    "air": "空军",
}
"""建筑明细展示顺序(键 = CardCategory.value)."""

_OPTION_LABELS = {
    "food": "食物",
    "resource": "资源",
    "done": "结束拿牌",
    "population": "增加人口",
    "farm_mine": "建造农场/矿场",
    "urban": "建造城市建筑",
    "tech": "研发科技",
}
"""事件/选择 pending 常见 option 的中文标签; 未收录者按卡 id 或原样显示."""

_EMPTY = "—"


def hidden_summary(count: int) -> str:
    """隐藏手牌摘要: 只暴露数量, 不暴露任何卡名."""
    return f"{count}张(隐藏)"


def _name(db: CardDB, card_id: str) -> str:
    return db.get(card_id).name


def _option_label(db: CardDB, option: str) -> str:
    """选择类 pending 的 option 标签: 卡 id 显示卡名, 其余查表/原样."""
    if option in db.cards:
        return db.get(option).name
    return _OPTION_LABELS.get(option, option)


def _base_strength(db: CardDB, p: PlayerState) -> int:
    """军事单位基础军力(不含阵型与静态加成), 用于军力分解展示."""
    total = 0
    for category in UNIT_CATEGORIES:
        for card_id, workers in p.buildings.get(category.value, {}).items():
            total += db.get(card_id).strength * workers
    return total


def _title_line(state: GameState) -> str:
    """标题行: 时代/轮次/当前玩家/相位/当前玩家剩余行动点."""
    actor = state.current_player
    p = state.players[actor]
    phase = _PHASE_NAMES.get(state.phase.value, state.phase.value)
    return (
        f"时代 {state.age.value} · 第 {state.round} 轮 · "
        f"P{actor} 的回合({phase}) "
        f"白点:{p.civil_actions} 红点:{p.military_actions}"
    )


def _pending_line(state: GameState) -> str:
    """pending 响应提示行(仅 pending 非空时调用)."""
    pending = state.pending[0]
    responder = (
        pending.responder
        if pending.responder is not None
        else state.current_player
    )
    return f"响应: P{responder} 待结算 {pending.kind}(队列 {len(state.pending)} 项)"


def _card_row_line(state: GameState, db: CardDB) -> str:
    """卡牌列: 13 格, 序号 + 卡名 + 拿牌费(ROW_COSTS), 空格显示 —."""
    slots: list[str] = []
    for i, card_id in enumerate(state.card_row):
        if card_id is None:
            slots.append(f"[{i}] {_EMPTY}")
            continue
        card = db.get(card_id)
        marker = "[奇迹]" if card.category is CardCategory.WONDER else ""
        slots.append(f"[{i}] {card.name}{marker}(费{ROW_COSTS[i]})")
    return "卡牌列: " + "  ".join(slots)


def _events_line(state: GameState) -> str:
    """事件区: 各堆只显示数量(当前事件堆暗置, 军事牌堆未启用为 0)."""
    return (
        f"事件: 当前事件堆 {len(state.current_events)} 张(暗置) | "
        f"未来事件堆 {len(state.future_events)} 张 | "
        f"军事牌堆 {len(state.military_deck)} 张"
    )


def _join_names(db: CardDB, card_ids: tuple[str, ...]) -> str:
    return "、".join(_name(db, cid) for cid in card_ids) if card_ids else _EMPTY


def _opponent_line(db: CardDB, state: GameState, index: int) -> str:
    """对手摘要(单行): 公开数值 + 隐藏手牌数量(军事手牌不显示卡名)."""
    p = state.players[index]
    civ = civ_values(db, p, state.players, index)
    leader = _name(db, p.leader) if p.leader else _EMPTY
    wonders = _join_names(db, p.wonders)
    tactics = _name(db, p.tactics) if p.tactics else _EMPTY
    resigned = " [已退出]" if p.resigned else ""
    return (
        f"P{index}: 文化{p.culture} 科技{p.science} 军力{civ.strength} "
        f"笑脸{civ.happiness}/需{happiness_required(p.yellow_bank)} | "
        f"工人{workers_total(p)}(池{p.worker_pool}) "
        f"黄点{p.yellow_bank} 蓝点{p.blue_bank} | "
        f"领袖:{leader} 奇迹:{wonders} 阵型:{tactics} "
        f"殖民地:{len(p.colonies)} | "
        f"内政手牌{len(p.hand_civil)} "
        f"军事手牌{hidden_summary(len(p.hand_military))}{resigned}"
    )


def _building_lines(db: CardDB, p: PlayerState) -> list[str]:
    """建筑明细: 每类有工人的卡 卡名×工人数(蓝点数, 仅卡上有蓝点时)."""
    lines = ["建筑明细:"]
    shown = False
    for category_value, label in _CATEGORY_LABELS.items():
        slots = p.buildings.get(category_value, {})
        parts: list[str] = []
        for card_id, workers in sorted(slots.items()):
            if workers <= 0:
                continue
            part = f"{_name(db, card_id)}×{workers}"
            tokens = p.card_tokens.get(card_id, 0)
            if tokens > 0:
                part += f"(蓝点{tokens})"
            parts.append(part)
        if parts:
            shown = True
            lines.append(f"  {label}: " + "、".join(parts))
    if not shown:
        lines.append("  (无)")
    return lines


def _hand_hint(card_category: CardCategory, cost_science: int,
               cost_revolution: int) -> str:
    """内政手牌费用提示(卡面静态费)."""
    if card_category is CardCategory.GOVERNMENT:
        return f"和平{cost_science}/革命{cost_revolution}"
    if card_category in WORKER_CATEGORIES or card_category is CardCategory.SPECIAL:
        return f"科技{cost_science}"
    if card_category in (CardCategory.ACTION, CardCategory.LEADER):
        return "白点1"
    if card_category is CardCategory.WONDER:
        return "奇迹"
    return ""


def _civil_hand_line(db: CardDB, p: PlayerState) -> str:
    parts: list[str] = []
    for card_id in p.hand_civil:
        card = db.get(card_id)
        hint = _hand_hint(
            card.category, card.cost_science, card.cost_science_revolution)
        parts.append(f"{card.name}({hint})" if hint else card.name)
    return "手牌-内政: " + ("、".join(parts) if parts else "(空)")


def _military_hand_line(db: CardDB, p: PlayerState) -> str:
    """自己的军事手牌(仅 seat 本人视角调用; 对手视角恒用数量摘要)."""
    names = "、".join(_name(db, cid) for cid in p.hand_military)
    return "手牌-军事: " + (names if names else "(空)")


def _profile_line(db: CardDB, p: PlayerState) -> str:
    """领袖/奇观(完成与进度 x/y)/阵型/殖民地."""
    leader = _name(db, p.leader) if p.leader else _EMPTY
    wonder_parts = [_name(db, cid) for cid in p.wonders]
    if p.wonder_progress is not None:
        card_id, done = p.wonder_progress
        total = len(db.get(card_id).wonder_stages)
        wonder_parts.append(f"{_name(db, card_id)}({done}/{total})")
    wonders = "、".join(wonder_parts) if wonder_parts else _EMPTY
    tactics = _name(db, p.tactics) if p.tactics else _EMPTY
    colonies = _join_names(db, p.colonies)
    return f"领袖 {leader} 奇观 {wonders} 阵型 {tactics} 殖民地 {colonies}"


def _panel_lines(db: CardDB, state: GameState, seat: int) -> list[str]:
    """seat 自己的面板详情."""
    p = state.players[seat]
    civ = civ_values(db, p, state.players, seat)
    base = _base_strength(db, p)
    pop_cost = (
        str(population_cost(p.yellow_bank)) if p.yellow_bank > 0 else _EMPTY
    )
    lines = [f"--- 你的面板 P{seat} ---"]
    lines.append(
        f"文化 {p.culture}(+{civ.culture_rate}/轮) "
        f"科技 {p.science}(+{civ.science_rate}/轮) "
        f"军力 {civ.strength}(基础{base} + 阵型/加成{civ.strength - base})"
    )
    lines.append(
        f"笑脸 {civ.happiness}/需{happiness_required(p.yellow_bank)} "
        f"不满{discontent(db, p, state.players, seat)}"
    )
    lines.append(
        f"黄点 银行{p.yellow_bank} 池{p.worker_pool} "
        f"增人口费{pop_cost} 食物消耗{consumption_value(p.yellow_bank)}"
    )
    lines.append(
        f"蓝点 银行{p.blue_bank} 腐败{corruption_value(p.blue_bank)}"
    )
    lines.append(f"食物 {food_total(db, p)} 资源 {resource_total(db, p)}")
    lines.extend(_building_lines(db, p))
    lines.append(_civil_hand_line(db, p))
    lines.append(_military_hand_line(db, p))
    lines.append(_profile_line(db, p))
    lines.append(
        f"行动点 白点{p.civil_actions} 红点{p.military_actions} "
        f"政体 {_name(db, p.government)}"
    )
    return lines


def render_game(state: GameState, db: CardDB, seat: int) -> str:
    """以 seat 视角渲染整屏(隐藏信息过滤见模块 docstring).

    Args:
        state: 当前游戏状态.
        db: 卡牌数据库.
        seat: 视角座位(0 基); 该玩家的手牌/面板完整显示, 对手仅摘要.

    Returns:
        多行文本(以换行连接).
    """
    lines = [_title_line(state)]
    if state.pending:
        lines.append(_pending_line(state))
    lines.append(_card_row_line(state, db))
    lines.append(_events_line(state))
    opponents = [i for i in range(len(state.players)) if i != seat]
    if opponents:
        lines.append("--- 对手 ---")
        lines.extend(_opponent_line(db, state, i) for i in opponents)
    lines.extend(_panel_lines(db, state, seat))
    return "\n".join(lines)


def describe_action(action: Action, db: CardDB) -> str:
    """动作的人类可读描述(含卡面静态费用; 供动作菜单与回放复用).

    Raises:
        ValueError: 未知动作类型.
    """
    if isinstance(action, TakeCard):
        return f"拿取 [{action.row_index}] 号位卡牌(白点{ROW_COSTS[action.row_index]})"
    if isinstance(action, DevelopTech):
        card = db.get(action.card_id)
        point = "红点1" if card.category in UNIT_CATEGORIES else "白点1"
        return f"研发 {card.name}(科技{card.cost_science}, {point})"
    if isinstance(action, DevelopGovernment):
        card = db.get(action.card_id)
        if action.revolution:
            return f"革命 {card.name}(科技{card.cost_science_revolution}, 全部剩余白点)"
        return f"和平演变 {card.name}(科技{card.cost_science}, 白点1)"
    if isinstance(action, Build):
        card = db.get(action.card_id)
        point = "红点1" if card.category in UNIT_CATEGORIES else "白点1"
        return f"建造 {card.name}(资源{card.build_cost}, {point})"
    if isinstance(action, Upgrade):
        from_card = db.get(action.from_card_id)
        to_card = db.get(action.to_card_id)
        point = "红点1" if to_card.category in UNIT_CATEGORIES else "白点1"
        diff = max(0, to_card.build_cost - from_card.build_cost)
        return f"升级 {from_card.name}→{to_card.name}(资源{diff}, {point})"
    if isinstance(action, Destroy):
        return f"拆除 {_name(db, action.card_id)}(白点1)"
    if isinstance(action, Disband):
        return f"解散 {_name(db, action.card_id)}(红点1)"
    if isinstance(action, PlayLeader):
        return f"打出领袖 {_name(db, action.card_id)}(白点1)"
    if isinstance(action, BuildWonderStage):
        return f"建造奇迹 {action.count} 阶段(白点1)"
    if isinstance(action, PlayActionCard):
        desc = f"打出行动卡 {_name(db, action.card_id)}(白点1)"
        if action.option:
            desc += f" 选项:{_option_label(db, action.option)}"
        return desc
    if isinstance(action, IncreasePopulation):
        return "增加人口(白点1 + 食物人口费)"
    if isinstance(action, PlayTactics):
        return f"打出阵型 {_name(db, action.card_id)}(红点1)"
    if isinstance(action, CopyTactics):
        return f"复制阵型 {_name(db, action.card_id)}(红点2)"
    if isinstance(action, DiscardMilitary):
        return f"弃军事牌 {_name(db, action.card_id)}"
    if isinstance(action, SkipPolitics):
        return "跳过政治阶段"
    if isinstance(action, SeedEvent):
        return f"筹划事件 {_name(db, action.card_id)}"
    if isinstance(action, PlayAggression):
        card = db.get(action.card_id)
        return f"发动侵略 {card.name} → P{action.target}(红点{card.military_cost})"
    if isinstance(action, DeclareWar):
        card = db.get(action.card_id)
        return f"宣告战争 {card.name} → P{action.target}(红点{card.military_cost})"
    if isinstance(action, ProposePact):
        return f"提议条约 {_name(db, action.card_id)} → P{action.target}(侧{action.side})"
    if isinstance(action, CancelPact):
        return f"退出条约 {_name(db, action.card_id)}"
    if isinstance(action, Resign):
        return "体面退出"
    if isinstance(action, PactAccept):
        return "接受条约"
    if isinstance(action, PactReject):
        return "拒绝条约"
    if isinstance(action, PlayDefenseBonus):
        card = db.get(action.card_id)
        return f"打出防御奖励 {card.name}(+{card.defense_bonus} 军力)"
    if isinstance(action, DiscardForStrength):
        return f"弃 {_name(db, action.card_id)}(+1 军力)"
    if isinstance(action, PassResponse):
        return "结束响应"
    if isinstance(action, DeclineResponse):
        return "放弃响应"
    if isinstance(action, ChooseEventOption):
        return f"选择 {_option_label(db, action.option)}"
    if isinstance(action, ChooseTurnStart):
        return f"选择 {_option_label(db, action.option)}"
    if isinstance(action, ColonizeBid):
        return f"殖民出价 {action.amount}"
    if isinstance(action, ColonizePass):
        return "退出殖民竞拍"
    if isinstance(action, ColonizePlayBonus):
        card = db.get(action.card_id)
        return f"打出殖民奖励 {card.name}(+{card.colonize_bonus})"
    if isinstance(action, ColonizeSacrifice):
        names = "、".join(_name(db, cid) for cid in action.units)
        return f"牺牲军事单位 {names}"
    if isinstance(action, PassTurn):
        return "结束回合"
    msg = f"未知动作类型: {type(action).__name__}"
    raise ValueError(msg)


_GROUPS: tuple[tuple[str, tuple[type, ...]], ...] = (
    ("拿牌", (TakeCard,)),
    ("研发", (DevelopTech, DevelopGovernment)),
    ("建造与升级", (Build, Upgrade)),
    ("人口与拆除", (IncreasePopulation, Destroy, Disband)),
    ("领袖与奇迹", (PlayLeader, BuildWonderStage)),
    ("行动卡", (PlayActionCard,)),
    ("政治行动", (
        SeedEvent, PlayAggression, DeclareWar, ProposePact, CancelPact,
        Resign, SkipPolitics,
    )),
    ("响应", (
        DeclineResponse, PlayDefenseBonus, DiscardForStrength, PassResponse,
        PactAccept, PactReject, ChooseEventOption, ChooseTurnStart,
        ColonizeBid, ColonizePass, ColonizePlayBonus, ColonizeSacrifice,
        DiscardMilitary,
    )),
)
"""动作菜单分组(顺序即展示顺序); 未归入者(阵型/结束回合)落 [其他]."""


def render_actions(legal: list[Action], db: CardDB) -> str:
    """合法动作渲染为分组编号菜单(编号全局连续, 菜单输入用).

    空分组不展示; 编号从 1 起, 跨分组连续递增。
    """
    buckets: dict[str, list[Action]] = {name: [] for name, _ in _GROUPS}
    others: list[Action] = []
    for action in legal:
        for name, types in _GROUPS:
            if isinstance(action, types):
                buckets[name].append(action)
                break
        else:
            others.append(action)

    lines = [f"可用动作(共 {len(legal)} 项):"]
    number = 0

    def _emit(group: str, actions: list[Action]) -> None:
        nonlocal number
        if not actions:
            return
        lines.append(f"[{group}]")
        for action in actions:
            number += 1
            lines.append(f"  {number}. {describe_action(action, db)}")

    for name, _ in _GROUPS:
        _emit(name, buckets[name])
    _emit("其他", others)
    return "\n".join(lines)
