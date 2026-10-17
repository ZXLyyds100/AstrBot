"""Synthetic plugin used only for local configuration-file preview acceptance."""

from astrbot.api.star import Context, Star, register
from astrbot.core.config.astrbot_config import AstrBotConfig


@register(
    "preview_fixture",
    "Local acceptance fixture",
    "Synthetic uploaded images; no model or messaging service is configured.",
    "1.0.0",
)
class PreviewFixture(Star):
    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config
