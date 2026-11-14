#!/usr/bin/env python3
"""修正前後のHTMLを埋め込んだ、前後比較ページ(1ファイル完結)を作る。

使い方:
  python3 build_compare.py --before before.html --after after.html -o compare.html \\
      --title "料金ページ" --verdict 改修 --note "主役を申し込みボタン1つに絞った"

assets/compare-template.html をもとに、次のことを行う:
  - 埋め込むHTMLの中の </script と <!-- を書き換える(そのままだと埋め込みが途中で途切れる)
  - 題名・判定・ひとことの説明を入れる

埋め込むHTMLは、CSSとスクリプトをインラインにした、単体で開ける形にしておく。
外部の読み込みが残っていないかは check_external.py で確かめられる。

Python 3.8 以降。標準ライブラリだけで動く。
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(HERE, "..", "assets", "compare-template.html")
SLOT = re.compile(r'(<script type="text/plain" id="dp-(before|after)">\n)(.*?)(</script>)', re.S)


def escape(html):
    """<script type="text/plain"> の中に安全に置けるようにする。表示するときに元へ戻される。"""
    html = re.sub(r"</(script)", r"<\\/\1", html, flags=re.I)
    return html.replace("<!--", "<\\!--")


def main():
    ap = argparse.ArgumentParser(description="前後比較ページ(1ファイル完結)を作る")
    ap.add_argument("--before", required=True, help="修正前のHTML")
    ap.add_argument("--after", required=True, help="修正後のHTML")
    ap.add_argument("-o", "--output", required=True, help="出力先")
    ap.add_argument("--title", default="前後比較", help="画面の名前")
    ap.add_argument("--verdict", default="", help="判定(調整 / 改修 / 再構成)")
    ap.add_argument("--note", default="", help="ひとことの説明")
    ap.add_argument("--template", default=DEFAULT_TEMPLATE, help="ひな形(既定は同梱の compare-template.html)")
    args = ap.parse_args()

    try:
        with open(args.template, encoding="utf-8") as f:
            template = f.read()
        pages = {}
        for side in ("before", "after"):
            with open(getattr(args, side), encoding="utf-8") as f:
                pages[side] = f.read()
    except OSError as e:
        print("読めません: %s" % e, file=sys.stderr)
        return 2

    found = []

    def fill(m):
        found.append(m.group(2))
        body = escape(pages[m.group(2)])
        return m.group(1) + body + ("" if body.endswith("\n") else "\n") + m.group(4)

    out = SLOT.sub(fill, template)
    if sorted(found) != ["after", "before"]:
        print("ひな形に埋め込み先(dp-before / dp-after)が見つかりません: " + args.template, file=sys.stderr)
        return 2

    meta = "window.DP_META = %s;" % json.dumps(
        {"title": args.title, "verdict": args.verdict, "note": args.note}, ensure_ascii=False, indent=2
    ).replace("</", "<\\/")
    out, n = re.subn(r"window\.DP_META = \{.*?\};", lambda m: meta, out, count=1, flags=re.S)
    if n != 1:
        print("ひな形に DP_META が見つかりません: " + args.template, file=sys.stderr)
        return 2

    # ひな形の使い方の説明を、生成物の説明に差し替える
    out = re.sub(
        r"<!--\n  design-polish 前後比較ページのひな形.*?-->",
        "<!--\n  design-polish 前後比較ページ\n\n"
        "  compare-template.html に、修正前後のHTMLを build_compare.py で埋め込んだもの。\n"
        "  外部の読み込みはない。保存してローカルで開いても、そのまま動く。\n-->",
        out, count=1, flags=re.S,
    )

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(out)
    print("作成: %s(%d バイト)" % (args.output, len(out.encode("utf-8"))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
