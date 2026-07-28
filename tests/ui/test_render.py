"""棋盘渲染器测试(见 tta/ui/render.py 模块 docstring).

快照以 new_game(build_card_db(), 2, seed=42) 与手工构造局中 state 为夹具,
断言关键行(非全屏逐字); 隐藏信息测试断言对手军事手牌卡名绝不入渲染。
"""

import re
from dataclasses import replace

import pytest

from tta.cards import build_card_db
from tta.engine import (
    Action,
    Build,
    BuildWonderStage,
    ChooseEventOption,
    ColonizeBid,
    CopyTactics,
    DeclineResponse,
    Destroy,
    DevelopGovernment,
    DevelopTech,
    Disband,
    DiscardMilitary,
    IncreasePopulation,
    PactAccept,
    PassResponse,
    PassTurn,
    PendingEffect,
    PlayActionCard,
    PlayAggression,
    PlayDefenseBonus,
    PlayLeader,
    PlayTactics,
    SkipPolitics,
    TakeCard,
    Upgrade,
    new_game,
)
from tta.engine.model import CardDB
from tta.engine.state import GameState
from tta.ui import (
    describe_action,
    hidden_summary,
    render_actions,
    render_game,
)


@pytest.fixture(scope="module")
def db() -> CardDB:
    return build_card_db()


@pytest.fixture()
def initial(db: CardDB) -> GameState:
    return new_game(db, 2, seed=42)


def _menu_numbers(out: str) -> list[int]:
    return [
        int(m.group(1))
        for line in out.splitlines()
        if (m := re.match(r"\s+(\d+)\. ", line))
    ]


# --- render_game: 开局快照 ----------------------------------------------------


def test_render_initial_snapshot(db: CardDB, initial: GameState) -> None:
    out = render_game(initial, db, 0)
    lines = out.splitlines()
    assert lines[0] == (
        "时代 A · 第 1 轮 · P0 的回合(行动阶段) 白点:1 红点:0")
    # 卡牌列 13 格齐全
    row_line = next(x for x in lines if x.startswith("卡牌列: "))
    for i in range(13):
        assert f"[{i}] " in row_line
    # 奇迹卡标注
    assert "[奇迹]" in row_line
    # 事件区只显示数量(2p: 当前事件堆 = 人数+2 = 4)
    assert "事件: 当前事件堆 4 张(暗置) | 未来事件堆 0 张 | 军事牌堆 0 张" in out
    # 对手摘要(武士 1 工人 = 军力 1; 军事手牌数量口径)
    assert (
        "P1: 文化0 科技0 军力1 笑脸0/需0 | 工人7(池1) 黄点18 蓝点16 | "
        "领袖:— 奇迹:— 阵型:— 殖民地:0 | 内政手牌0 军事手牌0张(隐藏)"
    ) in out
    # 自己的面板: 初始建筑工人分布与行动点/政体
    assert "--- 你的面板 P0 ---" in out
    assert "农场: 农业×2" in out
    assert "矿场: 青铜×2" in out
    assert "实验室: 哲学×1" in out
    assert "步兵: 武士×1" in out
    assert "军力 1(基础1 + 阵型/加成0)" in out
    assert "行动点 白点1 红点0 政体 专制" in out
    # 无 pending 时不显示响应行
    assert "响应:" not in out


def test_render_card_row_empty_slot(db: CardDB, initial: GameState) -> None:
    row = list(initial.card_row)
    row[3] = None
    state = replace(initial, card_row=tuple(row))
    out = render_game(state, db, 0)
    assert "[3] —" in out


def test_render_pending_hint(db: CardDB, initial: GameState) -> None:
    state = replace(initial, pending=(
        PendingEffect(kind="discard_military", discount=0, responder=1),
    ))
    out = render_game(state, db, 0)
    assert "响应: P1 待结算 discard_military(队列 1 项)" in out


# --- render_game: 手工局中 state 快照 ------------------------------------------


def _mid_game(initial: GameState) -> GameState:
    p0 = replace(
        initial.players[0],
        culture=12, science=8,
        leader="alexander_the_great",
        wonders=("pyramids",),
        wonder_progress=("hanging_gardens", 1),
        tactics="legion",
        colonies=("historic_territory_i",),
        hand_civil=("irrigation", "monarchy"),
        hand_military=("defense_colonization_i", "plunder_i"),
        civil_actions=4, military_actions=2,
        yellow_bank=15, blue_bank=9,
    )
    return replace(initial, players=(p0, initial.players[1]))


def test_render_mid_game_panel(db: CardDB, initial: GameState) -> None:
    state = _mid_game(initial)
    out = render_game(state, db, 0)
    stages = len(db.get("hanging_gardens").wonder_stages)
    assert "文化 12(" in out
    assert "科技 8(" in out
    assert "黄点 银行15 池1" in out
    assert "蓝点 银行9" in out
    assert "手牌-内政: 灌溉(科技3)、君主制(和平8/革命2)" in out
    assert "手牌-军事: 防御/殖民 I、掠夺" in out
    assert (
        f"领袖 亚历山大大帝 奇观 金字塔、空中花园(1/{stages}) "
        "阵型 军团 殖民地 历史地区"
    ) in out
    assert "行动点 白点4 红点2 政体 专制" in out


# --- 隐藏信息过滤 ---------------------------------------------------------------


def test_opponent_military_hand_hidden(db: CardDB, initial: GameState) -> None:
    secret = "defense_colonization_i"
    secret_name = db.get(secret).name
    p1 = replace(initial.players[1], hand_military=(secret, "plunder_i"))
    state = replace(initial, players=(initial.players[0], p1))
    out = render_game(state, db, 0)
    # 卡名与卡 id 均不出现在对手视角渲染中
    assert secret_name not in out
    assert secret not in out
    assert db.get("plunder_i").name not in out
    # 数量可见
    assert "军事手牌2张(隐藏)" in out
    # 本人视角卡名可见
    own = render_game(state, db, 1)
    assert secret_name in own


def test_hidden_summary() -> None:
    assert hidden_summary(0) == "0张(隐藏)"
    assert hidden_summary(3) == "3张(隐藏)"


# --- render_actions ------------------------------------------------------------


def _sample_actions() -> list[Action]:
    return [
        TakeCard(0), TakeCard(5),
        DevelopTech("irrigation"),
        DevelopGovernment("monarchy", False),
        DevelopGovernment("monarchy", True),
        Build("agriculture"),
        Upgrade("agriculture", "irrigation"),
        IncreasePopulation(),
        Destroy("bronze"), Disband("warriors"),
        PlayLeader("alexander_the_great"),
        BuildWonderStage(2),
        PlayActionCard("stockpile", ""),
        PlayAggression("plunder_i", 1),
        SkipPolitics(),
        PlayDefenseBonus("defense_colonization_i"),
        PassResponse(), DeclineResponse(), PactAccept(),
        ColonizeBid(3), ChooseEventOption("food"),
        DiscardMilitary("plunder_i"),
        PlayTactics("legion"), CopyTactics("phalanx"),
        PassTurn(),
    ]


def test_render_actions_groups_and_numbering(db: CardDB) -> None:
    legal = _sample_actions()
    out = render_actions(legal, db)
    assert out.splitlines()[0] == f"可用动作(共 {len(legal)} 项):"
    for group in (
        "拿牌", "研发", "建造与升级", "人口与拆除", "领袖与奇迹",
        "行动卡", "政治行动", "响应", "其他",
    ):
        assert f"[{group}]" in out
    # 编号全局连续 1..N
    assert _menu_numbers(out) == list(range(1, len(legal) + 1))


def test_render_actions_descriptions_with_costs(db: CardDB) -> None:
    out = render_actions(_sample_actions(), db)
    assert "拿取 [0] 号位卡牌(白点1)" in out
    assert "拿取 [5] 号位卡牌(白点2)" in out
    assert "研发 灌溉(科技3, 白点1)" in out
    assert "和平演变 君主制(科技8, 白点1)" in out
    assert "革命 君主制(科技2, 全部剩余白点)" in out
    assert "建造 农业(资源2, 白点1)" in out
    assert "升级 农业→灌溉(资源2, 白点1)" in out
    assert "解散 武士(红点1)" in out
    assert "打出阵型 军团(红点1)" in out
    assert "复制阵型 方阵(红点2)" in out
    assert "发动侵略 掠夺 → P1(红点1)" in out
    assert "打出防御奖励 防御/殖民 I(+2 军力)" in out
    assert "选择 食物" in out
    assert "结束回合" in out


def test_render_actions_empty(db: CardDB) -> None:
    assert render_actions([], db) == "可用动作(共 0 项):"


def test_describe_action_unknown_type(db: CardDB) -> None:
    class Weird:
        pass

    with pytest.raises(ValueError, match="未知动作类型"):
        describe_action(Weird(), db)  # type: ignore[arg-type]
