#!/usr/bin/env python3
"""exe 아이콘. 의존성 없이 PNG 를 직접 써서 ICO 로 묶는다.

    python build/make_icon.py        # build/pibo-connector.ico

모양은 static/favicon.svg 와 같다 — 둥근 사각형 안에 로봇 얼굴, 안테나 끝에 초록 점.
Vista 이후 ICO 는 PNG 항목을 그대로 담을 수 있어 256px 까지 깨끗하다.
"""

import struct
import zlib
from pathlib import Path

SIZES = (16, 24, 32, 48, 64, 128, 256)
OUT = Path(__file__).resolve().parent / "pibo-connector.ico"

BG = (0x17, 0x1A, 0x21)
BLUE = (0x4D, 0xA3, 0xFF)
GREEN = (0x3D, 0xDC, 0x84)


def _sd_round_rect(x, y, cx, cy, hw, hh, r):
    """둥근 사각형까지의 부호 거리."""
    dx, dy = abs(x - cx) - (hw - r), abs(y - cy) - (hh - r)
    ox, oy = max(dx, 0.0), max(dy, 0.0)
    return (ox * ox + oy * oy) ** 0.5 + min(max(dx, dy), 0.0) - r


def _sd_circle(x, y, cx, cy, r):
    return ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 - r


def _sd_segment(x, y, ax, ay, bx, by, w):
    px, py = x - ax, y - ay
    bx, by = bx - ax, by - ay
    h = max(0.0, min(1.0, (px * bx + py * by) / (bx * bx + by * by)))
    return ((px - bx * h) ** 2 + (py - by * h) ** 2) ** 0.5 - w


def _cov(d, aa):
    """부호 거리 → 커버리지 0..1 (aa 폭으로 안티에일리어싱)."""
    return max(0.0, min(1.0, 0.5 - d / aa))


def render(n):
    """n×n RGBA. 좌표는 32 기준 SVG 를 n 으로 비례."""
    s = n / 32.0
    aa = 1.0
    px = bytearray()
    for j in range(n):
        y = (j + 0.5) / s
        for i in range(n):
            x = (i + 0.5) / s
            r, g, b, a = 0.0, 0.0, 0.0, 0.0

            def put(col, c):
                nonlocal r, g, b, a
                if c <= 0:
                    return
                r = col[0] * c + r * (1 - c)
                g = col[1] * c + g * (1 - c)
                b = col[2] * c + b * (1 - c)
                a = c + a * (1 - c)

            # 배경 둥근 사각형 (0,0)-(32,32) r=7
            put(BG, _cov(_sd_round_rect(x, y, 16, 16, 16, 16, 7) * s, aa))
            # 얼굴 테두리: (7,9)-(25,23) r=4, 두께 2 → 링
            d_out = _sd_round_rect(x, y, 16, 16, 9, 7, 4)
            ring = max(d_out, -(d_out + 2.0))
            put(BLUE, _cov(ring * s, aa))
            # 눈
            put(BLUE, _cov(_sd_circle(x, y, 12.5, 16, 2) * s, aa))
            put(BLUE, _cov(_sd_circle(x, y, 19.5, 16, 2) * s, aa))
            # 안테나 대 (16,9)-(16,5) 폭 1
            put(BLUE, _cov(_sd_segment(x, y, 16, 9, 16, 5, 1.0) * s, aa))
            # 안테나 끝 초록 점
            put(GREEN, _cov(_sd_circle(x, y, 16, 4, 1.6) * s, aa))

            px += bytes((int(round(r)), int(round(g)), int(round(b)), int(round(a * 255))))
    return bytes(px)


def png(n, rgba):
    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + rgba[j * n * 4:(j + 1) * n * 4] for j in range(n))
    ihdr = struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    images = [(n, png(n, render(n))) for n in SIZES]
    head = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for n, data in images:
        entries += struct.pack("<BBBBHHII", n if n < 256 else 0, n if n < 256 else 0,
                               0, 0, 1, 32, len(data), offset)
        blobs += data
        offset += len(data)
    OUT.write_bytes(head + entries + blobs)
    print(f"{OUT}  {OUT.stat().st_size} bytes  sizes={SIZES}")


if __name__ == "__main__":
    main()
