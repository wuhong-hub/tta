"""规则引擎公开接口(P1 重构中: tracks/enums/model/rng/state/actions/legal/apply)."""

from tta.engine.actions import (
    Action,
    Build,
    BuildWonderStage,
    Destroy,
    DevelopGovernment,
    DevelopTech,
    Disband,
    IllegalActionError,
    PassTurn,
    PlayActionCard,
    PlayLeader,
    TakeCard,
    Upgrade,
    action_from_dict,
    action_to_dict,
)
from tta.engine.apply import apply
from tta.engine.enums import (
    UNIT_CATEGORIES,
    URBAN_CATEGORIES,
    WORKER_CATEGORIES,
    Age,
    CardCategory,
    DeckType,
    SpecialType,
)
from tta.engine.legal import ROW_COSTS, legal_actions
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
    "ROW_COSTS", "ROW_SLOTS", "UNIT_CATEGORIES", "URBAN_CATEGORIES",
    "WORKER_CATEGORIES", "Action", "Age", "Build", "BuildWonderStage",
    "CardCategory", "CardDB", "CardDefinition", "DeckType", "Destroy",
    "DevelopGovernment", "DevelopTech", "Disband", "GameState",
    "GovernmentStats", "IllegalActionError", "PassTurn", "PendingEffect",
    "PlayActionCard", "PlayLeader", "PlayerState", "SpecialType", "TakeCard",
    "Upgrade", "action_from_dict", "action_to_dict", "apply",
    "consumption_value", "corruption_value", "from_dict",
    "happiness_required", "legal_actions", "population_cost",
    "replace_player", "rng_below", "rng_shuffle", "state_hash", "to_dict",
    "workers_total",
]
