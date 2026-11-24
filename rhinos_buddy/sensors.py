"""Hardware sensors that psutil cannot read on Windows (GPU load/temperature, CPU temperature).

Two optional sources, both polled in background threads so the screen never waits on them:

* ``nvidia-smi``            - ships with the NVIDIA driver, no extra install.
* LibreHardwareMonitor      - free; enable *Options > Remote Web Server > Run* and this
                              module reads http://127.0.0.1:8085/data.json.
"""

from __future__ import annotations

import json
import logging
import math
import re
import subprocess
import sys
import threading
import time
import urllib.request

log = logging.getLogger("rhinos_buddy.sensors")
NAN = float("nan")
_NUM = re.compile(r"-?\d+(?:[.,]\d+)?")

# Preferred CPU temperature sensors, best first.
CPU_TEMP_PREFERENCE = (
    "CPU Package", "Core (Tctl/Tdie)", "Core (Tdie)", "Tctl/Tdie", "Core Average", "Core Max", "CPU", "Package",
)


def parse_number(text: str) -> float:
    """'45,5 °C' / '12.3 %' / '-' -> float (nan when there is no reading)."""
    m = _NUM.search(text or "")
    return float(m.group(0).replace(",", ".")) if m else NAN


def _to_gb(text: str) -> float:
    v = parse_number(text)
    if math.isnan(v):
        return NAN
    t = text.upper()
    if "MB" in t or "MIB" in t:
        return v / 1024
    return v  # already GB


# ------------------------------------------------------------ LibreHardwareMonitor
def flatten_lhm(tree: dict) -> list[tuple[tuple[str, ...], str]]:
    """Every leaf sensor as (path of names, raw Value string)."""
    out: list[tuple[tuple[str, ...], str]] = []

    def walk(node, path):
        name = node.get("Text", "")
        kids = node.get("Children") or []
        if "Value" in node and not kids and node["Value"] not in ("", None):
            out.append((path + (name,), str(node["Value"])))
        for k in kids:
            walk(k, path + (name,))

    walk(tree, ())
    return out


def parse_lhm(tree: dict) -> dict:
    """Pick the CPU and GPU readings out of a LibreHardwareMonitor data.json tree.

    Hardware is recognised by its sensors, not by vendor names: a CPU has a
    ``Load / CPU Total`` sensor, a GPU has a ``GPU Core`` sensor.
    """
    hardware: dict[str, dict[tuple[str, str], str]] = {}
    for path, value in flatten_lhm(tree):
        if len(path) < 3:
            continue
        hw, cat, name = path[-3], path[-2], path[-1]
        hardware.setdefault(hw, {})[(cat, name)] = value

    out: dict[str, float] = {}

    for sensors in hardware.values():
        if ("Load", "CPU Total") in sensors:
            out["cpu"] = parse_number(sensors[("Load", "CPU Total")])
            temps = {n: v for (c, n), v in sensors.items() if c == "Temperatures"}
            for pref in CPU_TEMP_PREFERENCE:
                if pref in temps and not math.isnan(parse_number(temps[pref])):
                    out["cpu_temp"] = parse_number(temps[pref])
                    break
            else:
                vals = [parse_number(v) for v in temps.values()]
                vals = [v for v in vals if not math.isnan(v)]
                if vals:
                    out["cpu_temp"] = max(vals)
            break

    gpus = []
    for sensors in hardware.values():
        names = {n for (_, n) in sensors}
        if "GPU Core" in names:
            gpus.append(sensors)
    if gpus:
        def vram(s):  # prefer the discrete card: the one with the most video memory
            v = _to_gb(next((val for (c, n), val in s.items() if n == "GPU Memory Total"), ""))
            return 0 if math.isnan(v) else v

        g = max(gpus, key=vram)
        out["gpu"] = parse_number(g.get(("Load", "GPU Core"), "-"))
        out["gpu_temp"] = parse_number(g.get(("Temperatures", "GPU Core"), "-"))
        used = _to_gb(next((v for (c, n), v in g.items() if n == "GPU Memory Used"), ""))
        total = _to_gb(next((v for (c, n), v in g.items() if n == "GPU Memory Total"), ""))
        out["gpu_mem_used_gb"], out["gpu_mem_total_gb"] = used, total
        if total and not math.isnan(total) and not math.isnan(used):
            out["gpu_mem"] = 100 * used / total
    disks = []  # storage devices: they have a temperature and a "Used Space" load, and are neither the CPU nor a GPU
    for name, sensors in hardware.items():
        if ("Load", "CPU Total") in sensors or "GPU Core" in {n for (_, n) in sensors}:
            continue
        temps = [parse_number(v) for (c, n), v in sensors.items() if c == "Temperatures"]
        temps = [t for t in temps if not math.isnan(t)]
        if temps and ("Load", "Used Space") in sensors:
            main = parse_number(sensors.get(("Temperatures", "Temperature"), "-"))
            disks.append({"name": name, "temp": main if not math.isnan(main) else max(temps),
                          "used": parse_number(sensors[("Load", "Used Space")])})
    res = {k: v for k, v in out.items() if not math.isnan(v)}
    if disks:
        res["disk_temps"] = disks
    return res


def fetch_lhm(url: str = "http://127.0.0.1:8085/data.json", timeout: float = 2.0) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return parse_lhm(json.load(r))
    except Exception:
        return None


# ---------------------------------------------------------------------- nvidia-smi
def parse_nvidia_smi(output: str) -> dict:
    """CSV lines 'util, temp, mem_used_MiB, mem_total_MiB' -> readings of the biggest GPU."""
    best = None
    for line in output.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 4:
            continue
        nums = [parse_number(p) for p in parts[:4]]
        if best is None or (not math.isnan(nums[3]) and nums[3] > best[3]):
            best = nums
    if best is None:
        return {}
    util, temp, used, total = best
    out = {"gpu": util, "gpu_temp": temp, "gpu_mem_used_gb": used / 1024, "gpu_mem_total_gb": total / 1024}
    if total:
        out["gpu_mem"] = 100 * used / total
    return {k: v for k, v in out.items() if not math.isnan(v)}


def fetch_nvidia_smi(timeout: float = 3.0) -> dict | None:
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW: no console flash
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,temperature.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=timeout, **kwargs,
        )
        if r.returncode != 0:
            return None
        return parse_nvidia_smi(r.stdout) or None
    except Exception:
        return None


# --------------------------------------------------------------------------- poller
class Poller(threading.Thread):
    """Calls ``fn`` every ``interval`` s (``retry`` s while it fails); keeps the last good dict."""

    def __init__(self, name: str, fn, interval: float = 2.0, retry: float = 15.0):
        super().__init__(daemon=True, name=f"poll-{name}")
        self.label, self.fn, self.interval, self.retry = name, fn, interval, retry
        self.data: dict = {}
        self.ok = False
        self._stop_evt = threading.Event()

    def run(self):
        while not self._stop_evt.is_set():
            res = self.fn()
            if res:
                if not self.ok:
                    log.info("sensor source '%s' is working", self.label)
                self.data, self.ok = res, True
                wait = self.interval
            else:
                self.data, self.ok = {}, False
                wait = self.retry
            self._stop_evt.wait(wait)

    def stop(self):
        self._stop_evt.set()
