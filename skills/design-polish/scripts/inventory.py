#!/usr/bin/env python3
"""CSSに書かれている値の棚卸し。色・文字サイズ・余白・角丸・影の種類を数える。

使い方:
  python3 inventory.py site.css page1.html page2.html
  python3 inventory.py --json src/styles/*.css
  python3 inventory.py --top 30 base.css          各分類で表示する件数(既定 15)

読むもの: .css ファイル、HTMLの <style> と style 属性。
数え方(references/multi-page.md と同じ):
  - 色は表記の違いで数える(#666 と #666666 は同じ、透明度が違えば別)
  - グラデーションと影の中の色は、色の種類に含めず、グラデーション・影として別に数える
  - カスタムプロパティ(--name: 値)の定義は「トークン」、それ以外に直接書かれた値は「直書き」として分ける
    直書きが多いほど、体系から外れた箇所が多い

これはソースに書かれた値の集計で、描画後の実際の値(継承や上書きの結果)ではない。
Tailwind などユーティリティクラスの出現数は数えない(クラス名を検索して別に数える)。

Python 3.8 以降。標準ライブラリだけで動く。
"""
import argparse
import json
import re
import sys
from collections import Counter
from html.parser import HTMLParser

COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|(?:rgba?|hsla?)\([^)]*\)")
SPACE_PROPS = re.compile(r"^(padding|margin)(-(top|right|bottom|left|inline|block)(-(start|end))?)?$|^(row-|column-)?gap$")
LENGTH_RE = re.compile(r"^-?\d*\.?\d+(px|rem|em|%|vh|vw|ch)$")


class StyleGrabber(HTMLParser):
    """HTMLから <style> の中身と style 属性を取り出す。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.css = []
        self._in = False

    def handle_starttag(self, tag, attrs):
        if tag == "style":
            self._in = True
        for k, v in attrs:
            if k == "style" and v:
                self.css.append("[style-attr]{%s}" % v)

    def handle_endtag(self, tag):
        if tag == "style":
            self._in = False

    def handle_data(self, data):
        if self._in:
            self.css.append(data)


def read_css(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if path.lower().endswith((".html", ".htm", ".vue", ".svelte")):
        g = StyleGrabber()
        g.feed(text)
        return "\n".join(g.css)
    return text


def declarations(css):
    """CSSから (プロパティ, 値) を順に取り出す。セレクタや @規則の前置きは読み飛ばす。"""
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    depth, buf, paren = 0, [], 0
    for ch in css:
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        if paren == 0 and ch in "{};":
            seg = "".join(buf).strip()
            buf = []
            if ch == "{":
                depth += 1
                continue
            if ch == "}":
                depth = max(0, depth - 1)
            if seg and ":" in seg and (depth > 0 or ch == "}"):
                prop, value = seg.split(":", 1)
                prop = prop.strip().lower()
                if re.fullmatch(r"-{0,2}[a-z][\w-]*", prop):
                    yield prop, value.replace("!important", "").strip()
            continue
        buf.append(ch)


def norm_color(c):
    c = c.strip().lower()
    if c.startswith("#"):
        h = c[1:]
        if len(h) in (3, 4):
            h = "".join(x * 2 for x in h)
        if len(h) == 8 and h.endswith("ff"):
            h = h[:6]
        return "#" + h
    return re.sub(r"\s+", "", c).replace(",", ", ")


def norm_value(v):
    return re.sub(r"\s+", " ", v.strip().lower())


def collect(paths):
    out = {k: {"token": Counter(), "raw": Counter()} for k in
           ("color_text", "color_background", "color_border", "color_other",
            "font_size", "font_weight", "space", "radius", "shadow", "gradient")}
    var_uses = 0
    tokens = 0

    for path in paths:
        for prop, value in declarations(read_css(path)):
            kind = "token" if prop.startswith("--") else "raw"
            if kind == "token":
                tokens += 1
            var_uses += len(re.findall(r"var\(", value))
            low = value.lower()

            # グラデーションと影は、中の色を数えずにまとめて1つとして数える
            rest = low
            for m in re.finditer(r"(?:repeating-)?(?:linear|radial|conic)-gradient\((?:[^()]|\([^()]*\))*\)", low):
                out["gradient"][kind][norm_value(m.group(0))] += 1
                rest = rest.replace(m.group(0), " ")
            if prop in ("box-shadow", "text-shadow") or (kind == "token" and re.search(r"\d+px\s+\d+px", low) and COLOR_RE.search(low)):
                if low not in ("none", "0"):
                    out["shadow"][kind][norm_value(value)] += 1
                continue
            if prop == "filter" and "drop-shadow" in low:
                out["shadow"][kind][norm_value(value)] += 1
                continue

            for c in COLOR_RE.findall(rest):
                if prop == "color" or prop.endswith("-text-fill-color"):
                    group = "color_text"
                elif prop.startswith("background"):
                    group = "color_background"
                elif prop.startswith("border") or prop.startswith("outline"):
                    group = "color_border"
                else:
                    group = "color_other"
                out[group][kind][norm_color(c)] += 1

            if prop == "font-size":
                out["font_size"][kind][norm_value(value)] += 1
            elif prop == "font-weight":
                out["font_weight"][kind][norm_value(value)] += 1
            elif prop.startswith("border") and prop.endswith("radius"):
                out["radius"][kind][norm_value(value)] += 1
            elif SPACE_PROPS.match(prop):
                for part in low.split():
                    if LENGTH_RE.match(part) and float(re.match(r"-?\d*\.?\d+", part).group(0)) != 0:
                        out["space"][kind][part] += 1
            elif kind == "token" and LENGTH_RE.match(low) and re.search(r"space|gap|pad|margin|size|radius", prop):
                # トークンとして定義された長さ(用途は名前から推測)
                if "radius" in prop:
                    out["radius"]["token"][low] += 1
                elif re.search(r"font|text|size", prop) and "space" not in prop:
                    out["font_size"]["token"][low] += 1
                else:
                    out["space"]["token"][low] += 1
    return out, tokens, var_uses


LABELS = [
    ("color_text", "文字色"), ("color_background", "背景色"), ("color_border", "罫線・枠の色"), ("color_other", "その他の色(トークンの定義を含む)"),
    ("font_size", "文字サイズ"), ("font_weight", "文字の太さ"), ("space", "余白"), ("radius", "角丸"),
    ("shadow", "影"), ("gradient", "グラデーション"),
]


def main():
    ap = argparse.ArgumentParser(description="CSSに書かれている値の棚卸し")
    ap.add_argument("files", nargs="+", help=".css、または <style> や style 属性を含むHTML")
    ap.add_argument("--json", action="store_true", help="結果をJSONで出す")
    ap.add_argument("--top", type=int, default=15, help="各分類で表示する件数(既定 15)")
    args = ap.parse_args()

    try:
        data, tokens, var_uses = collect(args.files)
    except OSError as e:
        print("読めません: %s" % e, file=sys.stderr)
        return 2

    all_colors = Counter()
    for key in ("color_text", "color_background", "color_border", "color_other"):
        all_colors.update(data[key]["raw"])
        all_colors.update(data[key]["token"])

    if args.json:
        print(json.dumps({
            "files": args.files, "custom_properties": tokens, "var_uses": var_uses,
            "distinct_colors": len(all_colors),
            "categories": {k: {"token": dict(v["token"]), "raw": dict(v["raw"])} for k, v in data.items()},
        }, ensure_ascii=False, indent=2))
        return 0

    print("# 値の棚卸し")
    print("対象: " + ", ".join(args.files))
    print("カスタムプロパティの定義 %d 個、var() の使用 %d か所" % (tokens, var_uses))
    print("色の種類(グラデーションと影の中の色を除く): %d 種類" % len(all_colors))
    print()
    print("| 分類 | 種類 | うち直書き | 直書きのうち1〜2か所だけ |")
    print("|---|---|---|---|")
    for key, label in LABELS:
        raw, tok = data[key]["raw"], data[key]["token"]
        kinds = len(set(raw) | set(tok))
        rare = sum(1 for n in raw.values() if n <= 2)
        print("| %s | %d | %d | %d |" % (label, kinds, len(raw), rare))
    print()
    for key, label in LABELS:
        raw, tok = data[key]["raw"], data[key]["token"]
        if not raw and not tok:
            continue
        print("## %s" % label)
        if tok:
            print("トークン: " + ", ".join("%s ×%d" % (v, n) for v, n in tok.most_common(args.top)))
        if raw:
            print("直書き: " + ", ".join("%s ×%d" % (v if len(v) <= 60 else v[:57] + "...", n) for v, n in raw.most_common(args.top)))
            if len(raw) > args.top:
                print("  (ほか %d 種類)" % (len(raw) - args.top))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
