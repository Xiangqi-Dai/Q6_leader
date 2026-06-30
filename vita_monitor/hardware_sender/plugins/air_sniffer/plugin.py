from __future__ import annotations

import json
import logging
import time
from typing import Any
from urllib.request import Request, urlopen

from plugins.plugin_base import BaseVitalPlugin

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 风险评估阈值（参考国标 GB/T 18883-2022）
# ---------------------------------------------------------------------------
_THRESHOLDS: dict[str, dict[str, Any]] = {
    # --- 线性阈值（浓度越低越好） ---
    "co2":    {"good": 1000, "bad": 2000, "invert": False, "unit": "ppm",
               "label": "CO₂", "warning_msg": "CO₂浓度偏高，建议通风。",
               "danger_msg": "CO₂浓度过高，请立即通风！"},
    "hcho":   {"good": 80,   "bad": 100,  "invert": False, "unit": "ug/m³",
               "label": "甲醛", "warning_msg": "甲醛浓度偏高，建议通风。",
               "danger_msg": "甲醛浓度过高，请立即通风！"},
    "voc":    {"good": 200,  "bad": 400,  "invert": False, "unit": "ug/m³",
               "label": "VOC", "warning_msg": "VOC浓度偏高，建议通风。",
               "danger_msg": "VOC浓度过高，请立即通风！"},
    "pm25":   {"good": 35,   "bad": 75,   "invert": False, "unit": "ug/m³",
               "label": "PM2.5", "warning_msg": "PM2.5偏高，建议关注空气质量。",
               "danger_msg": "PM2.5过高，请减少暴露！"},
    "pm10":   {"good": 50,   "bad": 150,  "invert": False, "unit": "ug/m³",
               "label": "PM10", "warning_msg": "PM10偏高，建议关注空气质量。",
               "danger_msg": "PM10过高，请减少暴露！"},
    "h2s":    {"good": 7,    "bad": 15,   "invert": False, "unit": "ppm",
               "label": "硫化氢", "warning_msg": "硫化氢浓度偏高，建议通风。",
               "danger_msg": "硫化氢浓度过高，请立即撤离并通风！"},
    "co":     {"good": 17,   "bad": 26,   "invert": False, "unit": "ppm",
               "label": "一氧化碳", "warning_msg": "一氧化碳浓度偏高，建议通风。",
               "danger_msg": "一氧化碳浓度过高，请立即通风并撤离！"},
    "so2":    {"good": 2,    "bad": 5,    "invert": False, "unit": "ppm",
               "label": "二氧化硫", "warning_msg": "二氧化硫浓度偏高，建议通风。",
               "danger_msg": "二氧化硫浓度过高，请立即防护！"},
    "no2":    {"good": 3,    "bad": 5,    "invert": False, "unit": "ppm",
               "label": "二氧化氮", "warning_msg": "二氧化氮浓度偏高，建议通风。",
               "danger_msg": "二氧化氮浓度过高，请立即防护！"},
    "ch4":    {"good": 10,   "bad": 25,   "invert": False, "unit": "%LEL",
               "label": "甲烷", "warning_msg": "可燃气浓度偏高，注意排查泄漏。",
               "danger_msg": "可燃气浓度达到危险级，立即排查并撤离！"},
    "nh3":    {"good": 29,   "bad": 43,   "invert": False, "unit": "ppm",
               "label": "氨气", "warning_msg": "氨气浓度偏高，建议通风。",
               "danger_msg": "氨气浓度过高，请立即防护！"},
    "ph3":    {"good": 0.05, "bad": 0.3,  "invert": False, "unit": "ppm",
               "label": "磷化氢", "warning_msg": "磷化氢浓度偏高，剧毒请注意。",
               "danger_msg": "磷化氢浓度过高，剧毒请立即撤离！"},
    "eto":    {"good": 1,    "bad": 2,    "invert": False, "unit": "ppm",
               "label": "环氧乙烷", "warning_msg": "环氧乙烷浓度偏高，注意通风。",
               "danger_msg": "环氧乙烷浓度过高，请立即撤离！"},
    # --- 区间阈值（过低过高都危险） ---
    "temperature": {"good_range": (15.0, 30.0), "bad_range": (5.0, 38.0),
                    "unit": "℃", "label": "温度",
                    "warning_msg": "温度偏离舒适区间，建议关注。",
                    "danger_msg": "温度严重偏离，请注意环境！"},
    "humidity":    {"good_range": (30.0, 70.0), "bad_range": (20.0, 80.0),
                    "unit": "%RH", "label": "湿度",
                    "warning_msg": "湿度偏离舒适区间，建议关注。",
                    "danger_msg": "湿度严重偏离，请注意环境！"},
    "o2":          {"good_range": (19.5, 23.5), "bad_range": (18.0, 25.0),
                    "unit": "%vol", "label": "氧气",
                    "warning_msg": "氧气浓度偏离正常区间（19.5~23.5%），建议关注。",
                    "danger_msg": "氧气浓度异常（缺氧/富氧），请立即处置！"},
}


def _score_linear(value: float, good: float, bad: float) -> float:
    """线性映射：value <= good -> 0, value >= bad -> 100"""
    if value <= good:
        return 0.0
    if value >= bad:
        return 100.0
    return (value - good) / (bad - good) * 100.0


def _score_range(value: float, good_lo: float, good_hi: float,
                 bad_lo: float, bad_hi: float) -> float:
    """区间映射：在 good 范围内 -> 0, 超出 bad 范围 -> 100"""
    if good_lo <= value <= good_hi:
        return 0.0
    if value < bad_lo:
        if bad_lo == good_lo:
            return 100.0
        return min(100.0, (good_lo - value) / (good_lo - bad_lo) * 100.0)
    # value > good_hi
    if bad_hi == good_hi:
        return 100.0
    return min(100.0, (value - good_hi) / (bad_hi - good_hi) * 100.0)


def _assess_risk(data: dict[str, float]) -> tuple[str, float, str, str]:
    """
    根据各项指标计算风险等级。
    返回 (risk_level, risk_score, main_factor, summary)
    """
    scores: dict[str, float] = {}

    for key, th in _THRESHOLDS.items():
        val = data.get(key)
        if val is None:
            continue

        if "good_range" in th:
            scores[key] = _score_range(
                val, th["good_range"][0], th["good_range"][1],
                th["bad_range"][0], th["bad_range"][1],
            )
        else:
            scores[key] = _score_linear(val, th["good"], th["bad"])

    if not scores:
        return "normal", 0.0, "", "数据不足，无法评估。"

    main_factor = max(scores, key=lambda k: scores[k])
    risk_score = round(scores[main_factor], 1)

    if risk_score > 70:
        risk_level = "danger"
    elif risk_score > 40:
        risk_level = "warning"
    else:
        risk_level = "normal"

    th = _THRESHOLDS[main_factor]
    if risk_level == "danger":
        summary = th.get("danger_msg", "空气质量异常，请注意！")
    elif risk_level == "warning":
        summary = th.get("warning_msg", "部分指标偏高，建议关注。")
    else:
        summary = "空气质量正常。"

    return risk_level, risk_score, main_factor, summary


class AirSnifferVitalPlugin(BaseVitalPlugin):
    """AIR-MOD-001 七合一空气传感器数据采集插件。"""

    vita_type = "air_sniffer"
    vita_data_schema: dict[str, Any] = {
        "status": "str",         # ok | error
        "sensor_url": "str",
        "sampled_at": "float",
        "co2": "int",            # ppm
        "hcho": "int",           # ug/m³
        "voc": "int",            # ug/m³
        "pm25": "int",           # ug/m³
        "pm10": "int",           # ug/m³
        "temperature": "float",  # ℃
        "humidity": "float",     # %RH
        "o2": "float",           # %vol
        "h2s": "int",            # ppm
        "co": "int",             # ppm
        "so2": "float",          # ppm
        "no2": "float",          # ppm
        "ch4": "int",            # %LEL
        "nh3": "int",            # ppm
        "ph3": "float",          # ppm
        "eto": "float",          # ppm
        "risk_level": "str",     # normal | warning | danger
        "risk_score": "float",   # 0~100
        "main_factor": "str",
        "summary": "str",
        "error": "str",
    }

    def __init__(self, *, info_pool: Any, interval_sec: float, qos: int = 0, **kwargs: Any) -> None:
        super().__init__(info_pool=info_pool, interval_sec=interval_sec, qos=qos, **kwargs)
        self._sensor_url = str(kwargs.get("sensor_url", "http://192.168.8.89/api/sensor")).strip()
        self._timeout_sec = float(kwargs.get("timeout_sec", 3.0))
        self._last_payload: dict[str, Any] = {
            "status": "error",
            "sensor_url": self._sensor_url,
            "sampled_at": 0.0,
            "co2": 0,
            "hcho": 0,
            "voc": 0,
            "pm25": 0,
            "pm10": 0,
            "temperature": 0.0,
            "humidity": 0.0,
            "o2": 0.0,
            "h2s": 0,
            "co": 0,
            "so2": 0.0,
            "no2": 0.0,
            "ch4": 0,
            "nh3": 0,
            "ph3": 0.0,
            "eto": 0.0,
            "risk_level": "normal",
            "risk_score": 0.0,
            "main_factor": "",
            "summary": "",
            "error": "no data yet",
        }

    def _fetch_sensor(self) -> dict[str, float]:
        """从 sensor_url 读取 JSON，返回解析后的字典。失败抛异常。"""
        req = Request(self._sensor_url, method="GET")
        with urlopen(req, timeout=self._timeout_sec) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw)

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        """将值转为 float，非法值返回 default。"""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def collect_real_vita_data(self) -> dict[str, Any]:
        """采集一次空气数据并评估风险；失败时返回上次快照。"""
        try:
            raw = self._fetch_sensor()
            sampled_at = time.time()

            co2    = int(self._safe_float(raw.get("co2")))
            hcho   = int(self._safe_float(raw.get("hcho")))
            voc    = int(self._safe_float(raw.get("voc")))
            pm25   = int(self._safe_float(raw.get("pm25")))
            pm10   = int(self._safe_float(raw.get("pm10")))
            temperature = self._safe_float(raw.get("temperature"))
            humidity    = self._safe_float(raw.get("humidity"))
            o2  = self._safe_float(raw.get("o2"))
            h2s = int(self._safe_float(raw.get("h2s")))
            co  = int(self._safe_float(raw.get("co")))
            so2 = self._safe_float(raw.get("so2"))
            no2 = self._safe_float(raw.get("no2"))
            ch4 = int(self._safe_float(raw.get("ch4")))
            nh3 = int(self._safe_float(raw.get("nh3")))
            ph3 = self._safe_float(raw.get("ph3"))
            eto = self._safe_float(raw.get("eto"))

            metrics = {
                "co2": co2, "hcho": hcho, "voc": voc,
                "pm25": pm25, "pm10": pm10,
                "temperature": temperature, "humidity": humidity,
                "o2": o2, "h2s": h2s, "co": co, "so2": so2, "no2": no2,
                "ch4": ch4, "nh3": nh3, "ph3": ph3, "eto": eto,
            }
            risk_level, risk_score, main_factor, summary = _assess_risk(metrics)

            out: dict[str, Any] = {
                "status": "ok",
                "sensor_url": self._sensor_url,
                "sampled_at": sampled_at,
                "co2": co2,
                "hcho": hcho,
                "voc": voc,
                "pm25": pm25,
                "pm10": pm10,
                "temperature": temperature,
                "humidity": humidity,
                "o2": o2,
                "h2s": h2s,
                "co": co,
                "so2": so2,
                "no2": no2,
                "ch4": ch4,
                "nh3": nh3,
                "ph3": ph3,
                "eto": eto,
                "risk_level": risk_level,
                "risk_score": risk_score,
                "main_factor": main_factor,
                "summary": summary,
                "error": "",
            }
            self._last_payload = out
            return dict(out)

        except Exception as exc:
            logger.exception("air_sniffer 采集失败")
            out = dict(self._last_payload)
            out["status"] = "error"
            out["error"] = str(exc)[:120]
            return out

    def collect_mock_vita_data(self) -> dict[str, Any]:
        from plugins.air_sniffer.mock_generator import generate_air_sniffer_mock

        out = generate_air_sniffer_mock(self.mock_config, sensor_url=self._sensor_url)
        self._last_payload = out
        return dict(out)
