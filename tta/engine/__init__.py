"""规则引擎公开接口.

P1: tracks/enums/model/rng/state/actions/legal/apply/setup
+ civ(文明数值)/effects(效果钩子)/economy(资源支付)/turn(回合机)。
"""

from tta.engine.actions import (
    Action,
    Build,
    BuildWonderStage,
    CancelPact,
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
    IllegalActionError,
    IncreasePopulation,
    PactAccept,
    PactReject,
    PassResponse,
    PassTurn,
    PlayActionCard,
    PlayAggression,
    PlayDefenseBonus,
    PlayLeader,
    PlayTactics,
    ProposePact,
    Resign,
    SeedEvent,
    SkipPolitics,
    TakeCard,
    Upgrade,
    action_from_dict,
    action_to_dict,
)
from tta.engine.apply import apply
from tta.engine.civ import (
    CivValues,
    civ_values,
    discontent,
    hand_limit_civil,
    is_uprising,
)
from tta.engine.economy import (
    food_total,
    gain_tokens,
    pay,
    produce,
    resource_total,
    settle_loss,
)
from tta.engine.effects import static_bonuses, turn_start_discounts
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
from tta.engine.setup import new_game
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
from tta.engine.turn import advance

__all__ = [
    "ROW_COSTS", "ROW_SLOTS", "UNIT_CATEGORIES", "URBAN_CATEGORIES",
    "WORKER_CATEGORIES", "Action", "Age", "Build", "BuildWonderStage",
    "CancelPact", "CardCategory", "CardDB", "CardDefinition",
    "ChooseEventOption", "ChooseTurnStart", "CivValues", "ColonizeBid",
    "ColonizePass", "ColonizePlayBonus", "ColonizeSacrifice", "CopyTactics",
    "DeckType", "DeclareWar", "DeclineResponse", "Destroy",
    "DevelopGovernment", "DevelopTech", "Disband", "DiscardForStrength",
    "DiscardMilitary", "GameState", "GovernmentStats", "IllegalActionError",
    "IncreasePopulation", "PactAccept", "PactReject", "PassResponse",
    "PassTurn", "PendingEffect", "PlayActionCard", "PlayAggression",
    "PlayDefenseBonus", "PlayLeader", "PlayTactics", "PlayerState",
    "ProposePact", "Resign", "SeedEvent", "SkipPolitics", "SpecialType",
    "TakeCard", "Upgrade", "action_from_dict", "action_to_dict",
    "advance", "apply", "civ_values", "consumption_value", "corruption_value",
    "discontent", "food_total", "from_dict", "gain_tokens",
    "hand_limit_civil", "happiness_required", "is_uprising", "legal_actions",
    "new_game", "pay", "population_cost", "produce", "replace_player",
    "resource_total", "rng_below", "rng_shuffle", "settle_loss",
    "state_hash", "static_bonuses", "to_dict", "turn_start_discounts",
    "workers_total",
]
