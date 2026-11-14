#!/usr/bin/env python3
"""HTML・CSS・JS が外部から何かを読み込んでいないかを調べる。

使い方:
  python3 check_external.py after.html
  python3 check_external.py docs/ skills/design-polish/assets/     フォルダは中を再帰的に調べる
  python3 check_external.py --json polish.css

見つけるもの(読み込み):
  - src / poster / srcset、<link href>、<object data>、<form action> が外部のURLを指している
  - CSS の @import と url(...) が外部のURLを指している
  - スクリプトの fetch / import / XMLHttpRequest / WebSocket などが外部のURLを指している

読み込みではないので「参考」として分けるもの:
  - <a href="https://..."> などの、ただのリンク
  - コメントの中に書かれたURL

data: と blob: のURL、ページ内リンク(#...)、相対パスは対象外。
読み込みが1つでもあれば終了コード 1 を返す。

Python 3.8 以降。標準ライブラリだけで動く。
"""
import argparse
import json
import os
import re
import sys

EXTS = (".html", ".htm", ".css", ".js", ".mjs", ".svg", ".vue", ".svelte", ".jsx", ".tsx", ".ts")
EXTERNAL = r"(?:https?:)?//[A-Za-z0-9][^\s\"'<>)]*"

LOAD_PATTERNS = [
    ("src/poster", re.compile(r"\b(?:src|poster|data-src)\s*=\s*[\"']?\s*(%s)" % EXTERNAL, re.I)),
    ("srcset", re.compile(r"\bsrcset\s*=\s*[\"'][^\"']*?(%s)" % EXTERNAL, re.I)),
    ("<link href>", re.compile(r"<link\b[^>]*?\bhref\s*=\s*[\"']?\s*(%s)" % EXTERNAL, re.I | re.S)),
    ("<object data>", re.compile(r"<object\b[^>]*?\bdata\s*=\s*[\"']?\s*(%s)" % EXTERNAL, re.I | re.S)),
    ("<form action>", re.compile(r"<form\b[^>]*?\baction\s*=\s*[\"']?\s*(%s)" % EXTERNAL, re.I | re.S)),
    ("@import", re.compile(r"@import\s+(?:url\(\s*)?[\"']?\s*(%s)" % EXTERNAL, re.I)),
    ("url()", re.compile(r"url\(\s*[\"']?\s*(%s)" % EXTERNAL, re.I)),
    ("スクリプトの通信", re.compile(
        r"(?:\bfetch|\bimport|importScripts|new\s+WebSocket|new\s+EventSource|new\s+Worker|sendBeacon|\.open)\s*\(\s*(?:[\"'`][A-Z]+[\"'`]\s*,\s*)?[\"'`]\s*(%s)" % EXTERNAL, re.I)),
    ("import ... from", re.compile(r"\bfrom\s+[\"']\s*(%s)" % EXTERNAL)),
]
LINK_PATTERN = re.compile(r"<a\b[^>]*?\bhref\s*=\s*[\"']?\s*(%s)" % EXTERNAL, re.I | re.S)
ANY_URL = re.compile(r"https?://[^\s\"'<>)]+")
COMMENT = re.compile(r"<!--.*?-->|/\*.*?\*/", re.S)


def blank(text, m):
    """一致した範囲を、行数を保ったまま空白にする。"""
    s = m.group(0)
    return re.sub(r"[^\n]", " ", s)


def scan(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    loads, info = [], []

    def line_of(pos):
        return text.count("\n", 0, pos) + 1

    # コメントの中のURLは参考にとどめ、本体の検査からは外す
    for m in COMMENT.finditer(text):
        for u in ANY_URL.finditer(m.group(0)):
            info.append({"file": path, "line": line_of(m.start() + u.start()), "kind": "コメント内のURL", "url": u.group(0)})
    body = COMMENT.sub(lambda m: blank(text, m), text)
    # data: の中に書かれた名前空間のURL(xmlns など)は読み込みではない
    body = re.sub(r"url\(\s*[\"']?data:[^)]*\)", lambda m: blank(body, m), body)
    body = re.sub(r"xmlns(?::\w+)?\s*=\s*[\"'][^\"']*[\"']", lambda m: blank(body, m), body)

    seen = set()
    for kind, pat in LOAD_PATTERNS:
        for m in pat.finditer(body):
            key = (m.start(1), m.group(1))
            if key in seen:
                continue
            seen.add(key)
            loads.append({"file": path, "line": line_of(m.start(1)), "kind": kind, "url": m.group(1)})
    for m in LINK_PATTERN.finditer(body):
        info.append({"file": path, "line": line_of(m.start(1)), "kind": "リンク(読み込みではない)", "url": m.group(1)})
    return loads, info


def targets(paths):
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
                for name in sorted(files):
                    if name.lower().endswith(EXTS):
                        yield os.path.join(root, name)
        else:
            yield p


def main():
    ap = argparse.ArgumentParser(description="外部からの読み込みがないかを調べる")
    ap.add_argument("paths", nargs="+", help="ファイルまたはフォルダ")
    ap.add_argument("--json", action="store_true", help="結果をJSONで出す")
    args = ap.parse_args()

    loads, info, count = [], [], 0
    for path in targets(args.paths):
        try:
            a, b = scan(path)
        except OSError as e:
            print("読めません: %s" % e, file=sys.stderr)
            return 2
        count += 1
        loads += a
        info += b

    if args.json:
        print(json.dumps({"files": count, "loads": loads, "info": info}, ensure_ascii=False, indent=2))
        return 1 if loads else 0

    print("調べたファイル: %d 個" % count)
    print("## 外部からの読み込み: %d 件" % len(loads))
    for x in loads:
        print("- %s:%d  [%s]  %s" % (x["file"], x["line"], x["kind"], x["url"]))
    if info:
        print("\n## 参考(読み込みではない): %d 件" % len(info))
        for x in info:
            print("- %s:%d  [%s]  %s" % (x["file"], x["line"], x["kind"], x["url"]))
    print("\n判定: " + ("外部からの読み込みがある" if loads else "外部からの読み込みはない"))
    return 1 if loads else 0


if __name__ == "__main__":
    sys.exit(main())
