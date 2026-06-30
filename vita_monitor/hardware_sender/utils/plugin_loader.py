from __future__ import annotations

import importlib
import logging
from typing import Any

from plugins.plugin_base import BaseVitalPlugin
from utils.runtime_config import RuntimeConfig

logger = logging.getLogger(__name__)


def _import_symbol(class_path: str) -> type[BaseVitalPlugin]:
    if ":" not in class_path:
        raise ValueError(f"invalid class path {class_path!r}, expected 'module.path:ClassName'")
    module_path, class_name = class_path.split(":", 1)
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise ImportError(f"class {class_name!r} not found in module {module_path!r}")
    if not isinstance(cls, type) or not issubclass(cls, BaseVitalPlugin):
        raise TypeError(f"{class_path!r} must be subclass of BaseVitalPlugin")
    return cls


def build_enabled_plugins(*, config: RuntimeConfig, info_pool: Any) -> list[BaseVitalPlugin]:
    plugins: list[BaseVitalPlugin] = []
    for vita_type, p in config.sender.plugins.items():
        if not p.enabled:
            continue
        cls = _import_symbol(p.class_path)
        # 将 sudo_password 注入到每个插件的 kwargs，插件自行决定是否使用
        merged_kwargs = dict(p.kwargs)
        if config.sudo_password:
            merged_kwargs["sudo_password"] = config.sudo_password
        plugin = cls(
            info_pool=info_pool,
            interval_sec=p.interval_sec,
            qos=p.qos,
            data_mode=p.data_mode,
            mock_config=p.mock,
            **merged_kwargs,
        )
        if plugin.vita_type != vita_type:
            raise ValueError(
                "config sender.plugins key must equal plugin.vita_type: "
                f"key={vita_type!r}, plugin={plugin.vita_type!r}"
            )
        log_fn = logger.warning if p.data_mode in ("mock", "simulated") else logger.info
        log_fn(
            "plugin registered: vita_type=%s data_mode=%s interval_sec=%s",
            vita_type,
            p.data_mode,
            p.interval_sec,
        )
        plugins.append(plugin)
    return plugins
