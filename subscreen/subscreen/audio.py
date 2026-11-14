"""Audio analysis for the music visualizer.

* ``analyze_block`` / ``band_levels`` / ``BeatDetector`` are pure numpy and fully testable.
* ``Analyzer`` runs a capture thread on the *output* of the sound card (Windows "loopback": whatever
  the speakers/headphones are playing, any player) through the optional ``soundcard`` package.
* The capture only runs while a visualizer is on the visible page; it sleeps otherwise.
* Without the package (or without a device) the visualizer simply stays flat and ``status()`` says why.
"""

from __future__ import annotations

import logging
import threading
import time

import numpy as np

log = logging.getLogger("subscreen.audio")

BLOCK = 2048          # frames per analysis block (~43 ms at 48 kHz)
FMIN, FMAX = 40.0, 14000.0
STALE_SECONDS = 0.5   # no audio block for this long == silence (WASAPI loopback sends nothing while silent)
IDLE_SECONDS = 4.0    # nobody asked for levels for this long: stop recording


def analyze_block(samples: np.ndarray) -> np.ndarray:
    """Magnitude spectrum (rfft) of one block of mono samples, Hann windowed."""
    x = np.asarray(samples, dtype=np.float32)
    if x.ndim > 1:
        x = x.mean(axis=1)
    if x.size < 64:
        return np.zeros(1, dtype=np.float32)
    x = x * np.hanning(x.size).astype(np.float32)
    return np.abs(np.fft.rfft(x)).astype(np.float32) / max(1, x.size // 2)


def band_edges(n: int, fmin: float = FMIN, fmax: float = FMAX) -> np.ndarray:
    """``n`` log-spaced bands (music is heard on a log frequency scale): n + 1 edges in Hz."""
    return np.geomspace(fmin, fmax, n + 1)


def band_energy(mag: np.ndarray, rate: int, n: int) -> np.ndarray:
    """Average magnitude per band (linear).  Empty bands borrow the nearest FFT bin."""
    if mag.size < 2:
        return np.zeros(n, dtype=np.float32)
    freqs = np.linspace(0, rate / 2, mag.size)
    edges = band_edges(n, FMIN, min(FMAX, rate / 2 * 0.98))
    out = np.zeros(n, dtype=np.float32)
    for i in range(n):
        sel = (freqs >= edges[i]) & (freqs < edges[i + 1])
        if sel.any():
            out[i] = float(mag[sel].mean())
        else:
            out[i] = float(mag[int(np.argmin(np.abs(freqs - (edges[i] + edges[i + 1]) / 2)))])
    return out


def to_levels(energy: np.ndarray, reference: float, sensitivity: int = 50) -> np.ndarray:
    """Energy -> 0..1 bar heights on a log (decibel-like) scale relative to ``reference``.

    ``sensitivity`` 1..100 shifts the floor: higher shows quieter sounds."""
    ref = max(float(reference), 1e-6)
    floor_db = -70.0 + (sensitivity - 50) * 0.4   # 50 -> -70 dB below the reference peak
    db = 20.0 * np.log10(np.maximum(energy, 1e-9) / ref)
    return np.clip((db - floor_db) / -floor_db, 0.0, 1.0).astype(np.float32)


class BeatDetector:
    """Flags a beat when low-frequency energy jumps above its recent average."""

    def __init__(self, ratio: float = 1.45, min_gap: float = 0.22, floor: float = 1e-4):
        self.ratio, self.min_gap, self.floor = ratio, min_gap, floor
        self.avg = 0.0
        self.last = -10.0

    def feed(self, bass: float, now: float) -> bool:
        beat = bass > self.floor and bass > self.ratio * self.avg and now - self.last >= self.min_gap
        self.avg = bass if self.avg == 0 else 0.92 * self.avg + 0.08 * bass
        if beat:
            self.last = now
        return beat


class Analyzer:
    """Holds the latest spectrum and beat strength; fed by ``process`` (tests) or a capture thread."""

    def __init__(self):
        self._lock = threading.Lock()
        self.rate = 48000
        self.mag = np.zeros(1, dtype=np.float32)
        self.peak = 0.02          # slowly decaying loudest band energy seen (automatic gain)
        self.beat = 0.0           # 0..1, set to 1 on a beat, decays when read
        self._beat_seen = 0.0
        self._detector = BeatDetector()
        self.last_block = 0.0
        self.last_touch = 0.0
        self.state = "idle"       # idle | ok | unavailable | error
        self.message = "Visualizador desligado."
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.clock = time.monotonic

    # ---- data in
    def process(self, block: np.ndarray, rate: int, now: float | None = None) -> None:
        now = self.clock() if now is None else now
        mag = analyze_block(block)
        e = band_energy(mag, rate, 16)
        with self._lock:
            self.rate, self.mag, self.last_block = rate, mag, now
            self.peak = max(self.peak * 0.9985, float(e.max()))
            bass = float(e[:3].mean())
            if self._detector.feed(bass, now):
                self._beat_seen = 1.0
            self.state, self.message = "ok", "Capturando o áudio do computador."

    # ---- data out
    def levels(self, n: int, sensitivity: int = 50) -> np.ndarray:
        self.touch()
        with self._lock:
            fresh = self.clock() - self.last_block < STALE_SECONDS
            mag, rate, peak = self.mag, self.rate, self.peak
        if not fresh:
            return np.zeros(n, dtype=np.float32)
        return to_levels(band_energy(mag, rate, n), peak, sensitivity)

    def beat_strength(self) -> float:
        """Strongest beat since the last call (1.0 right on a beat), then it fades."""
        self.touch()
        with self._lock:
            v, self._beat_seen = self._beat_seen, self._beat_seen * 0.55
            if self.clock() - self.last_block >= STALE_SECONDS:
                return 0.0
        return v

    def status(self) -> dict:
        return {"state": self.state, "message": self.message}

    # ---- capture thread
    def touch(self) -> None:
        self.last_touch = self.clock()
        if self._thread is None or not self._thread.is_alive():
            if self.state != "unavailable":
                self.start()

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="audio", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        try:
            import soundcard as sc
        except Exception:
            self.state = "unavailable"
            self.message = "Pacote de áudio ausente (pip install soundcard). O visualizador ficará parado."
            log.info("soundcard is not installed; visualizer disabled")
            return
        while not self._stop.is_set():
            try:
                speaker = sc.default_speaker()
                mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
                rate = 48000
                with mic.recorder(samplerate=rate, channels=2, blocksize=BLOCK) as rec:
                    self.state, self.message = "ok", "Capturando o áudio do computador."
                    while not self._stop.is_set():
                        if self.clock() - self.last_touch > IDLE_SECONDS:
                            self.state, self.message = "idle", "Visualizador em espera (fora da tela)."
                            self._stop.wait(0.3)
                            continue
                        self.process(rec.record(numframes=BLOCK), rate)
            except Exception as e:  # no device, device changed, driver hiccup...
                self.state, self.message = "error", f"Sem captura de áudio: {str(e)[:80]}"
                log.warning("audio capture failed: %s", e)
                self._stop.wait(3.0)


_instance: Analyzer | None = None
_instance_lock = threading.Lock()


def get_analyzer() -> Analyzer:
    global _instance
    with _instance_lock:
        if _instance is None:
            _instance = Analyzer()
        return _instance


def shutdown() -> None:
    if _instance is not None:
        _instance.stop()
