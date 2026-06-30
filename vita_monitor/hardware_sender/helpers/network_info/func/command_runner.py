from __future__ import annotations

import locale
import os
import re
import subprocess
import sys
from typing import List, Optional, Tuple


class CommandRunner:
    """跨平台子进程封装：对控制台输出做多编码尝试并择优解码（Windows/Linux、中英文等）。"""

    @staticmethod
    def _encoding_candidates() -> Tuple[str, ...]:
        encs: List[str] = []
        if sys.platform == "win32":
            encs.extend(["utf-8", "utf-8-sig", "cp65001", "gbk", "cp936", "mbcs", "latin-1"])
        else:
            for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
                v = os.environ.get(name)
                if v and "." in v:
                    enc = v.split(".", 1)[-1].strip()
                    if enc and enc.lower() not in {e.lower() for e in encs}:
                        encs.append(enc)
            try:
                pref = locale.getpreferredencoding(False)
                if pref and pref.lower() not in {e.lower() for e in encs}:
                    encs.append(pref)
            except Exception:
                pass
            encs.extend(["utf-8", "C.UTF-8", "latin-1"])
        seen: set[str] = set()
        out: List[str] = []
        for e in encs:
            k = e.lower()
            if k not in seen:
                seen.add(k)
                out.append(e)
        return tuple(out)

    @staticmethod
    def _decode_quality_score(text: str) -> int:
        if not text:
            return -10_000
        score = 0
        score -= text.count("\ufffd") * 200
        n = len(text)
        if n:
            printable = sum(1 for c in text if c.isprintable() or c in "\n\r\t")
            score += int(80 * printable / n)
        if re.search(
            r"(?i)(ttl|icmp|ping|loss|transmitted|received|time|ms|rtt|"
            r"mdev|min/avg|average|minimum|maximum|统计|丢失|时间|数据包|"
            r"packets?|verlust|perte|perdidos|persi|transmis|re[cç]us)",
            text,
        ):
            score += 120
        if re.search(r"(?i)(netsh|wlan|ipconfig|route|ip\s+route|iw\s+dev)", text):
            score += 40
        return score

    @staticmethod
    def _decode_cmd_output(data: bytes) -> str:
        if not data:
            return ""
        best: Optional[Tuple[int, str]] = None
        for enc in CommandRunner._encoding_candidates():
            try:
                s = data.decode(enc, errors="strict")
            except (UnicodeDecodeError, LookupError):
                continue
            q = CommandRunner._decode_quality_score(s)
            if best is None or q > best[0]:
                best = (q, s)
        if best is not None:
            return best[1]
        if sys.platform == "win32":
            try:
                return data.decode("gbk", errors="replace")
            except LookupError:
                pass
        return data.decode("utf-8", errors="replace")

    @staticmethod
    def run(argv: List[str], timeout: float = 8.0, sudo_password: Optional[str] = None) -> Tuple[str, int]:
        """执行子进程命令。若提供 sudo_password，则自动在命令前加 sudo -S 并通过 stdin 传入密码。"""
        # 需要使用 sudo 的情况：提供了密码且命令本身不以 sudo 开头
        stdin_data = None
        if sudo_password and argv and not argv[0].endswith("sudo"):
            argv = ["sudo", "-S"] + argv
            stdin_data = (sudo_password + "\n").encode("utf-8")
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                timeout=timeout,
                input=stdin_data,
            )
            raw = (proc.stdout or b"") + (proc.stderr or b"")
            out = CommandRunner._decode_cmd_output(raw)
            return out.strip(), proc.returncode
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            return "", -1
