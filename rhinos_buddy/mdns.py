"""A tiny mDNS ("Bonjour") responder so the phone can open ``http://rhinos-buddy.local:PORT`` instead of a bare IP.

It answers only questions for its own name, with the PC's private address, and nothing else (no service browsing, no
other records).  iPhones resolve ``.local`` names natively; recent Android browsers usually do too, so the IP link is
always shown as well.  Standard library only (RFC 6762, just the part needed).
"""

from __future__ import annotations

import logging
import socket
import struct
import threading

log = logging.getLogger("rhinos_buddy.mdns")

NAME = "rhinos-buddy.local"
GROUP, PORT, TTL = "224.0.0.251", 5353, 120
TYPE_A, TYPE_AAAA, TYPE_ANY, TYPE_NSEC = 1, 28, 255, 47


def _labels(name: str) -> bytes:
    return b"".join(bytes([len(p)]) + p.encode("ascii") for p in name.rstrip(".").split(".")) + b"\x00"


def parse_questions(packet: bytes) -> list[tuple[str, int, int]] | None:
    """The questions of a query as ``(name, type, class)``; None when it is not a plain query (or is malformed)."""
    if len(packet) < 12:
        return None
    flags, qd = struct.unpack("!2xHH6x", packet[:12])
    if flags & 0x8000 or qd == 0 or qd > 16:       # a response, or nothing asked
        return None
    pos, out = 12, []
    try:
        for _ in range(qd):
            parts = []
            while True:
                n = packet[pos]
                pos += 1
                if n == 0:
                    break
                if n & 0xC0 or pos + n > len(packet):  # compression in a question is not used by real queries
                    return None
                parts.append(packet[pos:pos + n].decode("ascii", "ignore").lower())
                pos += n
            qtype, qclass = struct.unpack("!HH", packet[pos:pos + 4])
            pos += 4
            out.append((".".join(parts), qtype, qclass))
    except (IndexError, struct.error):
        return None
    return out


def build_answer(packet: bytes, name: str, ip: str, legacy: bool = False) -> bytes | None:
    """The reply to ``packet`` when it asks for ``name`` (A, AAAA or ANY), else None.  AAAA gets a "no such record" (NSEC)."""
    qs = parse_questions(packet)
    if not qs:
        return None
    want = name.lower()
    mine = [(t, c) for n, t, c in qs if n == want and (c & 0x7FFF) in (1, 255)]
    if not mine:
        return None
    nm = _labels(name)
    answers = b""
    count = 0
    if any(t in (TYPE_A, TYPE_ANY) for t, _ in mine):
        answers += nm + struct.pack("!HHIH", TYPE_A, 0x8001, TTL, 4) + socket.inet_aton(ip)
        count += 1
    if any(t in (TYPE_AAAA, TYPE_ANY) for t, _ in mine):  # we only have an IPv4 address: say so, so nobody waits for AAAA
        rdata = nm + b"\x00\x01\x40"
        answers += nm + struct.pack("!HHIH", TYPE_NSEC, 0x8001, TTL, len(rdata)) + rdata
        count += 1
    if not count:
        return None
    ident = packet[:2] if legacy else b"\x00\x00"
    return ident + struct.pack("!HHHHH", 0x8400, 0, count, 0, 0) + answers


class Responder:
    """Joins the mDNS group on the LAN interface of ``ip`` and answers for ``name`` until ``stop()``."""

    def __init__(self, ip: str, name: str = NAME):
        self.ip, self.name = ip, name
        self.sock: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.error = ""

    def start(self) -> bool:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if hasattr(socket, "SO_REUSEPORT"):
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            s.bind(("", PORT))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(GROUP) + socket.inet_aton(self.ip))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self.ip))
            s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
            s.settimeout(0.5)
        except OSError as e:
            s.close()
            self.error = str(e.strerror or e)
            log.warning("mDNS name could not start: %s", e)
            return False
        self.sock, self.error = s, ""
        self.thread = threading.Thread(target=self._loop, name="mdns", daemon=True)
        self.thread.start()
        return True

    def _loop(self) -> None:
        while self.sock is not None:
            s = self.sock
            try:
                data, addr = s.recvfrom(1500)
            except socket.timeout:
                continue
            except OSError:
                return
            try:
                legacy = addr[1] != PORT
                qs = parse_questions(data)
                unicast = legacy or bool(qs and any(c & 0x8000 for _, _, c in qs))
                reply = build_answer(data, self.name, self.ip, legacy)
                if reply:
                    s.sendto(reply, addr if unicast else (GROUP, PORT))
            except Exception:  # never let a stray packet stop the responder
                log.debug("mDNS packet ignored", exc_info=True)

    def stop(self) -> None:
        s, self.sock = self.sock, None
        if s is not None:
            try:
                s.close()
            except OSError:
                pass
        if self.thread is not None:
            self.thread.join(timeout=1.5)
            self.thread = None

    @property
    def running(self) -> bool:
        return self.sock is not None
