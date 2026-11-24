"""System metrics exposed to widgets as a flat dict of names -> numbers/strings.

Always available (psutil): cpu, ram, ram_used_gb, ram_total_gb, disk, net_*, battery.
Optional (see sensors.py): cpu_temp, gpu, gpu_temp, gpu_mem, gpu_mem_used_gb, gpu_mem_total_gb.
A reading that is not available is ``nan`` and is shown as "--" by text widgets.
"""

from __future__ import annotations

import math
import os
import sys
import time
from collections import defaultdict

import psutil

from . import sensors

NAN = float("nan")
OPTIONAL = ("cpu_temp", "gpu", "gpu_temp", "gpu_mem", "gpu_mem_used_gb", "gpu_mem_total_gb")


DRIVES_EVERY = 5.0  # seconds between looks at the drives (space changes slowly; listing them is not free)


def list_drives() -> list[dict]:
    """Every mounted drive with its space: ``{id, mount, total_gb, used_gb, free_gb, percent, removable}``.

    Optical drives and unreadable ones are left out.  ``id`` is what a person calls it ("C:" on Windows, the mount point elsewhere)."""
    out, seen = [], set()
    try:
        parts = psutil.disk_partitions(all=False)
    except Exception:
        return out
    for p in parts:
        opts = (p.opts or "").lower()
        if "cdrom" in opts or not p.fstype or p.mountpoint in seen:
            continue
        try:
            u = psutil.disk_usage(p.mountpoint)
        except Exception:  # an empty card reader, a disconnected network drive...
            continue
        if not u.total:
            continue
        seen.add(p.mountpoint)
        mount = p.mountpoint
        ident = mount[:2] if sys.platform == "win32" and len(mount) >= 2 and mount[1] == ":" else mount
        out.append({"id": ident, "mount": mount, "total_gb": u.total / 2**30, "used_gb": u.used / 2**30,
                    "free_gb": u.free / 2**30, "percent": float(u.percent), "removable": "removable" in opts})
    return out


def system_drive_id() -> str:
    root = os.environ.get("SystemDrive") if sys.platform == "win32" else None
    return (root or os.path.abspath(os.sep)).rstrip("\\/") or "/"


def match_drive(drives: list[dict], wanted: str = "") -> dict | None:
    """The drive a person asked for ("C", "c:", "D:\\", "/home"...); empty or "auto" = the drive Windows lives on."""
    w = (wanted or "").strip()
    if not drives:
        return None
    if not w or w.lower() in ("auto", "automatico", "automático"):
        sysid = system_drive_id().lower()
        return next((d for d in drives if d["id"].lower().rstrip("\\/") == sysid or d["mount"].lower().rstrip("\\/") == sysid), drives[0])
    key = w.lower().rstrip("\\/")
    if len(key) == 1 and key.isalpha():
        key += ":"
    return next((d for d in drives if d["id"].lower().rstrip("\\/") == key or d["mount"].lower().rstrip("\\/") == key), None)


def pick_disk_temp(temps: list[dict], drive: dict | None, hint: str = "") -> float:
    """Temperature of the physical disk behind ``drive`` from LibreHardwareMonitor's storage sensors.

    LibreHardwareMonitor knows disks by model name, not by drive letter, so: the name the user typed wins; with a single
    disk it is that one; otherwise the disk whose "Used Space" is closest to the drive's own percentage (within 3 points)."""
    temps = [t for t in (temps or []) if isinstance(t, dict) and isinstance(t.get("temp"), (int, float)) and not math.isnan(t["temp"])]
    if not temps:
        return NAN
    h = (hint or "").strip().lower()
    if h:
        hit = next((t for t in temps if h in str(t.get("name", "")).lower()), None)
        return float(hit["temp"]) if hit else NAN
    if len(temps) == 1:
        return float(temps[0]["temp"])
    if drive:
        close = sorted((abs(t["used"] - drive["percent"]), t) for t in temps if isinstance(t.get("used"), (int, float)) and not math.isnan(t["used"]))
        if close and close[0][0] <= 3.0 and (len(close) == 1 or close[1][0] - close[0][0] > 0.5):
            return float(close[0][1]["temp"])
    return NAN


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
        try:
            self._io = psutil.disk_io_counters()
        except Exception:  # some systems have no disk counters
            self._io = None
        self._drives: list[dict] = []
        self._drives_t = -1e9
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
        if now - self._drives_t >= DRIVES_EVERY:
            self._drives, self._drives_t = list_drives(), now
        d["drives"] = self._drives
        try:  # whole-computer disk activity (Windows does not map the counters to drive letters)
            io = psutil.disk_io_counters()
            if io is not None and self._io is not None:
                d["disk_read_kbs"] = max(0.0, (io.read_bytes - self._io.read_bytes) / 1024 / dt)
                d["disk_write_kbs"] = max(0.0, (io.write_bytes - self._io.write_bytes) / 1024 / dt)
            self._io = io
        except Exception:
            pass
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
        d.setdefault("disk_temps", [])
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
