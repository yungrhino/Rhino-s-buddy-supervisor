"""Command line: ports | run | image | clear | brightness | hello"""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from PIL import Image

from .devices import RevADisplay, SimulatorDisplay, list_ports, make_display
from .engine import Engine, load_config


def _display_from_args(a):
    if getattr(a, "simulator", False):
        return SimulatorDisplay(orientation=a.orientation, output=a.output)
    return RevADisplay(port=a.port, orientation=a.orientation, baudrate=a.baud)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="rhinos_buddy", description=__doc__)
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("ports", help="list serial ports (use this to find your screen)")
    sub.add_parser("sensors", help="show which sensors (CPU/GPU load and temperature) were found")

    r = sub.add_parser("run", help="run a config file")
    r.add_argument("-c", "--config", default="config.toml")
    r.add_argument("--simulator", action="store_true", help="no hardware: write preview.png")
    r.add_argument("--http", type=int, metavar="PORT", help="with --simulator: live preview on http://127.0.0.1:PORT")

    for name, helptext in (("image", "show one image and exit"), ("clear", "clear screen"),
                           ("brightness", "set brightness 0-100"), ("hello", "send identification probe"),
                           ("screen-on", "wake the panel"),
                           ("bench", "measure real USB throughput"),
                           ("partialtest", "draw small test rectangles at different alignments to find what the panel needs"),
                           ("selftest", "wake panel and show red/green/blue/white, trying both brightness polarities")):
        s = sub.add_parser(name, help=helptext)
        s.add_argument("--port", default="auto")
        s.add_argument("--baud", type=int, default=115200, help="serial speed (try 921600, 1500000, 3000000)")
        s.add_argument("--orientation", default="landscape")
        s.add_argument("--simulator", action="store_true")
        s.add_argument("--output", default="preview.png")
        if name == "image":
            s.add_argument("file")
            s.add_argument("--fit", choices=["cover", "contain", "stretch"], default="cover")
        if name == "brightness":
            s.add_argument("level", type=float)

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if a.cmd == "ports":
        for p in list_ports():
            print(f"{p['device']:<10} vid={p['vid']} pid={p['pid']} serial={p['serial_number']!r} {p['description']}")
        return 0

    if a.cmd == "sensors":
        import json
        import math
        import urllib.request

        from . import sensors as S
        from .metrics import Metrics

        m = Metrics({"nvidia_smi": False, "lhm": False})
        m.get()
        import time as _t

        _t.sleep(1.0)
        base = m.get()
        print("== psutil (sempre disponivel) ==")
        for k in ("cpu", "ram", "ram_used_gb", "ram_total_gb", "net_down_h", "net_up_h"):
            print(f"  {k:<18} {base.get(k)}")
        print("\n== nvidia-smi ==")
        nv = S.fetch_nvidia_smi()
        print("  " + (json.dumps(nv) if nv else "nao encontrado (sem GPU NVIDIA ou nvidia-smi fora do PATH)"))
        print("\n== LibreHardwareMonitor (http://127.0.0.1:8085/data.json) ==")
        try:
            with urllib.request.urlopen("http://127.0.0.1:8085/data.json", timeout=2) as r:
                tree = json.load(r)
        except Exception as e:
            print(f"  nao acessivel ({e}).\n  Abra o LibreHardwareMonitor como administrador e ative Options > Remote Web Server > Run.")
        else:
            print("  escolhido:", json.dumps(S.parse_lhm(tree)))
            print("  todos os sensores:")
            for path, value in S.flatten_lhm(tree):
                print("   ", " / ".join(path[1:]), "=", value)
        return 0

    if a.cmd == "run":
        cfg = load_config(a.config)
        if a.simulator:
            dev = dict(cfg.get("device", {}), type="simulator")
            if a.http:
                dev["http_port"] = a.http
            cfg["device"] = dev
        eng = Engine(cfg)
        signal.signal(signal.SIGINT, lambda *_: eng.stop_event.set())
        try:
            signal.signal(signal.SIGTERM, lambda *_: eng.stop_event.set())
        except (AttributeError, ValueError):
            pass
        eng.run()
        return 0

    disp = _display_from_args(a)
    with disp:
        if a.cmd == "image":
            from .widgets import _fit

            with Image.open(a.file) as im:
                frame = _fit(im, disp.width, disp.height, a.fit)
            bg = Image.new("RGB", frame.size, "black")
            bg.paste(frame, mask=frame.split()[3])
            disp.blit(bg)
        elif a.cmd == "clear":
            disp.clear()
        elif a.cmd == "brightness":
            disp.set_brightness(a.level)
        elif a.cmd == "screen-on":
            disp.screen_on()
            print("screen-on sent")
        elif a.cmd == "bench":
            import time

            from PIL import ImageDraw

            # A recognisable pattern (not noise) so you can SEE whether the picture is intact.
            pat = Image.new("RGB", (disp.width, disp.height))
            d = ImageDraw.Draw(pat)
            bars = [(255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0),
                    (255, 0, 255), (255, 0, 0), (0, 0, 255), (0, 0, 0)]
            bw = disp.width / len(bars)
            for i, c in enumerate(bars):
                d.rectangle((i * bw, 0, (i + 1) * bw, disp.height * 0.7), fill=c)
            for x in range(disp.width):
                g = int(255 * x / disp.width)
                d.line((x, disp.height * 0.7, x, disp.height), fill=(g, g, g))
            d.text((10, 10), f"BAUD {a.baud}", fill=(0, 0, 0))
            frame_bytes = disp.width * disp.height * 2
            disp.chunk_lines = 8
            print(f"baud={a.baud}; full frame = {frame_bytes / 1024:.0f} KB")
            print("Watch the screen: you should see 8 colour bars over a grey ramp.\n")
            t = time.perf_counter()
            disp.blit(pat)
            one = time.perf_counter() - t
            n = 1 if one > 4 else 3
            t = time.perf_counter()
            for _ in range(n):
                disp.blit(pat)
            dt = (time.perf_counter() - t) / n
            print(f"{1 / dt:5.2f} fps   {frame_bytes / dt / 1e6:5.2f} MB/s   ({dt:.2f} s per full frame)")
            time.sleep(3)
        elif a.cmd == "partialtest":
            from PIL import ImageDraw

            def tile(w, h, label_color):
                """Framed rectangle with a diagonal: any shear/skew is obvious."""
                im = Image.new("RGB", (w, h), (20, 20, 60))
                d = ImageDraw.Draw(im)
                d.rectangle((0, 0, w - 1, h - 1), outline=(255, 255, 255))
                d.line((0, 0, w - 1, h - 1), fill=label_color)
                d.line((0, h - 1, w - 1, 0), fill=label_color)
                return im

            disp.blit(Image.new("RGB", (disp.width, disp.height), (0, 0, 0)))
            cases = []
            # Row A: x offset 0..7 (position alignment), even width 40
            for k in range(8):
                cases.append((16 + 56 * k + k, 20, 40, 24, f"A{k}"))
            # Row B: widths 33..40 at an aligned x (width alignment)
            for k in range(8):
                cases.append((16 + 56 * k, 80, 33 + k, 24, f"B{k}"))
            # Row C: y offset 0..7 (vertical alignment), aligned x/width
            for k in range(8):
                cases.append((16 + 56 * k, 140 + k, 40, 24, f"C{k}"))
            # Row D: aligned to 8 (what the engine now uses)
            for k in range(8):
                cases.append((16 + 56 * k, 200, 40, 24, f"D{k}"))
            for x, y, w, h, name in cases:
                disp.blit(tile(w, h, (255, 255, 0)), x, y)
            print("Rows (top to bottom), 8 small framed boxes each with an X inside:")
            print("  A: x position offset 0..7     B: width 33..40")
            print("  C: y position offset 0..7     D: all aligned to 8")
            print("Tell me which boxes look broken/sheared (e.g. 'A1,A3,A5,A7 and B0,B2...').")
        elif a.cmd == "selftest":
            import time

            for inverted in (True, False):
                disp.invert_brightness = inverted
                print(f"\n--- brightness polarity: {'inverted (default)' if inverted else 'normal'} ---")
                disp.screen_on()
                disp.set_brightness(100)
                for name, rgb in (("RED", (255, 0, 0)), ("GREEN", (0, 255, 0)),
                                  ("BLUE", (0, 0, 255)), ("WHITE", (255, 255, 255))):
                    print("showing", name)
                    disp.blit(Image.new("RGB", (disp.width, disp.height), rgb))
                    time.sleep(2)
            print("\ndone. Tell me which polarity (if any) lit the screen and whether colors matched.")
        elif a.cmd == "hello":
            print("response:", disp.hello().hex(" ") or "(empty)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
