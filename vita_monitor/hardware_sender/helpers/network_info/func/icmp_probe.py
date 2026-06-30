from __future__ import annotations

import math
import platform
import re
import statistics
from typing import List, Optional, Tuple

from .command_runner import CommandRunner

# 与 docs/plugins/1. heartbeat.md 约定一致：公网 ICMP 双目标均失败时的断联哨兵
ICMP_COMPLETE_FAILURE_LATENCY_MS = 460.0
ICMP_COMPLETE_FAILURE_JITTER_MS = 100.0
# 与 docs/plugins/5. ip_peer_monitor.md 约定一致：对端探测失败哨兵
PEER_FAILURE_LATENCY_MS = 999


class IcmpProbe:
    """跨平台 ICMP ping 命令构造与输出解析；供公网与对端 IP 探测共用。"""

    @staticmethod
    def ping_argv(host: str, *, ping_count: int = 3, ping_timeout_sec: float = 2.0) -> List[str]:
        count = max(1, int(ping_count))
        sysname = platform.system().lower()
        if sysname == "windows":
            return ["ping", "-4", "-n", str(count), host]
        if sysname == "darwin":
            wait_ms = max(1, int(math.ceil(ping_timeout_sec * 1000)))
            return ["ping", "-c", str(count), "-W", str(wait_ms), host]
        wait_sec = max(1, int(math.ceil(ping_timeout_sec)))
        return ["ping", "-c", str(count), "-W", str(wait_sec), host]

    @staticmethod
    def measure(
        host: str,
        *,
        ping_count: int = 3,
        ping_timeout_sec: float = 2.0,
    ) -> Tuple[float, float, float, bool]:
        """
        对单个主机执行 ICMP 探测。

        Returns:
            ``(latency_ms, packet_loss_rate, jitter_ms, ok)``
        """
        argv = IcmpProbe.ping_argv(host, ping_count=ping_count, ping_timeout_sec=ping_timeout_sec)
        timeout = max(float(ping_timeout_sec) + 1.0, 2.0)
        out, _code = CommandRunner.run(argv, timeout=timeout)
        if not (out and out.strip()):
            return 0.0, 1.0, 0.0, False
        lat, loss, jit, ok = IcmpProbe.parse_ping_output(out)
        return float(lat or 0.0), float(loss), float(jit or 0.0), ok

    @staticmethod
    def parse_ping_output(text: str) -> Tuple[Optional[float], float, Optional[float], bool]:
        samples = IcmpProbe._collect_rtt_samples(text)
        loss = IcmpProbe._parse_packet_loss(text)

        latency: Optional[float] = None
        jitter: Optional[float] = None

        if len(samples) >= 1:
            latency = statistics.mean(samples)
            jitter = statistics.pstdev(samples) if len(samples) >= 2 else 0.0
        else:
            lat2, jit2 = IcmpProbe._parse_summary_latency_jitter(text)
            latency, jitter = lat2, jit2

        if jitter is None:
            jitter = 0.0
        if latency is None:
            latency = 0.0

        ok = bool(samples) or bool(
            re.search(
                r"(?i)(Average|平均|Moyenne|Media|Mittelwert|Durchschnitt|rtt\s+min|min/avg|"
                r"Ping\s+statistics|ping\s+statistics|统计信息|Approximate\s+round\s+trip|"
                r"Approximative\s+round\s+trip|packet\s+loss|丢失|Verlust|perte|transmitted|re[cç]us)",
                text,
            )
        )
        return latency, loss, jitter, ok

    @staticmethod
    def _collect_rtt_samples(text: str) -> List[float]:
        samples: List[float] = []
        for m in re.finditer(r"time[<=](\d+(?:\.\d+)?)\s*ms", text, flags=re.IGNORECASE):
            samples.append(float(m.group(1)))
        for _ in re.finditer(r"time<\s*1\s*ms", text, flags=re.IGNORECASE):
            samples.append(0.5)
        for m in re.finditer(r"时间[<=＝](\d+(?:\.\d+)?)\s*ms", text):
            samples.append(float(m.group(1)))
        for _ in re.finditer(r"时间<\s*1\s*ms", text):
            samples.append(0.5)
        for m in re.finditer(r"temps[<=](\d+(?:\.\d+)?)\s*ms", text, flags=re.IGNORECASE):
            samples.append(float(m.group(1)))
        for _ in re.finditer(r"temps<\s*1\s*ms", text, flags=re.IGNORECASE):
            samples.append(0.5)
        for m in re.finditer(r"Zeit[<=]\s*(\d+(?:\.\d+)?)\s*ms", text, flags=re.IGNORECASE):
            samples.append(float(m.group(1)))
        for _ in re.finditer(r"Zeit<\s*1\s*ms", text, flags=re.IGNORECASE):
            samples.append(0.5)
        for m in re.finditer(r"tempo[<=](\d+(?:\.\d+)?)\s*ms", text, flags=re.IGNORECASE):
            samples.append(float(m.group(1)))
        for m in re.finditer(r"tijd[<=](\d+(?:\.\d+)?)\s*ms", text, flags=re.IGNORECASE):
            samples.append(float(m.group(1)))
        for m in re.finditer(r"tiempo[<=](\d+(?:\.\d+)?)\s*ms", text, flags=re.IGNORECASE):
            samples.append(float(m.group(1)))
        for m in re.finditer(r"retardo[<=](\d+(?:\.\d+)?)\s*ms", text, flags=re.IGNORECASE):
            samples.append(float(m.group(1)))
        return samples

    @staticmethod
    def _parse_summary_latency_jitter(text: str) -> Tuple[Optional[float], Optional[float]]:
        m_lin = re.search(
            r"(?:rtt|round-trip)\s+min/avg/max/(?:mdev|stddev)\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)(?:/([\d.]+))?\s*ms",
            text,
            flags=re.IGNORECASE,
        )
        if m_lin:
            jit_v = float(m_lin.group(4)) if m_lin.group(4) else None
            return float(m_lin.group(2)), jit_v
        m_lin2 = re.search(
            r"(?:(?:rtt|round-trip)\s+)?min/avg/max/(?:mdev|stddev)\s*=\s*([\d.]+)/([\d.]+)/([\d.]+)(?:/([\d.]+))?\s*ms",
            text,
            flags=re.IGNORECASE,
        )
        if m_lin2:
            jit_v = float(m_lin2.group(4)) if m_lin2.group(4) else None
            return float(m_lin2.group(2)), jit_v
        m_win = re.search(
            r"Minimum\s*=\s*(\d+(?:\.\d+)?)\s*ms.*?Maximum\s*=\s*(\d+(?:\.\d+)?)\s*ms.*?Average\s*=\s*(\d+(?:\.\d+)?)\s*ms",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m_win:
            lo, hi, avg = float(m_win.group(1)), float(m_win.group(2)), float(m_win.group(3))
            return avg, max(0.0, (hi - lo) / 2.0)
        m_cn = re.search(
            r"最短\s*[=＝]\s*(\d+(?:\.\d+)?)\s*ms.*?最长\s*[=＝]\s*(\d+(?:\.\d+)?)\s*ms.*?平均\s*[=＝]\s*(\d+(?:\.\d+)?)\s*ms",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m_cn:
            lo, hi, avg = float(m_cn.group(1)), float(m_cn.group(2)), float(m_cn.group(3))
            return avg, max(0.0, (hi - lo) / 2.0)
        m_de = re.search(
            r"Mindestwert\s*=\s*(\d+(?:\.\d+)?)\s*ms.*?Höchstwert\s*=\s*(\d+(?:\.\d+)?)\s*ms.*?"
            r"(?:Mittelwert|Durchschnitt)\s*=\s*(\d+(?:\.\d+)?)\s*ms",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m_de:
            lo, hi, avg = float(m_de.group(1)), float(m_de.group(2)), float(m_de.group(3))
            return avg, max(0.0, (hi - lo) / 2.0)
        m_fr = re.search(
            r"Minimum\s*=\s*(\d+(?:\.\d+)?)\s*ms.*?Maximum\s*=\s*(\d+(?:\.\d+)?)\s*ms.*?Moyenne\s*=\s*(\d+(?:\.\d+)?)\s*ms",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m_fr:
            lo, hi, avg = float(m_fr.group(1)), float(m_fr.group(2)), float(m_fr.group(3))
            return avg, max(0.0, (hi - lo) / 2.0)
        m_es = re.search(
            r"Mínimo\s*=\s*(\d+(?:\.\d+)?)\s*ms.*?Máximo\s*=\s*(\d+(?:\.\d+)?)\s*ms.*?Media\s*=\s*(\d+(?:\.\d+)?)\s*ms",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if m_es:
            lo, hi, avg = float(m_es.group(1)), float(m_es.group(2)), float(m_es.group(3))
            return avg, max(0.0, (hi - lo) / 2.0)
        return None, None

    @staticmethod
    def _parse_packet_loss(text: str) -> float:
        pct_patterns = (
            r"\(\s*(\d+(?:\.\d+)?)\s*%\s*loss\s*\)",
            r"(\d+(?:\.\d+)?)\s*%\s*packet\s*loss",
            r"\(\s*(\d+(?:\.\d+)?)\s*%\s*丢失\s*\)",
            r"丢失[^0-9]*(\d+)\s*%",
            r"丢失\s*=\s*\d+\s*\(\s*(\d+(?:\.\d+)?)\s*%\s*丢失",
            r"\(\s*(\d+(?:\.\d+)?)\s*%\s*verlust\s*\)",
            r"(\d+(?:\.\d+)?)\s*%\s*verlust",
            r"\(\s*(\d+(?:\.\d+)?)\s*%\s*perte\s*\)",
            r"(\d+(?:\.\d+)?)\s*%\s*perte",
            r"\(\s*(\d+(?:\.\d+)?)\s*%\s*perdidos\s*\)",
        )
        for pat in pct_patterns:
            m = re.search(pat, text, flags=re.IGNORECASE)
            if m:
                pct = float(m.group(1))
                return max(0.0, min(1.0, pct / 100.0))

        m_cn = re.search(
            r"数据包\s*[:：]\s*已发送\s*[=＝]\s*(\d+)\s*[,，]\s*已接收\s*[=＝]\s*(\d+)",
            text,
            flags=re.IGNORECASE,
        )
        if m_cn:
            sent, recv = int(m_cn.group(1)), int(m_cn.group(2))
            if sent > 0:
                return max(0.0, min(1.0, 1.0 - (recv / sent)))

        for pat in (
            r"(\d+)\s+packets?\s+transmitted.*?(\d+)\s+received.*?(\d+(?:\.\d+)?)\s*%\s*packet\s*loss",
            r"(\d+)\s+packets?\s+transmitted.*?(\d+)\s+packets?\s+received.*?(\d+(?:\.\d+)?)\s*%\s*packet\s*loss",
            r"(\d+)\s+packets?\s+transmitted.*?(\d+)\s+received",
        ):
            m2 = re.search(pat, text, flags=re.IGNORECASE | re.DOTALL)
            if m2:
                sent, recv = int(m2.group(1)), int(m2.group(2))
                if sent > 0:
                    if m2.lastindex is not None and m2.lastindex >= 3 and m2.group(3):
                        return max(0.0, min(1.0, float(m2.group(3)) / 100.0))
                    return max(0.0, min(1.0, 1.0 - (recv / sent)))
        return 0.0
