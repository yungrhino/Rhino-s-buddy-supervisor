"""Exemplo de plugin: desenha QUALQUER coisa com Pillow.

Contrato: classe `Plugin` com `render(w, h) -> PIL.Image` e, opcionalmente,
`update() -> bool` (devolva False quando nada mudou para economizar banda USB).
"""

import math
import time

from PIL import Image, ImageDraw


class Plugin:
    def __init__(self, cfg, ctx):
        self.cfg = cfg
        self.ctx = ctx  # ctx.metrics.get() -> dict com cpu, ram, ...

    def update(self):
        return True  # animação: sempre redesenha

    def render(self, w, h):
        img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        t = time.time()
        for i in range(24):
            a = t * 2 + i * math.tau / 24
            r = 28 + 12 * math.sin(t * 3 + i)
            cx, cy = w / 2 + math.cos(a) * 60, h / 2 + math.sin(a) * 40
            d.ellipse((cx - r / 3, cy - r / 3, cx + r / 3, cy + r / 3), fill=(77, 171, 247, 200))
        return img
