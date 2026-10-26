"""Builds docs/feed.xml (RSS) + tall pin images from every live Etsy listing in the Printify shop.
Pinterest auto-publishes new feed items (up to 200 a day). Runs daily in GitHub Actions.
Needs env PRINTIFY_TOKEN. Pages serves the docs/ folder.
"""
import json, os, re, sys, html, hashlib, urllib.request
from io import BytesIO
from datetime import datetime, timezone
from email.utils import format_datetime
from PIL import Image, ImageDraw, ImageFont

SHOP = 12148770
SITE = os.environ.get("SITE_URL", "https://maincharactercous.github.io/pins")
OUT = "docs"
W, H = 1000, 1500
HERE = os.path.dirname(os.path.abspath(__file__))


def get(url, tok=None):
    h = {"User-Agent": "MainCharacterPins"}
    if tok:
        h["Authorization"] = "Bearer " + tok
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=90) as r:
        return r.read()


def font(name, size, wght=None):
    f = ImageFont.truetype(os.path.join(HERE, name), size)
    if wght:
        try:
            f.set_variation_by_axes([wght] if "Inter" in name else [wght])
        except Exception:
            pass
    return f


def wrap(draw, text, f, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=f) <= width:
            cur = t
        else:
            lines.append(cur); cur = w
    if cur:
        lines.append(cur)
    return lines


def short_title(t):
    t = re.split(r",", t)[0]
    return re.sub(r"\s+", " ", t).strip()


def make_pin(img_bytes, title, sub, path):
    bg = (246, 241, 234)
    pin = Image.new("RGB", (W, H), bg)
    shot = Image.open(BytesIO(img_bytes)).convert("RGB")
    shot = shot.resize((W, W), Image.LANCZOS)
    pin.paste(shot, (0, 0))
    d = ImageDraw.Draw(pin)
    d.rectangle([0, W, W, H], fill=(28, 34, 44))
    ft = font("Fraunces-VF.ttf", 64)
    fs = font("Inter-VF.ttf", 34)
    lines = wrap(d, title, ft, W - 120)[:3]
    y = W + 60
    for ln in lines:
        d.text((60, y), ln, font=ft, fill=(250, 246, 240)); y += 78
    d.text((60, y + 18), sub, font=fs, fill=(242, 160, 90))
    d.text((60, H - 70), "Main Character Co  ·  on Etsy", font=fs, fill=(170, 178, 190))
    pin.save(path, quality=86)


def main():
    tok = os.environ["PRINTIFY_TOKEN"].strip()
    os.makedirs(os.path.join(OUT, "img"), exist_ok=True)
    items, page = [], 1
    while True:
        d = json.loads(get(f"https://api.printify.com/v1/shops/{SHOP}/products.json?limit=50&page={page}", tok))
        for p in d["data"]:
            ext = p.get("external") or {}
            if not ext.get("id") or not p.get("visible", True):
                continue
            img = next((i["src"] for i in p["images"] if i.get("is_default")), p["images"][0]["src"] if p["images"] else None)
            if not img:
                continue
            title = short_title(p["title"])
            kind = "Sweatshirt" if "Sweatshirt" in p["title"] else "Tee"
            sub = f"Funny family Christmas {kind.lower()} · free shipping"
            key = hashlib.md5(str(ext["id"]).encode()).hexdigest()[:10]
            path = os.path.join(OUT, "img", key + ".jpg")
            if not os.path.exists(path):
                make_pin(get(img), title, sub, path)
            items.append({"key": key, "title": title, "desc": re.sub(r"\s+", " ", p.get("description", ""))[:450],
                          "link": f"https://www.etsy.com/listing/{ext['id']}", "img": f"{SITE}/img/{key}.jpg",
                          "date": p.get("created_at") or datetime.now(timezone.utc).isoformat()})
        if page >= d.get("last_page", 1):
            break
        page += 1
    items.sort(key=lambda x: x["date"], reverse=True)

    def rfc(s):
        try:
            return format_datetime(datetime.fromisoformat(s.replace(" ", "T").replace("Z", "+00:00")).astimezone(timezone.utc))
        except Exception:
            return format_datetime(datetime.now(timezone.utc))
    rows = "".join(f"""
  <item>
    <title>{html.escape(i['title'])}</title>
    <link>{html.escape(i['link'])}</link>
    <guid isPermaLink="false">{i['key']}</guid>
    <pubDate>{rfc(i['date'])}</pubDate>
    <description>{html.escape(i['desc'])}</description>
    <enclosure url="{i['img']}" type="image/jpeg" length="0"/>
    <media:content url="{i['img']}" medium="image" type="image/jpeg"/>
  </item>""" for i in items)
    feed = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/">
<channel>
  <title>Main Character Co</title>
  <link>https://www.etsy.com/shop/MainCharacterCoUS</link>
  <description>Funny matching family shirts and sweatshirts</description>{rows}
</channel>
</rss>
"""
    open(os.path.join(OUT, "feed.xml"), "w").write(feed)
    open(os.path.join(OUT, "index.html"), "w").write(
        "<!doctype html><meta charset=utf-8><meta name=\"p:domain_verify\" content=\"e2ea8d7d66273fbbdae183edb528cea3\"/><title>Main Character Co pins</title>"
        "<p>Pin feed for <a href='https://www.etsy.com/shop/MainCharacterCoUS'>Main Character Co</a>.</p>")
    print(f"{len(items)} items in feed")


if __name__ == "__main__":
    main()
