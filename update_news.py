# -*- coding: utf-8 -*-
"""医药头条 · 本地抓取脚本（Python 3 标准库，无需 pip install）
运行:  python update_news.py
产出:  news.js  —— index.html 打开时自动读取
"""
import json, os, re, html, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

# ============ 配置：换成你信任的 RSS / Atom 地址 ============
FEEDS = [
    {"name": "医药魔方", "url": "https://bydrug.pharmcube.com/rss"},
    {"name": "生物谷",   "url": "https://www.bioon.com/rss/news.xml"},
]
MAX_PER_FEED = 15     # 每个源最多取几条
SUMMARY_LEN  = 140    # 摘要截断长度
OUT_FILE     = os.path.join(os.path.dirname(os.path.abspath(__file__)), "news.js")
UA = "Mozilla/5.0 (compatible; PharmaHeadlineBot/1.0)"


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/rss+xml,application/atom+xml,application/xml,text/xml,*/*",
        "Accept-Encoding": "identity",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def decode(raw):
    """中文站常见 utf-8 / gb18030，依次尝试"""
    for enc in ("utf-8", "gb18030", "big5"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def clean(t):
    if not t:
        return ""
    t = re.sub(r"(?is)<(script|style).*?</\1>", " ", t)
    t = re.sub(r"(?s)<[^>]+>", " ", t)
    t = html.unescape(t)
    return re.sub(r"\s+", " ", t).strip()


def localname(tag):
    return tag.split("}")[-1].lower()


def first(node, name):
    for c in node:
        if localname(c.tag) == name:
            return c
    return None


def first_text(node, names):
    for n in names:
        c = first(node, n)
        if c is not None and (c.text or "").strip():
            return c.text.strip()
    return ""


def entry_link(node):
    """兼容 RSS2.0 的 <link>文本</link> 与 Atom 的 <link href=...>"""
    l = first(node, "link")
    if l is not None:
        if l.get("href"):
            return l.get("href").strip()
        if (l.text or "").strip():
            return l.text.strip()
    for c in node:
        if localname(c.tag) == "link" and c.get("href"):
            return c.get("href").strip()
    for k, v in node.attrib.items():          # RSS 1.0 的 rdf:about
        if k.endswith("about"):
            return v.strip()
    return ""


def parse_time(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def parse_feed(text, source):
    out = []
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return out
    for e in root.iter():
        if localname(e.tag) not in ("item", "entry"):
            continue
        title = clean(first_text(e, ("title",)))
        link = entry_link(e)
        if not title or not link:
            continue
        raw_sum = first_text(e, ("description", "summary", "content", "encoded"))
        dt = parse_time(first_text(e, ("pubdate", "published", "updated", "date")))
        out.append({
            "title": title,
            "link": link,
            "time": dt.isoformat() if dt else "",
            "summary": clean(raw_sum)[:SUMMARY_LEN],
            "source": source,
            "_ts": dt.timestamp() if dt else 0,
        })
    return out


def main():
    all_items = []
    for f in FEEDS:
        try:
            items = parse_feed(decode(fetch(f["url"])), f["name"])[:MAX_PER_FEED]
            if items:
                all_items += items
                print("[OK]   %s: %d 条" % (f["name"], len(items)))
            else:
                print("[WARN] %s: 未解析到条目（源可能失效或没有 RSS）" % f["name"])
        except Exception as ex:
            print("[FAIL] %s: %s %s" % (f["name"], type(ex).__name__, ex))

    if not all_items:
        print("本次没抓到任何条目，保留原有 news.js 不变。")
        return 1

    seen, uniq = set(), []
    for it in sorted(all_items, key=lambda x: x["_ts"], reverse=True):
        if it["link"] in seen:
            continue
        seen.add(it["link"])
        uniq.append(it)

    payload = {
        "updatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "items": [{k: v for k, v in it.items() if not k.startswith("_")} for it in uniq],
    }
    with open(OUT_FILE, "w", encoding="utf-8") as fp:
        fp.write("window.PHARMA_NEWS = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n")
    print("已写入 %s，共 %d 条。" % (OUT_FILE, len(uniq)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
