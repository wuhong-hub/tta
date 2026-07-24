"""规则引擎公开接口."""

from tta.engine.actions import (
    Action,
    Build,
    Develop,
    IllegalActionError,
    IncreasePopulation,
    PassTurn,
    PlayActionCard,
    TakeCard,
)
from tta.engine.apply import apply, happiness, strength
from tta.engine.legal import legal_actions
from tta.engine.model import CardDB, CardDefinition, GovernmentStats
from tta.engine.setup import new_game
from tta.engine.state import GameState, PlayerState, from_dict, state_hash, to_dict

__all__ = [
    "Action", "Build", "CardDB", "CardDefinition", "Develop", "GameState",
    "GovernmentStats", "IllegalActionError", "IncreasePopulation", "PassTurn",
    "PlayActionCard", "PlayerState", "TakeCard", "apply", "from_dict",
    "happiness", "legal_actions", "new_game", "state_hash", "strength", "to_dict",
]
