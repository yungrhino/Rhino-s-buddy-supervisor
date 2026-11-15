"""System metrics exposed to widgets as a flat dict of names -> numbers/strings.

Always available (psutil): cpu, ram, ram_used_gb, ram_total_gb, disk, net_*, battery.
Optional (see sensors.py): cpu_temp, gpu, gpu_temp, gpu_mem, gpu_mem_used_gb, gpu_mem_total_gb.
A reading that is not available is ``nan`` and is shown as "--" by text widgets.
"""

from __future__ import annotations

import math
import os
import time
from collections import defaultdict

import psutil

from . import sensors

NAN = float("nan")
OPTIONAL = ("cpu_temp", "gpu", "gpu_temp", "gpu_mem", "gpu_mem_used_gb", "gpu_mem_total_gb")


def human_rate(kb_per_s: float) -> str:
    """Auto-unit transfer rate: '350 KB/s', '1.2 MB/s' (the text widget turns '.' into ',')."""
    if kb_per_s >= 1024 * 1024:
        return f"{kb_per_s / 1024 / 1024:.1f} GB/s"
    if kb_per_s >= 1024:
        return f"{kb_per_s / 1024:.1f} MB/s"
    return f"{kb_per_s:.0f} KB/s"


# Deadband per metric: (level 1, level 2) absolute change needed before the shown value moves.
DEADBAND = {
    "cpu": (2.0, 5.0), "gpu": (2.0, 5.0), "ram": (1.0, 2.0), "disk": (1.0, 2.0), "gpu_mem": (1.0, 2.0),
    "cpu_temp": (1.0, 2.0), "gpu_temp": (1.0, 2.0), "battery": (1.0, 2.0),
    "ram_used_gb": (0.1, 0.2), "gpu_mem_used_gb": (0.1, 0.2),
}
# Network rates: relative change and absolute floor (KB/s) per level.
NET_BAND = {1: (0.25, 8.0), 2: (0.5, 25.0)}
NET_KEYS = ("net_down_kbs", "net_up_kbs")


class Metrics:
    """Samples psutil lazily and at most once per ``min_interval`` seconds."""

    def __init__(self, cfg: dict | None = None, min_interval: float = 0.5):
        cfg = cfg or {}
        self.min_interval = min_interval
        self._t = 0.0
        self._data: dict = {}
        self._net = psutil.net_io_counters()
        self._net_t = time.monotonic()
        self.history: dict[str, list[float]] = defaultdict(list)
        self.stability = 1
        self._shown: dict = {}
        psutil.cpu_percent(None)  # prime
        self.pollers: list[sensors.Poller] = []
        if cfg.get("nvidia_smi", True):
            self.pollers.append(sensors.Poller("nvidia-smi", sensors.fetch_nvidia_smi, 2.0))
        if cfg.get("lhm", True):
            url = cfg.get("lhm_url", "http://127.0.0.1:8085/data.json")
            self.pollers.append(sensors.Poller("LibreHardwareMonitor", lambda: sensors.fetch_lhm(url), 2.0))
        for p in self.pollers:
            p.start()

    def set_stability(self, level: int) -> None:
        """0 = show every reading, 1 = ignore tiny wobbles (default), 2 = even calmer."""
        self.stability = max(0, min(2, int(level)))
        self._shown = {}

    def _publish(self, raw: dict) -> dict:
        """Keep the previously shown value unless the reading moved enough to matter.

        Every changed digit costs a USB redraw (~128 KB/s link), so jitter is not worth showing."""
        lvl = self.stability
        out = dict(raw)
        if lvl > 0:
            shown = self._shown
            for k, (b1, b2) in DEADBAND.items():
                v = raw.get(k)
                if not isinstance(v, (int, float)) or math.isnan(v):
                    shown.pop(k, None)
                    continue
                old = shown.get(k)
                if old is None or abs(v - old) >= (b1, b2)[lvl - 1]:
                    shown[k] = v
                out[k] = shown[k]
            rel, floor = NET_BAND[lvl]
            for k in NET_KEYS:
                v = raw.get(k)
                if not isinstance(v, (int, float)) or math.isnan(v):
                    continue
                old = shown.get(k)
                if old is None or abs(v - old) > max(floor, rel * old):
                    shown[k] = v
                out[k] = shown[k]
        for k in NET_KEYS:
            if k in out:
                out[k.replace("_kbs", "_mbps")] = out[k] * 8 / 1024
                out[k.replace("_kbs", "_h")] = human_rate(out[k])
        self._data = out
        return out

    def stop(self) -> None:
        for p in self.pollers:
            p.stop()

    def get(self) -> dict:
        now = time.monotonic()
        if now - self._t >= self.min_interval:
            self._sample(now)
        return self._data

    def _sample(self, now: float) -> None:
        d: dict = {}
        d["cpu"] = psutil.cpu_percent(None)
        vm = psutil.virtual_memory()
        d["ram"] = vm.percent
        d["ram_used_gb"] = vm.used / 2**30
        d["ram_total_gb"] = vm.total / 2**30
        try:
            d["disk"] = psutil.disk_usage(os.path.abspath(os.sep)).percent
        except Exception:
            d["disk"] = 0.0
        net = psutil.net_io_counters()
        dt = max(now - self._net_t, 1e-6)
        d["net_down_kbs"] = (net.bytes_recv - self._net.bytes_recv) / 1024 / dt
        d["net_up_kbs"] = (net.bytes_sent - self._net.bytes_sent) / 1024 / dt
        d["net_down_mbps"] = d["net_down_kbs"] * 8 / 1024
        d["net_up_mbps"] = d["net_up_kbs"] * 8 / 1024
        d["net_down_h"] = human_rate(d["net_down_kbs"])
        d["net_up_h"] = human_rate(d["net_up_kbs"])
        self._net, self._net_t = net, now
        d["cpu_temp"] = self._psutil_cpu_temp()
        try:
            b = psutil.sensors_battery()
            d["battery"] = b.percent if b else 0.0
        except Exception:
            d["battery"] = 0.0
        for k in OPTIONAL:
            d.setdefault(k, NAN)
        # External sources override psutil where they have a real reading.
        for p in self.pollers:
            for k, v in dict(p.data).items():
                if not (isinstance(v, float) and math.isnan(v)):
                    d[k] = v
        self._t = now
        self._publish(d)
        for k, v in d.items():
            if isinstance(v, (int, float)) and not math.isnan(v):
                h = self.history[k]
                h.append(float(v))
                del h[:-240]

    @staticmethod
    def _psutil_cpu_temp() -> float:
        try:
            temps = psutil.sensors_temperatures()
        except Exception:  # not available on Windows/macOS
            return NAN
        for key in ("coretemp", "k10temp", "cpu_thermal", "zenpower"):
            if key in temps and temps[key]:
                return float(temps[key][0].current)
        for entries in temps.values():
            if entries:
                return float(entries[0].current)
        return NAN
