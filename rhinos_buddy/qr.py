"""A small QR code encoder (byte mode, error correction level M, versions 1-9: up to 180 bytes).

It exists so the "phone access" panel can show a QR code without any extra package.  The result is the module
matrix (``True`` = dark); the page draws it.  The algorithm is the standard one (ISO/IEC 18004): Reed-Solomon
over GF(256), function patterns, zig-zag placement, the 8 masks scored with the four penalty rules.
"""

from __future__ import annotations

# error-correction codewords per block / number of blocks, level M, versions 1..10 (index 0 unused)
_ECC_PER_BLOCK = [0, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]
_NUM_BLOCKS = [0, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]
MAX_VERSION = 9


def _raw_modules(ver: int) -> int:
    n = (16 * ver + 128) * ver + 64
    if ver >= 2:
        a = ver // 7 + 2
        n -= (25 * a - 10) * a - 55
        if ver >= 7:
            n -= 36
    return n


def _data_codewords(ver: int) -> int:
    return _raw_modules(ver) // 8 - _ECC_PER_BLOCK[ver] * _NUM_BLOCKS[ver]


def capacity(ver: int = MAX_VERSION) -> int:
    """How many bytes fit in ``ver`` (byte mode, level M)."""
    bits = _data_codewords(ver) * 8 - 4 - 8  # mode indicator + 8-bit count (versions 1-9)
    if ver >= 10:
        bits -= 8                              # 16-bit count from version 10
    return bits // 8


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list[int]:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data: list[int], divisor: list[int]) -> list[int]:
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, c in enumerate(divisor):
            result[i] ^= _gf_mul(c, factor)
    return result


def _align_positions(ver: int) -> list[int]:
    if ver == 1:
        return []
    n = ver // 7 + 2
    step = (ver * 4 + n * 2 + 1) // (n * 2 - 2) * 2
    res = [6]
    pos = ver * 4 + 10
    for _ in range(n - 1):
        res.insert(1, pos)
        pos -= step
    return res


def _bch(value: int, poly: int, bits_poly: int, shift: int) -> int:
    rem = value
    for _ in range(shift):
        rem = (rem << 1) ^ ((rem >> (bits_poly - 1)) * poly)
    return rem


def _build_codewords(data: bytes, ver: int) -> list[int]:
    bits: list[int] = []

    def put(val: int, n: int) -> None:
        bits.extend((val >> i) & 1 for i in range(n - 1, -1, -1))

    put(0b0100, 4)
    put(len(data), 8 if ver < 10 else 16)
    for b in data:
        put(b, 8)
    cap = _data_codewords(ver) * 8
    put(0, min(4, cap - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    pad = 0xEC
    while len(bits) < cap:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]

    blocks_n, ecc_len = _NUM_BLOCKS[ver], _ECC_PER_BLOCK[ver]
    raw_words = _raw_modules(ver) // 8
    short_blocks = blocks_n - raw_words % blocks_n
    short_len = raw_words // blocks_n
    blocks, divisor, k = [], _rs_divisor(ecc_len), 0
    for i in range(blocks_n):
        size = short_len - ecc_len + (0 if i < short_blocks else 1)
        chunk = words[k:k + size]
        k += size
        ecc = _rs_remainder(chunk, divisor)
        if i < short_blocks:
            chunk = chunk + [0]
        blocks.append((chunk, ecc))
    out: list[int] = []
    for i in range(len(blocks[0][0])):
        for j, (chunk, _) in enumerate(blocks):
            if i != short_len - ecc_len or j >= short_blocks:
                out.append(chunk[i])
    for i in range(ecc_len):
        for _, ecc in blocks:
            out.append(ecc[i])
    return out


class _Grid:
    def __init__(self, ver: int):
        self.ver, self.size = ver, ver * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.func = [[False] * self.size for _ in range(self.size)]
        self._draw_function_patterns()

    def _set(self, x: int, y: int, dark: bool) -> None:
        self.dark[y][x] = dark
        self.func[y][x] = True

    def _draw_function_patterns(self) -> None:
        n = self.size
        for i in range(n):
            self._set(6, i, i % 2 == 0)
            self._set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):  # finders with their separators
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        self._set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _align_positions(self.ver)
        for i, cx in enumerate(pos):
            for j, cy in enumerate(pos):
                if (i == 0 and j == 0) or (i == 0 and j == len(pos) - 1) or (i == len(pos) - 1 and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self._set(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
        self._draw_format(0)  # reserve the area
        self._draw_version()

    def _draw_format(self, mask: int) -> None:
        n = self.size
        data = (0b00 << 3) | mask  # level M = 00
        bits = ((data << 10) | _bch(data, 0x537, 10, 10)) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 == 1  # noqa: E731
        for i in range(6):
            self._set(8, i, bit(i))
        self._set(8, 7, bit(6))
        self._set(8, 8, bit(7))
        self._set(7, 8, bit(8))
        for i in range(9, 15):
            self._set(14 - i, 8, bit(i))
        for i in range(8):
            self._set(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self._set(8, n - 15 + i, bit(i))
        self._set(8, n - 8, True)

    def _draw_version(self) -> None:
        if self.ver < 7:
            return
        bits = (self.ver << 12) | _bch(self.ver, 0x1F25, 12, 12)
        n = self.size
        for i in range(18):
            b = (bits >> i) & 1 == 1
            a, c = n - 11 + i % 3, i // 3
            self._set(a, c, b)
            self._set(c, a, b)

    def place(self, codewords: list[int]) -> None:
        n, i = self.size, 0
        total = len(codewords) * 8
        for right in range(n - 1, 0, -2):
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = n - 1 - vert if upward else vert
                    if not self.func[y][x] and i < total:
                        self.dark[y][x] = (codewords[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1

    def apply_mask(self, mask: int) -> None:
        masks = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
                 lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
                 lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
                 lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)
        f = masks[mask]
        for y in range(self.size):
            for x in range(self.size):
                if not self.func[y][x] and f(x, y):
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self) -> int:
        n, d, score = self.size, self.dark, 0
        lines = [row for row in d] + [[d[y][x] for y in range(n)] for x in range(n)]
        for line in lines:  # rule 1 (runs of 5+) and rule 3 (finder-like 1:1:3:1:1 pattern)
            run = 1
            for k in range(1, n):
                if line[k] == line[k - 1]:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run = 1
            if run >= 5:
                score += run - 2
            s = "".join("1" if v else "0" for v in line)
            for pat in ("00001011101", "10111010000"):
                start = s.find(pat)
                while start != -1:
                    score += 40
                    start = s.find(pat, start + 1)
        for y in range(n - 1):  # rule 2: 2x2 blocks
            for x in range(n - 1):
                if d[y][x] == d[y][x + 1] == d[y + 1][x] == d[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(r) for r in d)  # rule 4: balance
        k = (abs(dark * 20 - n * n * 10) + n * n - 1) // (n * n) - 1
        return score + max(0, k) * 10


def encode(text: str) -> list[list[bool]]:
    """The QR code of ``text`` as rows of booleans (True = dark module), without the quiet zone."""
    data = text.encode("utf-8")
    ver = next((v for v in range(1, MAX_VERSION + 1) if len(data) <= capacity(v)), None)
    if ver is None:
        raise ValueError("text too long for the built-in QR encoder")
    words = _build_codewords(data, ver)
    best = None
    for mask in range(8):
        g = _Grid(ver)
        g.place(words)
        g.apply_mask(mask)
        g._draw_format(mask)
        g._draw_version()
        p = g.penalty()
        if best is None or p < best[0]:
            best = (p, g)
    return best[1].dark


def to_svg(matrix: list[list[bool]], border: int = 4) -> str:
    """A self-contained SVG (white background, quiet zone included) - crisp at any size."""
    n = len(matrix)
    cells = "".join(f"M{x + border},{y + border}h1v1h-1z" for y, row in enumerate(matrix) for x, v in enumerate(row) if v)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n + 2 * border} {n + 2 * border}" shape-rendering="crispEdges">'
            f'<rect width="100%" height="100%" fill="#fff"/><path d="{cells}" fill="#000"/></svg>')
