"""Builds Pinterest RSS feeds + tall pin images from every live Etsy listing in the Printify shop.
Runs daily in GitHub Actions. Needs env PRINTIFY_TOKEN. Pages serves the docs/ folder.

Each listing is sorted into one niche, and each niche has its own feed so Pinterest
can auto-publish it to its own board:
  docs/feed.xml               -> Christmas board (the original feed, already connected)
  docs/feed-dog.xml           -> Dog lover shirts board
  docs/feed-cat.xml           -> Cat lover shirts board
  docs/feed-thanksgiving.xml  -> Thanksgiving shirts board
  docs/feed-family.xml        -> Family matching shirts board
  docs/feed-funny.xml         -> Funny graphic tees board
Christmas pins keep their original guids so nothing already pinned gets posted twice.
"""
import json, os, re, html, hashlib, urllib.request, random
from io import BytesIO
from datetime import datetime, timezone, timedelta
from email.utils import format_datetime
from PIL import Image, ImageDraw, ImageFont

SHOP = 12148770
SITE = os.environ.get("SITE_URL", "https://maincharactercous.github.io/pins")
OUT = "docs"
W, H = 1000, 1500
HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = "Main Character Co  ·  on Etsy"

# Order matters: first match wins.
NICHES = [
    ("thanksgiving", r"\b(thanksgiving|turkey|gravy|stuffing|friendsgiving|gobble)\b"),
    ("dog", r"\b(dogs?|pug|puppy|puppies|corgi|doodle|dachshund|frenchie|golden retriever|dog mom|dog dad)\b"),
    ("cat", r"\b(cats?|kitten|kitty|meow|cat mom|cat dad|cat lady)\b"),
    ("family", r"\b(family|matching|crew|reunion|siblings?|most likely to)\b"),
    ("christmas", r"\b(christmas|xmas|holiday|santa|reindeer|elf|ugly sweater|festive|new year|winter)\b"),
]
NICHE_INFO = {
    "christmas": dict(feed="feed.xml", name="Funny Christmas Shirts",
                      kw="Funny Christmas Shirt, Holiday Gift",
                      sub="Funny Christmas {kind} with free shipping",
                      tags="funny christmas shirt, holiday party outfit, christmas gift idea, family christmas pajamas alternative"),
    "dog": dict(feed="feed-dog.xml", name="Funny Dog Lover Shirts",
                kw="Funny Dog Lover Shirt, Dog Mom Gift",
                sub="Funny dog lover {kind} with free shipping",
                tags="dog mom shirt, dog dad gift, funny dog shirt, gift for dog lovers"),
    "cat": dict(feed="feed-cat.xml", name="Funny Cat Lover Shirts",
                kw="Funny Cat Shirt, Cat Mom Gift",
                sub="Funny cat lover {kind} with free shipping",
                tags="cat mom shirt, cat lover gift, funny cat shirt, cat dad gift"),
    "thanksgiving": dict(feed="feed-thanksgiving.xml", name="Funny Thanksgiving Shirts",
                         kw="Funny Thanksgiving Shirt, Friendsgiving Tee",
                         sub="Funny Thanksgiving {kind} with free shipping",
                         tags="thanksgiving shirt, friendsgiving outfit, funny fall shirt, thanksgiving dinner tee"),
    "family": dict(feed="feed-family.xml", name="Funny Family Matching Shirts",
                   kw="Family Matching Shirt, Funny Group Tee",
                   sub="Funny family matching {kind} with free shipping",
                   tags="family matching shirts, family reunion shirt, group photo tee, funny sibling gift"),
    "funny": dict(feed="feed-funny.xml", name="Funny Graphic Tees",
                  kw="Funny Graphic Tee, Sarcastic Gift Shirt",
                  sub="Funny graphic {kind} with free shipping",
                  tags="funny graphic tee, sarcastic shirt, introvert shirt, gift for friend"),
}
HOOKS = {
    "christmas": ["Christmas party approved", "Ugly sweater party alternative", "Holiday outfit sorted",
                  "Family photo ready", "The shirt that wins Christmas", "Holiday dinner conversation starter"],
    "dog": ["For the dog mom who gets it", "Every dog parent needs this", "Gift for the dog obsessed",
            "Their dog would approve", "Made for dog people"],
    "cat": ["For the cat mom who gets it", "Every cat person needs this", "Gift for the cat obsessed",
            "Their cat would approve, maybe", "Made for cat people"],
    "thanksgiving": ["Thanksgiving dinner approved", "Friendsgiving outfit sorted", "Wear it to the family table",
                     "Pie first, questions later", "The Thanksgiving shirt they'll talk about"],
    "family": ["Match the whole crew", "Family photo ready", "Get one for everyone",
               "Group pic approved", "Reunion outfit sorted"],
    "funny": ["Perfect gift for the friend who gets it", "They'll actually wear this one",
              "The gift that gets a laugh every time", "For the person who's impossible to shop for",
              "A gift they won't return"],
}
# Accent colors per niche for the second pin style (bar, hook text)
ACCENT = {"christmas": (196, 52, 46), "dog": (214, 120, 40), "cat": (120, 92, 170),
          "thanksgiving": (190, 98, 30), "family": (36, 120, 140), "funny": (241, 100, 30)}


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
            f.set_variation_by_axes([wght])
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
    t = re.split(r",| \| ", t)[0]
    return re.sub(r"\s+", " ", t).strip()


def classify(p):
    text = p.get("title", "").lower()  # titles carry the buyer keywords; tags are too broad
    for niche, rx in NICHES:
        if re.search(rx, text):
            return niche
    return "funny"


def price_of(p):
    prices = [v["price"] for v in p.get("variants", []) if v.get("is_enabled") and v.get("price")]
    return f"{min(prices) / 100:.2f}" if prices else None


def make_pin_standard(img_bytes, title, sub, path):
    pin = Image.new("RGB", (W, H), (246, 241, 234))
    shot = Image.open(BytesIO(img_bytes)).convert("RGB").resize((W, W), Image.LANCZOS)
    pin.paste(shot, (0, 0))
    d = ImageDraw.Draw(pin)
    d.rectangle([0, W, W, H], fill=(28, 34, 44))
    ft, fs = font("Fraunces-VF.ttf", 64), font("Inter-VF.ttf", 34)
    y = W + 60
    for ln in wrap(d, title, ft, W - 120)[:3]:
        d.text((60, y), ln, font=ft, fill=(250, 246, 240)); y += 78
    d.text((60, y + 18), sub, font=fs, fill=(242, 160, 90))
    d.text((60, H - 70), BRAND, font=fs, fill=(170, 178, 190))
    pin.save(path, quality=86)


def make_pin_hook(img_bytes, title, hook, accent, path):
    pin = Image.new("RGB", (W, H), (250, 244, 237))
    iw = W - 80
    shot = Image.open(BytesIO(img_bytes)).convert("RGB").resize((iw, iw), Image.LANCZOS)
    pin.paste(shot, (40, 40))
    d = ImageDraw.Draw(pin)
    bar_y = 40 + iw + 20
    d.rectangle([60, bar_y, W - 60, bar_y + 6], fill=accent)
    ft, fs, fh = font("Fraunces-VF.ttf", 52), font("Inter-VF.ttf", 32), font("Inter-VF.ttf", 38, wght=600)
    y = bar_y + 40
    for ln in wrap(d, hook, fh, W - 120)[:2]:
        d.text((60, y), ln, font=fh, fill=accent); y += 50
    y += 6
    for ln in wrap(d, title, ft, W - 120)[:3]:
        d.text((60, y), ln, font=ft, fill=(28, 34, 44)); y += 68
    d.text((60, H - 70), BRAND, font=fs, fill=(170, 178, 190))
    pin.save(path, quality=86)


def make_pin_holiday(img_bytes, title, hook, path):
    pin = Image.new("RGB", (W, H), (22, 28, 24))
    shot = Image.open(BytesIO(img_bytes)).convert("RGB").resize((W, W), Image.LANCZOS)
    pin.paste(shot, (0, 0))
    d = ImageDraw.Draw(pin)
    d.rectangle([0, W, W, H], fill=(22, 42, 32))
    ft, fs, fh = font("Fraunces-VF.ttf", 56), font("Inter-VF.ttf", 32), font("Inter-VF.ttf", 36, wght=600)
    y = W + 40
    d.text((60, y), hook, font=fh, fill=(218, 185, 107)); y += 54
    for ln in wrap(d, title, ft, W - 120)[:3]:
        d.text((60, y), ln, font=ft, fill=(250, 246, 240)); y += 72
    d.text((60, H - 70), BRAND, font=fs, fill=(140, 160, 150))
    pin.save(path, quality=86)


def pick_images(images, n=3):
    front = [i for i in images if i.get("position") == "front" or i.get("is_default")]
    other = [i for i in images if i not in front]
    return [i["src"] for i in (front + other)[:n]]


def write_page(key, title, sub, etsy, price, desc):
    os.makedirs(os.path.join(OUT, "p"), exist_ok=True)
    t, dsc = html.escape(title), html.escape(desc[:280])
    price_meta = (f'<meta property="og:price:amount" content="{price}">\n'
                  f'<meta property="og:price:currency" content="USD">\n'
                  f'<meta property="product:price:amount" content="{price}">\n'
                  f'<meta property="product:price:currency" content="USD">\n'
                  f'<meta property="og:availability" content="instock">\n') if price else ""
    price_line = f"<p class=price>${price} on Etsy · free shipping</p>" if price else ""
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{t} | Main Character Co</title>
<meta name="description" content="{dsc}">
<meta property="og:type" content="product">
<meta property="og:site_name" content="Main Character Co">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{dsc}">
<meta property="og:url" content="{SITE}/p/{key}.html">
<meta property="og:image" content="{SITE}/img/{key}.jpg">
{price_meta}<style>
body{{margin:0;font-family:system-ui,sans-serif;background:#1c222c;color:#faf6f0;display:flex;flex-direction:column;align-items:center;padding:24px 16px;gap:18px}}
img{{max-width:min(420px,100%);border-radius:10px}}
h1{{font-size:24px;text-align:center;margin:0;max-width:30ch}}
p{{margin:0;color:#f2a05a;text-align:center}}
p.price{{color:#faf6f0;font-weight:700;font-size:20px}}
a.buy{{background:#f1641e;color:#fff;text-decoration:none;font-weight:700;font-size:20px;padding:16px 28px;border-radius:999px}}
small{{color:#aab2be}}
</style>
</head>
<body>
<img src="../img/{key}.jpg" alt="{t}">
<h1>{t}</h1>
<p>{html.escape(sub)}</p>
{price_line}
<a class="buy" href="{etsy}">See it on Etsy</a>
<small>Main Character Co  ·  funny shirts on Etsy</small>
</body>
</html>
"""
    open(os.path.join(OUT, "p", key + ".html"), "w").write(page)


def parse_dt(s):
    try:
        return datetime.fromisoformat(s.replace(" ", "T").replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def add_pin(items, key, maker, img_url, pin_title, sub, etsy, price, desc, date):
    path = os.path.join(OUT, "img", key + ".jpg")
    if not os.path.exists(path):
        maker(get(img_url), path)
    write_page(key, pin_title, sub, etsy, price, desc)
    items.append({"key": key, "title": pin_title, "desc": desc,
                  "link": f"{SITE}/p/{key}.html", "img": f"{SITE}/img/{key}.jpg", "date": date})


def main():
    tok = os.environ["PRINTIFY_TOKEN"].strip()
    os.makedirs(os.path.join(OUT, "img"), exist_ok=True)
    feeds = {n: [] for n in NICHE_INFO}
    rng = random.Random(42)
    page = 1
    while True:
        d = json.loads(get(f"https://api.printify.com/v1/shops/{SHOP}/products.json?limit=50&page={page}", tok))
        for p in d["data"]:
            ext = p.get("external") or {}
            if not ext.get("id") or not p.get("visible", True) or not p.get("images"):
                continue
            niche = classify(p)
            info = NICHE_INFO[niche]
            title = short_title(p["title"])
            kind = "sweatshirt" if "sweatshirt" in p["title"].lower() else "tee"
            sub = info["sub"].format(kind=kind)
            etsy_id = str(ext["id"])
            etsy = f"https://www.etsy.com/listing/{etsy_id}"
            price = price_of(p)
            created = parse_dt(p.get("created_at") or "")
            imgs = pick_images(p["images"], 3)
            img = lambda i: imgs[i] if len(imgs) > i else imgs[0]
            body = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", p.get("description", ""))).strip()
            price_txt = f" ${price} with free shipping on Etsy." if price else " Free shipping on Etsy."
            desc = f"{title}. {info['kw']}.{price_txt} {body}"[:440].rstrip() + f" #{' #'.join(t.replace(' ', '') for t in info['tags'].split(', ')[:3])}"
            kw_title = f"{title} | {info['kw']}"[:100]
            hook = lambda: rng.choice(HOOKS[niche])
            items = feeds[niche]

            if niche == "christmas":
                # Same guids as the original single feed, so the Christmas board never double-posts.
                k1 = hashlib.md5(etsy_id.encode()).hexdigest()[:10]
                k2 = hashlib.md5((etsy_id + "-gift").encode()).hexdigest()[:10]
                k3 = hashlib.md5((etsy_id + "-holiday").encode()).hexdigest()[:10]
                h2, h3 = hook(), hook()
                add_pin(items, k1, lambda b, pth: make_pin_standard(b, title, sub, pth), img(0),
                        kw_title, sub, etsy, price, desc, created.isoformat())
                add_pin(items, k2, lambda b, pth: make_pin_hook(b, title, h2, ACCENT[niche], pth), img(1),
                        f"{h2} | {title}"[:100], h2, etsy, price, desc, (created + timedelta(hours=6)).isoformat())
                add_pin(items, k3, lambda b, pth: make_pin_holiday(b, title, h3, pth), img(2),
                        f"{h3} | {title}"[:100], h3, etsy, price, desc, (created + timedelta(hours=12)).isoformat())
            else:
                # New guids per niche so each listing posts fresh to its own board.
                k1 = hashlib.md5(f"{etsy_id}-{niche}-a".encode()).hexdigest()[:10]
                k2 = hashlib.md5(f"{etsy_id}-{niche}-b".encode()).hexdigest()[:10]
                h2 = hook()
                add_pin(items, k1, lambda b, pth: make_pin_standard(b, title, sub, pth), img(0),
                        kw_title, sub, etsy, price, desc, created.isoformat())
                add_pin(items, k2, lambda b, pth: make_pin_hook(b, title, h2, ACCENT[niche], pth), img(1),
                        f"{h2} | {title}"[:100], h2, etsy, price, desc, (created + timedelta(hours=8)).isoformat())
        if page >= d.get("last_page", 1):
            break
        page += 1

    def rfc(s):
        return format_datetime(parse_dt(s).astimezone(timezone.utc))

    for niche, items in feeds.items():
        info = NICHE_INFO[niche]
        items.sort(key=lambda x: x["date"], reverse=True)
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
  <title>Main Character Co: {info['name']}</title>
  <link>{SITE}/</link>
  <description>{info['name']} from Main Character Co on Etsy</description>{rows}
</channel>
</rss>
"""
        open(os.path.join(OUT, info["feed"]), "w").write(feed)
        print(f"{info['feed']}: {len(items)} pins")

    links = "".join(f"<li><a href='{NICHE_INFO[n]['feed']}'>{NICHE_INFO[n]['name']}</a></li>" for n in NICHE_INFO)
    open(os.path.join(OUT, "index.html"), "w").write(
        "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n<meta name=\"p:domain_verify\" content=\"e2ea8d7d66273fbbdae183edb528cea3\"/>\n<title>Main Character Co pins</title>\n</head>\n"
        f"<body><p>Pin feeds for <a href='https://www.etsy.com/shop/MainCharacterCoUS'>Main Character Co</a>.</p><ul>{links}</ul></body>\n</html>\n")


if __name__ == "__main__":
    main()
