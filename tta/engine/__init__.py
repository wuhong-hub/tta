"""规则引擎公开接口(P1 重构中: 当前仅导出 tracks/enums/model/rng)."""

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
from tta.engine.tracks import (
    consumption_value,
    corruption_value,
    happiness_required,
    population_cost,
)

__all__ = [
    "UNIT_CATEGORIES", "URBAN_CATEGORIES", "WORKER_CATEGORIES",
    "Age", "CardCategory", "CardDB", "CardDefinition", "DeckType",
    "GovernmentStats", "SpecialType",
    "consumption_value", "corruption_value", "happiness_required",
    "population_cost", "rng_below", "rng_shuffle",
]
