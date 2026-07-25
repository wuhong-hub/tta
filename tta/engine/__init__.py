"""规则引擎公开接口(P1 重构中: 当前导出 tracks/enums/model/rng/state)."""

from tta.engine.enums import (
    UNIT_CATEGORIES,
    URBAN_CATEGORIES,
    WORKER_CATEGORIES,
    Age,
    CardCategory,
    DeckType,
    SpecialType,
)
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.rng import rng_below, rng_shuffle
from tta.engine.state import (
    ROW_SLOTS,
    GameState,
    PendingEffect,
    PlayerState,
    from_dict,
    replace_player,
    state_hash,
    to_dict,
    workers_total,
)
from tta.engine.tracks import (
    consumption_value,
    corruption_value,
    happiness_required,
    population_cost,
)

__all__ = [
    "ROW_SLOTS", "UNIT_CATEGORIES", "URBAN_CATEGORIES", "WORKER_CATEGORIES",
    "Age", "CardCategory", "CardDB", "CardDefinition", "DeckType",
    "GameState", "GovernmentStats", "PendingEffect", "PlayerState",
    "SpecialType", "consumption_value", "corruption_value", "from_dict",
    "happiness_required", "population_cost", "replace_player", "rng_below",
    "rng_shuffle", "state_hash", "to_dict", "workers_total",
]
