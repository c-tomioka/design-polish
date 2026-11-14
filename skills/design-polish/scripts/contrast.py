#!/usr/bin/env python3
"""文字色と背景色のコントラスト比を計算する。

使い方:
  python3 contrast.py "#1b1f1d" "#f4f5f2"              文字色 背景色
  python3 contrast.py "#565e59:#f4f5f2" "#fff:#b8321a"  「文字色:背景色」をいくつでも
  python3 contrast.py --large "#767e78:#fbfbf9"         大きな文字・操作部品の境界(基準 3:1)
  python3 contrast.py --on "#ffffff" "rgba(0,0,0,.6):#f4f5f2"
                                                        半透明の背景色を重ねる下地の色(既定は白)

色は #rgb / #rrggbb / #rrggbbaa / rgb() / rgba() / hsl() / hsla() と、white / black が使える。
半透明の文字色は背景に重ねてから計算する。

基準(WCAG 2.x): 本文 4.5:1 以上、大きな文字と操作部品の境界 3:1 以上。
基準に届かない組み合わせが1つでもあれば、終了コード 1 を返す。

Python 3.8 以降。標準ライブラリだけで動く。
"""
import argparse
import colorsys
import re
import sys

NAMED = {"white": (255, 255, 255, 1.0), "black": (0, 0, 0, 1.0), "transparent": (0, 0, 0, 0.0)}


def parse_color(text):
    """色の文字列を (r, g, b, a) にする。r,g,b は 0〜255、a は 0〜1。"""
    s = text.strip().lower()
    if s in NAMED:
        return NAMED[s]
    m = re.fullmatch(r"#([0-9a-f]{3,8})", s)
    if m:
        h = m.group(1)
        if len(h) in (3, 4):
            h = "".join(c * 2 for c in h)
        if len(h) not in (6, 8):
            raise ValueError("色として読めません: " + text)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
        return (r, g, b, a)
    m = re.fullmatch(r"(rgba?|hsla?)\(([^)]*)\)", s)
    if m:
        parts = [p for p in re.split(r"[\s,/]+", m.group(2).strip()) if p]
        if len(parts) < 3:
            raise ValueError("色として読めません: " + text)

        def num(p, scale=1.0):
            return float(p[:-1]) / 100 * scale if p.endswith("%") else float(p)

        a = num(parts[3]) if len(parts) > 3 else 1.0
        if len(parts) > 3 and parts[3].endswith("%"):
            a = float(parts[3][:-1]) / 100
        if m.group(1).startswith("rgb"):
            r, g, b = (num(p, 255) for p in parts[:3])
        else:
            hue = float(re.sub(r"(deg)$", "", parts[0])) % 360 / 360
            sat = float(parts[1].rstrip("%")) / 100
            lig = float(parts[2].rstrip("%")) / 100
            r, g, b = (v * 255 for v in colorsys.hls_to_rgb(hue, lig, sat))
        return (r, g, b, max(0.0, min(1.0, a)))
    raise ValueError("色として読めません: " + text)


def over(top, bottom):
    """半透明の色 top を、不透明な色 bottom の上に重ねた色。"""
    a = top[3]
    return tuple(top[i] * a + bottom[i] * (1 - a) for i in range(3)) + (1.0,)


def luminance(c):
    def lin(v):
        v = v / 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def ratio(fg, bg, base=(255, 255, 255, 1.0)):
    """コントラスト比。bg が半透明なら base に、fg が半透明なら bg に重ねる。"""
    bg = over(bg, base) if bg[3] < 1 else bg
    fg = over(fg, bg) if fg[3] < 1 else fg
    a, b = luminance(fg), luminance(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def main():
    ap = argparse.ArgumentParser(description="文字色と背景色のコントラスト比を計算する")
    ap.add_argument("colors", nargs="+", help="「文字色 背景色」の2つ、または「文字色:背景色」をいくつでも")
    ap.add_argument("--large", action="store_true", help="大きな文字・操作部品の境界として判定する(基準 3:1)")
    ap.add_argument("--on", default="#ffffff", help="半透明の背景色を重ねる下地の色(既定 #ffffff)")
    args = ap.parse_args()

    if len(args.colors) == 2 and not any(":" in c for c in args.colors):
        pairs = [(args.colors[0], args.colors[1])]
    else:
        pairs = []
        for item in args.colors:
            if ":" not in item:
                ap.error("「文字色:背景色」の形で書いてください: " + item)
            fg, bg = item.split(":", 1)
            pairs.append((fg, bg))

    need = 3.0 if args.large else 4.5
    failed = 0
    try:
        base = parse_color(args.on)
        for fg, bg in pairs:
            r = ratio(parse_color(fg), parse_color(bg), base)
            ok = r >= need
            failed += 0 if ok else 1
            note = "" if ok else "  ← 基準 %.1f:1 に届かない" % need
            print("%s  %5.2f:1  文字 %s / 背景 %s%s" % ("OK" if ok else "NG", r, fg.strip(), bg.strip(), note))
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    print("基準 %.1f:1(%s)、%d 組中 %d 組が不足" % (need, "大きな文字・境界" if args.large else "本文", len(pairs), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
