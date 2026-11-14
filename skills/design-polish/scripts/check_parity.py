#!/usr/bin/env python3
"""修正前と修正後のHTMLを突き合わせ、機能に関わる部分が変わっていないかを確かめる。

使い方:
  python3 check_parity.py before.html after.html
  python3 check_parity.py --json before.html after.html

確かめること:
  - id、name、リンク先(href)、フォームの送信先、data-* 属性、on* 属性が消えていないか
  - 操作できる要素(a、button、input、select、textarea、form、details、summary)の数
  - 操作できる要素(id か name を持つもの)の並び順と、tabindex
  - スクリプトの差分。行の違いが「表示用の文字列だけ」か、処理に及ぶかを分ける
    セレクタ、イベント名、URL、属性名、比較している値、テンプレート文字列の ${} の中身は、
    文字列の中にあっても処理として扱う
  - スクリプトが参照している id とクラスが、修正後のマークアップやCSSに残っているか

結果は3種類:
  NG    機能が変わったおそれがある(消えた id、減った操作要素、入れ替わった順序、処理に及ぶスクリプトの変更など)
  確認  意図した変更かを人が見て判断するもの(増えた要素、文言だけのスクリプト変更など)
  OK    一致

NG が1つでもあれば終了コード 1 を返す。
これは静的な照合で、実際に操作して確かめるものではない。通っても、表示しての確認は別に行う。

Python 3.8 以降。標準ライブラリだけで動く。
"""
import argparse
import difflib
import json
import re
import sys
from collections import Counter
from html.parser import HTMLParser

CONTROLS = ("a", "button", "input", "select", "textarea", "form", "details", "summary", "label", "option")
# 減ると操作が失われる要素。label と option は「確認」にとどめる
STRICT_CONTROLS = ("a", "button", "input", "select", "textarea", "form", "details", "summary")
# 並び順を比べる要素(タブ順と、エラー時にフォーカスが移る先に関わる)
ORDERED = ("a", "button", "input", "select", "textarea", "summary")

# この呼び出しの最初の引数に書かれた文字列は、表示用の文言ではなく処理の一部として扱う
FUNC_CALL = re.compile(
    r"(?:\b(?:getElementById|querySelector|querySelectorAll|closest|matches|getElementsByClassName|getElementsByName"
    r"|getElementsByTagName|addEventListener|removeEventListener|dispatchEvent|CustomEvent|Event|fetch|open|import"
    r"|require|importScripts|getAttribute|setAttribute|hasAttribute|removeAttribute|toggleAttribute|getItem|setItem"
    r"|removeItem|createElement|pushState|replaceState|assign|URL|WebSocket|EventSource|Worker|sendBeacon|postMessage"
    r"|startsWith|endsWith|includes|indexOf|split|test|match)"
    r"|classList\.(?:add|remove|toggle|contains|replace)|location\.replace)\s*\(\s*$")
# 代入先がこれなら、文字列は処理の一部
FUNC_ASSIGN = re.compile(
    r"(?:\.(?:href|src|action|method|className|id|name|type|value|htmlFor|target|hash|search|pathname)|location)\s*=\s*$")
# 比較や分岐に使われている文字列、添字として使われている文字列
BEFORE_COMPARE = re.compile(r"(?:[=!]==?|\bcase|\bin|\[)\s*$")
AFTER_COMPARE = re.compile(r"^\s*(?:[=!]==?|\]|\bin\b)")
STRING = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`")


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.attrs = {k: Counter() for k in ("id", "name", "href", "action", "src", "type", "for", "role", "tabindex")}
        self.data = Counter()
        self.handlers = Counter()
        self.tags = Counter()
        self.classes = set()
        self.scripts = []
        self.styles = []
        self.order = []
        self._in = None
        self._buf = []

    def handle_starttag(self, tag, attrs):
        self.tags[tag] += 1
        d = dict(attrs)
        for k in self.attrs:
            if d.get(k) is not None:
                # script の type や src は別に扱う
                if tag == "script" and k == "type":
                    continue
                self.attrs[k][d[k]] += 1
        for k, v in attrs:
            if k.startswith("data-"):
                self.data["%s=%s" % (k, v if v is not None else "")] += 1
            elif k.startswith("on"):
                self.handlers["%s=%s" % (k, (v or "").strip())] += 1
        for c in (d.get("class") or "").split():
            self.classes.add(c)
        if tag in ORDERED and (d.get("type") or "").lower() != "hidden":
            if d.get("id"):
                self.order.append("#" + d["id"])
            elif d.get("name"):
                self.order.append("%s[name=%s]%s" % (tag, d["name"], "[value=%s]" % d["value"] if d.get("value") else ""))
        if tag in ("script", "style"):
            self._in = tag
            self._buf = []
            if tag == "script" and d.get("type") not in (None, "", "text/javascript", "module", "application/javascript"):
                self._in = "ignore"

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._in:
            text = "".join(self._buf)
            if self._in == "script" and text.strip():
                self.scripts.append(text)
            elif self._in == "style":
                self.styles.append(text)
            self._in = None

    def handle_data(self, data):
        if self._in:
            self._buf.append(data)


def load(path):
    p = Page()
    with open(path, encoding="utf-8") as f:
        p.feed(f.read())
    return p


def strip_strings(line, keep_functional=False):
    """文字列リテラルの中身を消す(文言だけの変更かどうかを見るため)。

    keep_functional が真なら、処理の一部として働く文字列は残す:
    セレクタやイベント名などの引数、href などへの代入、比較している値、テンプレート文字列の ${} の中身。
    """
    def blank(m):
        text = m.group(0)
        q = text[0]
        if not keep_functional:
            return q + q
        before, after = line[:m.start()], line[m.end():]
        if FUNC_CALL.search(before) or FUNC_ASSIGN.search(before) or BEFORE_COMPARE.search(before) or AFTER_COMPARE.search(after):
            return text
        if q == "`":
            return "`" + "".join(re.findall(r"\$\{[^}]*\}", text)) + "`"
        return q + q

    return STRING.sub(blank, line).strip()


def order_diff(before, after):
    """両方にある操作要素の並び順を比べる。違えば (修正前の並び, 修正後の並び) を返す。"""
    def numbered(seq):
        seen, out = Counter(), []
        for k in seq:
            seen[k] += 1
            out.append(k if seen[k] == 1 else "%s (%d個目)" % (k, seen[k]))
        return out

    a, b = numbered(before), numbered(after)
    common = set(a) & set(b)
    a = [k for k in a if k in common]
    b = [k for k in b if k in common]
    return (a, b) if a != b else None


def script_refs(scripts):
    """スクリプトが参照している id とクラスを、ゆるく拾う。"""
    text = "\n".join(scripts)
    ids, classes = set(), set()
    for m in re.finditer(r"getElementById\(\s*['\"]([\w-]+)['\"]", text):
        ids.add(m.group(1))
    for m in re.finditer(r"classList\.(?:add|remove|toggle|contains)\(\s*['\"]([\w-]+)['\"]", text):
        classes.add(m.group(1))
    for m in re.finditer(r"(?:querySelector(?:All)?|closest|matches)\(\s*(['\"])(.*?)\1", text):
        sel = m.group(2)
        ids.update(re.findall(r"#([A-Za-z_][\w-]*)", sel))
        classes.update(re.findall(r"\.([A-Za-z_][\w-]*)", sel))
    return ids, classes


def compare(before, after):
    ng, check, ok = [], [], []

    def multiset(label, a, b, strict=True):
        lost = sorted((a - b).elements())
        added = sorted((b - a).elements())
        if lost:
            (ng if strict else check).append("%s が消えた: %s" % (label, ", ".join(lost)))
        if added:
            check.append("%s が増えた: %s" % (label, ", ".join(added)))
        if not lost and not added and a:
            ok.append("%s は一致(%d 個)" % (label, sum(a.values())))

    multiset("id", before.attrs["id"], after.attrs["id"])
    multiset("name", before.attrs["name"], after.attrs["name"])
    multiset("リンク先(href)", before.attrs["href"], after.attrs["href"])
    multiset("送信先(action)", before.attrs["action"], after.attrs["action"])
    multiset("読み込み(src)", before.attrs["src"], after.attrs["src"])
    multiset("入力の種類(type)", before.attrs["type"], after.attrs["type"])
    multiset("data-* 属性", before.data, after.data)
    multiset("on* 属性", before.handlers, after.handlers)
    multiset("role", before.attrs["role"], after.attrs["role"], strict=False)
    multiset("label の for", before.attrs["for"], after.attrs["for"], strict=False)
    multiset("tabindex", before.attrs["tabindex"], after.attrs["tabindex"], strict=False)

    moved = order_diff(before.order, after.order)
    if moved:
        a_seq, b_seq = moved
        at = next(i for i, (x, y) in enumerate(zip(a_seq, b_seq)) if x != y)
        ng.append("操作要素の順序が変わった(タブ順やフォーカスの移る先が変わる)")
        ng.append("    修正前: … " + " → ".join(a_seq[at:at + 4]))
        ng.append("    修正後: … " + " → ".join(b_seq[at:at + 4]))
    elif before.order:
        ok.append("操作要素の順序は一致(id か name を持つ %d 個)" % len(before.order))

    changed = []
    for tag in CONTROLS:
        a, b = before.tags[tag], after.tags[tag]
        if a == b:
            continue
        msg = "<%s> の数 %d → %d" % (tag, a, b)
        if b < a and tag in STRICT_CONTROLS:
            ng.append("操作要素が減った: " + msg)
        else:
            check.append("要素の数が変わった: " + msg)
        changed.append(tag)
    if not changed:
        ok.append("操作要素の数は一致(%s)" % ", ".join("%s %d" % (t, before.tags[t]) for t in CONTROLS if before.tags[t]))

    # スクリプトの差分
    a_lines = [l.rstrip() for l in "\n".join(before.scripts).splitlines() if l.strip()]
    b_lines = [l.rstrip() for l in "\n".join(after.scripts).splitlines() if l.strip()]
    if a_lines == b_lines:
        ok.append("スクリプトは一致(%d 行)" % len(a_lines))
    else:
        a_code = [strip_strings(l) for l in a_lines]
        b_code = [strip_strings(l) for l in b_lines]
        a_func = [strip_strings(l, True) for l in a_lines]
        b_func = [strip_strings(l, True) for l in b_lines]
        if a_code == b_code and a_func == b_func:
            pairs = [(x.strip(), y.strip()) for x, y in zip(a_lines, b_lines) if x != y]
            check.append("スクリプトは表示用の文字列だけが変わった(%d 行。文言の変更かを見て確かめる)" % len(pairs))
            for x, y in pairs[:12]:
                check.append("    - %s" % x[:140])
                check.append("    + %s" % y[:140])
        elif a_code == b_code:
            pairs = [(x.strip(), y.strip()) for x, y, fx, fy in zip(a_lines, b_lines, a_func, b_func) if fx != fy]
            ng.append("スクリプトの中の、動作に関わる文字列が変わった(%d 行。セレクタ、イベント名、URL、属性名、比較している値、${} の中身など)" % len(pairs))
            for x, y in pairs[:12]:
                ng.append("    - %s" % x[:140])
                ng.append("    + %s" % y[:140])
            rest = sum(1 for x, y, fx, fy in zip(a_lines, b_lines, a_func, b_func) if x != y and fx == fy)
            if rest:
                check.append("スクリプトのほかの %d 行は、表示用の文字列だけが変わった" % rest)
        else:
            diff = [l for l in difflib.unified_diff(a_code, b_code, lineterm="", n=0)
                    if l[:1] in "+-" and l[:3] not in ("+++", "---")]
            ng.append("スクリプトの処理が変わった(文字列を除いても %d 行の差)" % len(diff))
            for l in diff[:16]:
                ng.append("    " + l[:140])

    # スクリプトが頼っている id とクラス
    ids, classes = script_refs(before.scripts)
    after_css = "\n".join(after.styles)
    before_css = "\n".join(before.styles)
    missing_ids = sorted(i for i in ids if before.attrs["id"][i] and not after.attrs["id"][i])
    if missing_ids:
        ng.append("スクリプトが参照する id が修正後にない: " + ", ".join(missing_ids))
    missing_cls = []
    for c in sorted(classes):
        pat = r"\.%s(?![\w-])" % re.escape(c)
        in_before = c in before.classes or re.search(pat, before_css)
        in_after = c in after.classes or re.search(pat, after_css)
        if in_before and not in_after:
            missing_cls.append(c)
    if missing_cls:
        ng.append("スクリプトが参照するクラスが修正後のマークアップにもCSSにもない: " + ", ".join(missing_cls))
    if not missing_ids and not missing_cls:
        ok.append("スクリプトが参照する id %d 個・クラス %d 個は修正後にも残っている" % (len(ids), len(classes)))

    return {"ng": ng, "check": check, "ok": ok}


def main():
    ap = argparse.ArgumentParser(description="修正前後のHTMLを突き合わせ、機能に関わる部分が変わっていないかを確かめる")
    ap.add_argument("before")
    ap.add_argument("after")
    ap.add_argument("--json", action="store_true", help="結果をJSONで出す")
    args = ap.parse_args()

    result = compare(load(args.before), load(args.after))
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for key, title in (("ng", "NG(機能が変わったおそれ)"), ("check", "確認(意図した変更かを見る)"), ("ok", "OK")):
            print("## %s: %d 件" % (title, len([l for l in result[key] if not l.startswith("    ")])))
            for line in result[key]:
                print(line if line.startswith("    ") else "- " + line)
            print()
        print("判定: " + ("NG あり。上の項目を直すか、意図した変更なら報告に書く" if result["ng"] else "機能に関わる部分の欠落は見つからなかった(静的な照合。表示しての確認は別に行う)"))
    return 1 if result["ng"] else 0


if __name__ == "__main__":
    sys.exit(main())
