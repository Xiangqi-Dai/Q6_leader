from __future__ import annotations

import logging

from plugins.plugin_base import BaseVitalPlugin

logger = logging.getLogger(__name__)


def launch_plugins(plugins: list[BaseVitalPlugin]) -> None:
    for plugin in plugins:
        logger.info("launch plugin: %s", plugin.vita_type)
        plugin.launch()


def shutdown_plugins(plugins: list[BaseVitalPlugin]) -> None:
    for plugin in plugins:
        try:
            logger.info("shutdown plugin: %s", plugin.vita_type)
            plugin.shutdown()
        except Exception:
            logger.exception("shutdown plugin failed: %s", plugin.vita_type)
