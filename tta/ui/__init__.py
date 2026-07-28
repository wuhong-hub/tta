"""人类玩家界面视图层(纯渲染函数, 无 IO; 仅依赖 engine 公开接口)."""

from tta.ui.render import (
    describe_action,
    hidden_summary,
    render_actions,
    render_game,
)

__all__ = ["describe_action", "hidden_summary", "render_actions", "render_game"]
