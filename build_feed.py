"""Builds docs/feed.xml (RSS) + tall pin images from every live Etsy listing in the Printify shop.
Pinterest auto-publishes new feed items (up to 200 a day). Runs daily in GitHub Actions.
Needs env PRINTIFY_TOKEN. Pages serves the docs/ folder.

Each listing gets up to 3 pin variations with different photos and framings,
so Pinterest surfaces each product multiple times in different contexts.
"""
import json, os, re, sys, html, hashlib, urllib.request, random
from io import BytesIO
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from PIL import Image, ImageDraw, ImageFont

SHOP = 12148770
SITE = os.environ.get("SITE_URL", "https://maincharactercous.github.io/pins")
OUT = "docs"
W, H = 1000, 1500
HERE = os.path.dirname(os.path.abspath(__file__))

# Pin variation styles: each product gets up to 3 pins with different looks
GIFT_HOOKS = [
    "Perfect gift for the friend who gets it",
    "They'll actually wear this one",
    "The gift that gets a laugh every time",
    "For the person who's impossible to shop for",
    "A gift they won't return",
    "Holiday gift they'll actually love",
]

HOLIDAY_HOOKS = [
    "Christmas party approved",
    "Ugly sweater party alternative",
    "Holiday outfit sorted",
    "Family photo ready",
    "The shirt that wins Christmas",
    "Holiday dinner conversation starter",
]


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


def make_pin_standard(img_bytes, title, sub, path):
    """Original dark-bottom-bar style."""
    pin = Image.new("RGB", (W, H), (246, 241, 234))
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


def make_pin_gift(img_bytes, title, hook, path):
    """Warm gift-guide style with cream background and coral accent."""
    pin = Image.new("RGB", (W, H), (250, 244, 237))
    shot = Image.open(BytesIO(img_bytes)).convert("RGB")
    # Slightly smaller photo with rounded feel
    iw = W - 80
    shot = shot.resize((iw, iw), Image.LANCZOS)
    pin.paste(shot, (40, 40))
    d = ImageDraw.Draw(pin)
    # Coral accent bar under the photo
    bar_y = 40 + iw + 20
    d.rectangle([60, bar_y, W - 60, bar_y + 6], fill=(241, 100, 30))
    ft = font("Fraunces-VF.ttf", 52)
    fs = font("Inter-VF.ttf", 32)
    fh = font("Inter-VF.ttf", 38, wght=600)
    # Hook line
    y = bar_y + 40
    d.text((60, y), hook, font=fh, fill=(241, 100, 30))
    y += 56
    # Title
    lines = wrap(d, title, ft, W - 120)[:3]
    for ln in lines:
        d.text((60, y), ln, font=ft, fill=(28, 34, 44)); y += 68
    d.text((60, H - 70), "Main Character Co  ·  on Etsy", font=fs, fill=(170, 178, 190))
    pin.save(path, quality=86)


def make_pin_holiday(img_bytes, title, hook, path):
    """Dark holiday style with green accent."""
    pin = Image.new("RGB", (W, H), (22, 28, 24))
    shot = Image.open(BytesIO(img_bytes)).convert("RGB")
    shot = shot.resize((W, W), Image.LANCZOS)
    pin.paste(shot, (0, 0))
    d = ImageDraw.Draw(pin)
    # Dark green bottom panel
    d.rectangle([0, W, W, H], fill=(22, 42, 32))
    ft = font("Fraunces-VF.ttf", 56)
    fs = font("Inter-VF.ttf", 32)
    fh = font("Inter-VF.ttf", 36, wght=600)
    y = W + 40
    # Hook in gold
    d.text((60, y), hook, font=fh, fill=(218, 185, 107))
    y += 54
    # Title in cream
    lines = wrap(d, title, ft, W - 120)[:3]
    for ln in lines:
        d.text((60, y), ln, font=ft, fill=(250, 246, 240)); y += 72
    d.text((60, H - 70), "Main Character Co  ·  on Etsy", font=fs, fill=(140, 160, 150))
    pin.save(path, quality=86)


def pick_images(images, max_imgs=3):
    """Pick up to max_imgs distinct mockup photos from a listing."""
    front = [i for i in images if i.get("position") == "front" or i.get("is_default")]
    other = [i for i in images if i not in front]
    picks = []
    for i in front + other:
        if len(picks) >= max_imgs:
            break
        picks.append(i["src"])
    return picks


def write_page(key, title, sub, etsy):
    os.makedirs(os.path.join(OUT, "p"), exist_ok=True)
    t = html.escape(title)
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t} | Main Character Co</title>
<meta property="og:title" content="{t}">
<meta property="og:image" content="{SITE}/img/{key}.jpg">
<style>
body{{margin:0;font-family:system-ui,sans-serif;background:#1c222c;color:#faf6f0;display:flex;flex-direction:column;align-items:center;padding:24px 16px;gap:18px}}
img{{max-width:min(420px,100%);border-radius:10px}}
h1{{font-size:24px;text-align:center;margin:0;max-width:30ch}}
p{{margin:0;color:#f2a05a}}
a.buy{{background:#f1641e;color:#fff;text-decoration:none;font-weight:700;font-size:20px;padding:16px 28px;border-radius:999px}}
small{{color:#aab2be}}
</style>
</head>
<body>
<img src="../img/{key}.jpg" alt="{t}">
<h1>{t}</h1>
<p>{html.escape(sub)}</p>
<a class="buy" href="{etsy}">See it on Etsy</a>
<small>Main Character Co  ·  funny shirts on Etsy</small>
</body>
</html>
"""
    open(os.path.join(OUT, "p", key + ".html"), "w").write(page)


def main():
    tok = os.environ["PRINTIFY_TOKEN"].strip()
    os.makedirs(os.path.join(OUT, "img"), exist_ok=True)
    items, page = [], 1
    rng = random.Random(42)  # deterministic so rebuilds don't reshuffle hooks
    while True:
        d = json.loads(get(f"https://api.printify.com/v1/shops/{SHOP}/products.json?limit=50&page={page}", tok))
        for p in d["data"]:
            ext = p.get("external") or {}
            if not ext.get("id") or not p.get("visible", True):
                continue
            if not p.get("images"):
                continue
            title = short_title(p["title"])
            kind = "Sweatshirt" if "Sweatshirt" in p["title"] else "Tee"
            sub_standard = f"Funny holiday {kind.lower()} with free shipping"
            etsy_id = str(ext["id"])
            etsy = f"https://www.etsy.com/listing/{etsy_id}"
            created = p.get("created_at") or datetime.now(timezone.utc).isoformat()
            img_urls = pick_images(p["images"], 3)
            desc = re.sub(r"\s+", " ", p.get("description", ""))[:450]

            # -- Variation 1: standard pin (original style) --
            key1 = hashlib.md5(etsy_id.encode()).hexdigest()[:10]
            path1 = os.path.join(OUT, "img", key1 + ".jpg")
            if not os.path.exists(path1):
                make_pin_standard(get(img_urls[0]), title, sub_standard, path1)
            write_page(key1, title, sub_standard, etsy)
            items.append({"key": key1, "title": title, "desc": desc,
                          "link": f"{SITE}/p/{key1}.html", "img": f"{SITE}/img/{key1}.jpg",
                          "date": created})

            # -- Variation 2: gift guide pin --
            key2 = hashlib.md5((etsy_id + "-gift").encode()).hexdigest()[:10]
            path2 = os.path.join(OUT, "img", key2 + ".jpg")
            gift_hook = rng.choice(GIFT_HOOKS)
            img2 = img_urls[1] if len(img_urls) > 1 else img_urls[0]
            if not os.path.exists(path2):
                make_pin_gift(get(img2), title, gift_hook, path2)
            write_page(key2, title, gift_hook, etsy)
            # Stagger the pub date so Pinterest doesn't see them all at once
            dt2 = datetime.fromisoformat(created.replace(" ", "T").replace("Z", "+00:00")) + timedelta(hours=6)
            items.append({"key": key2, "title": f"{gift_hook} | {title}", "desc": desc,
                          "link": f"{SITE}/p/{key2}.html", "img": f"{SITE}/img/{key2}.jpg",
                          "date": dt2.isoformat()})

            # -- Variation 3: holiday style pin --
            key3 = hashlib.md5((etsy_id + "-holiday").encode()).hexdigest()[:10]
            path3 = os.path.join(OUT, "img", key3 + ".jpg")
            holiday_hook = rng.choice(HOLIDAY_HOOKS)
            img3 = img_urls[2] if len(img_urls) > 2 else img_urls[0]
            if not os.path.exists(path3):
                make_pin_holiday(get(img3), title, holiday_hook, path3)
            write_page(key3, title, holiday_hook, etsy)
            dt3 = datetime.fromisoformat(created.replace(" ", "T").replace("Z", "+00:00")) + timedelta(hours=12)
            items.append({"key": key3, "title": f"{holiday_hook} | {title}", "desc": desc,
                          "link": f"{SITE}/p/{key3}.html", "img": f"{SITE}/img/{key3}.jpg",
                          "date": dt3.isoformat()})

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
  <link>{SITE}/</link>
  <description>Funny matching family shirts and sweatshirts</description>{rows}
</channel>
</rss>
"""
    open(os.path.join(OUT, "feed.xml"), "w").write(feed)
    open(os.path.join(OUT, "index.html"), "w").write(
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"p:domain_verify\" content=\"e2ea8d7d66273fbbdae183edb528cea3\"/>\n<title>Main Character Co pins</title>\n</head>\n"
        "<body><p>Pin feed for <a href='https://www.etsy.com/shop/MainCharacterCoUS'>Main Character Co</a>.</p></body>\n</html>\n")
    n_listings = len(items) // 3
    print(f"{len(items)} pins from {n_listings} listings in feed")


if __name__ == "__main__":
    main()
