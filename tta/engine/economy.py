"""资源支付引擎: 农场/矿场蓝点的统计、支付、收益与生产.

蓝点储存在农场/矿场卡上(PlayerState.card_tokens), 每点价值 = 卡的
token_value(农场=食物, 矿场=资源); 供给区为 PlayerState.blue_bank.

确定性支付算法(引擎约定, 全引擎唯一支付口径):
1. 反复从该类型卡中取 token_value 最小(并列取 card_id 字典序最小)的卡上
   1 个蓝点放回供给区(blue_bank += 1), 直到累计价值 >= 应付额(官方规则:
   支付/消耗/腐败花掉的蓝点放回蓝色供给区, 不销毁);
2. 若超付, 找零 = 超付额: 从供给区向该类型最低等级卡(同样 token_value
   最小、card_id 字典序并列)放蓝点(blue_bank -= 1), 每点抵该卡 token_value,
   直到找零尽或供给空; 单点价值超过剩余找零额时停止, 找不零的部分损失;
3. 全程不改动入参 PlayerState, 嵌套 dict 整体复制后返回新实例.

支付净效应: 卡上蓝点 -> 供给区, 找零再从供给区 -> 卡; 生产(produce)/
gain_tokens 方向相反(供给区 -> 卡), 蓝点总量闭环守恒。

生产(produce): 该类型每张有工人的卡各从供给区得 1 蓝点; 供给不足时高等级
(token_value 降序, 并列 card_id 字典序升序)卡优先.

按价值获得(gain_value): 向最低等级卡放蓝点直到累计价值达 amount; 单点
价值超过剩余额时停止(找不齐的部分损失), 用于事件"生产 N 食物/资源"。
"""

from dataclasses import replace

from tta.engine.enums import CardCategory
from tta.engine.model import CardDB
from tta.engine.state import PlayerState

_KIND_CATEGORY = {
    "food": CardCategory.FARM,
    "resource": CardCategory.MINE,
}


def _category(kind: str) -> CardCategory:
    """校验 kind 并返回对应卡牌类别."""
    category = _KIND_CATEGORY.get(kind)
    if category is None:
        msg = f'kind 须为 "food" 或 "resource", 收到 {kind!r}'
        raise ValueError(msg)
    return category


def _is_kind(db: CardDB, card_id: str, category: CardCategory) -> bool:
    card = db.cards.get(card_id)
    return card is not None and card.category is category


def _kind_card_ids(db: CardDB, p: PlayerState, category: CardCategory) -> list[str]:
    """玩家场上该类别的卡 id(已研发 / 有工人 / 有蓝点的并集)."""
    ids = set(p.developed)
    ids |= set(p.buildings.get(category.value, {}))
    ids |= set(p.card_tokens)
    return [cid for cid in ids if _is_kind(db, cid, category)]


def _lowest_key(db: CardDB, card_id: str) -> tuple[int, str]:
    """最低等级排序键: token_value 升序, 并列 card_id 字典序."""
    return (db.get(card_id).token_value, card_id)


def _total(db: CardDB, p: PlayerState, kind: str) -> int:
    category = _category(kind)
    return sum(
        n * db.get(cid).token_value
        for cid, n in p.card_tokens.items()
        if n > 0 and _is_kind(db, cid, category)
    )


def food_total(db: CardDB, p: PlayerState) -> int:
    """食物总量 = 农场卡上蓝点 × 各自 token_value 之和."""
    return _total(db, p, "food")


def resource_total(db: CardDB, p: PlayerState) -> int:
    """资源总量 = 矿场卡上蓝点 × 各自 token_value 之和."""
    return _total(db, p, "resource")


def pay(db: CardDB, p: PlayerState, kind: str, amount: int) -> PlayerState:
    """按模块 docstring 的确定性算法支付 amount 点 food/resource.

    amount > 持有总量时抛 ValueError(支付合法性由 legal 层保证).
    """
    category = _category(kind)
    if amount < 0:
        msg = f"amount 须非负, 收到 {amount}"
        raise ValueError(msg)
    total = _total(db, p, kind)
    if amount > total:
        msg = f"{kind} 不足: 需 {amount}, 仅有 {total}"
        raise ValueError(msg)

    tokens = dict(p.card_tokens)
    blue_bank = p.blue_bank

    # 第 1 步: 从最低等级卡逐点取, 取下的蓝点放回供给区, 直到累计 >= amount
    paid = 0
    while paid < amount:
        target = min(
            (cid for cid, n in tokens.items()
             if n > 0 and _is_kind(db, cid, category)),
            key=lambda cid: _lowest_key(db, cid),
        )
        left = tokens[target] - 1
        if left > 0:
            tokens[target] = left
        else:
            del tokens[target]
        blue_bank += 1
        paid += db.get(target).token_value

    # 第 2 步: 超付找零, 从供给区向最低等级卡放蓝点, 找不零的部分损失
    change = paid - amount
    while change > 0 and blue_bank > 0:
        ids = _kind_card_ids(db, p, category)
        if not ids:
            break
        target = min(ids, key=lambda cid: _lowest_key(db, cid))
        value = db.get(target).token_value
        if value > change:
            break
        tokens[target] = tokens.get(target, 0) + 1
        blue_bank -= 1
        change -= value

    return replace(p, card_tokens=tokens, blue_bank=blue_bank)


def settle_loss(
    db: CardDB, p: PlayerState, kind: str, amount: int,
) -> tuple[PlayerState, int]:
    """损失结算(腐败/消耗): 按 pay 的口径支付, 不足部分损失到此为止.

    与 pay 不同, 持有量不足时不抛错: 交出全部持有(蓝点同样放回供给区),
    返回实际支付数。返回 (新 PlayerState, 实际支付的价值), 全程不产生负值。
    """
    total = _total(db, p, kind)
    paid = min(amount, total)
    if paid <= 0:
        return p, 0
    return pay(db, p, kind, paid), paid


def gain_tokens(db: CardDB, p: PlayerState, kind: str, count: int) -> PlayerState:
    """从供给区向该类型最低等级卡放 count 个蓝点.

    供给不足则尽力而为; 场上无该类型卡则放弃(原样返回).
    """
    category = _category(kind)
    if count < 0:
        msg = f"count 须非负, 收到 {count}"
        raise ValueError(msg)
    ids = _kind_card_ids(db, p, category)
    if not ids or count == 0 or p.blue_bank == 0:
        return p
    target = min(ids, key=lambda cid: _lowest_key(db, cid))
    n = min(count, p.blue_bank)
    tokens = dict(p.card_tokens)
    tokens[target] = tokens.get(target, 0) + n
    return replace(p, card_tokens=tokens, blue_bank=p.blue_bank - n)


def produce(db: CardDB, p: PlayerState, kind: str) -> PlayerState:
    """生产: 该类型每张有工人的卡各从供给区得 1 蓝点, 高等级卡优先."""
    category = _category(kind)
    slots = p.buildings.get(category.value, {})
    working = [
        cid for cid, workers in slots.items()
        if workers > 0 and _is_kind(db, cid, category)
    ]
    if not working or p.blue_bank == 0:
        return p
    order = sorted(working, key=lambda cid: (-db.get(cid).token_value, cid))
    tokens = dict(p.card_tokens)
    blue_bank = p.blue_bank
    for cid in order:
        if blue_bank == 0:
            break
        tokens[cid] = tokens.get(cid, 0) + 1
        blue_bank -= 1
    return replace(p, card_tokens=tokens, blue_bank=blue_bank)


def gain_value(db: CardDB, p: PlayerState, kind: str, amount: int) -> PlayerState:
    """按价值获得: 从供给区向该类型最低等级卡放蓝点, 累计价值恰好 amount.

    单点价值超过剩余额时停止(找不齐的部分损失, 与 pay 找零同口径);
    供给不足或场上无该类型卡时尽力而为。用于事件"生产/获得 N 食物或
    资源"(如 border_conflict 产 3 资源、foray 产共 3 食物/资源)。
    """
    category = _category(kind)
    if amount < 0:
        msg = f"amount 须非负, 收到 {amount}"
        raise ValueError(msg)
    ids = _kind_card_ids(db, p, category)
    if not ids or amount == 0 or p.blue_bank == 0:
        return p
    target = min(ids, key=lambda cid: _lowest_key(db, cid))
    value = db.get(target).token_value
    n = min(amount // value, p.blue_bank)
    if n <= 0:
        return p
    tokens = dict(p.card_tokens)
    tokens[target] = tokens.get(target, 0) + n
    return replace(p, card_tokens=tokens, blue_bank=p.blue_bank - n)
