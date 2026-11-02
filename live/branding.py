"""Channel images for Gita Sarathi Live, drawn with the stream's own fonts and colours (like EscapeArenaLive's
branding.js).

    python branding.py              writes branding/avatar.png, banner.png, thumbnail.png, watermark.png

The emblem: a gold chariot wheel (Sarathi, the charioteer) whose hub is a peacock-feather eye (Krishna).
"""
from __future__ import annotations

import math
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from gitalive.fonts import ensure  # noqa: E402
from gitalive.render import Fonts, Renderer  # noqa: E402

NAVY_STOPS = [(0, (27, 34, 86)), (128, (11, 15, 43)), (255, (3, 4, 11))]
GOLD, GOLD_LIGHT, GOLD_DEEP = (242, 181, 68), (255, 222, 150), (190, 128, 30)
RED, INK = (229, 32, 46), (255, 255, 255)
OUT = HERE / "branding"

# A verse for the thumbnail's stream frame (Swami Swarupananda's 1909 translation, public domain)
SAMPLE = {"type": "verse", "id": "brand", "progress": {"index": 84, "total": 701},
          "verse": {"id": "BG 2.47", "chapter": 2, "verse": 47, "chapter_name": "Sankhya Yoga", "chapter_name_sanskrit": "सांख्ययोग",
                    "speaker": "Krishna", "addressed_to": "Arjuna", "speaker_hindi": "श्रीकृष्ण", "listener_hindi": "अर्जुन",
                    "sanskrit": "कर्मण्येवाधिकारस्ते मा फलेषु कदाचन।\nमा कर्मफलहेतुर्भूर्मा ते सङ्गोऽस्त्वकर्मणि।।",
                    "transliteration": "karmaṇy-evādhikāras te mā phaleṣhu kadāchana\nmā karma-phala-hetur bhūr mā te saṅgo ’stvakarmaṇi",
                    "translation": "Thy right is to work only; but never to the fruits thereof. Be thou not the producer of the "
                                   "fruits of (thy) actions; neither let thy attachment be towards inaction.",
                    "translation_source": "Swami Swarupananda (1909)"}}


def background(w: int, h: int, cx: float, cy: float, radius: float, glow: list[tuple] = (), stars: int = 300, seed: int = 7) -> Image.Image:
    """The stream's night sky: navy radial gradient, stars, soft gold glows."""
    r = int(radius)
    g = Image.radial_gradient("L").resize((2 * r, 2 * r))
    g = g.crop((int(r - cx), int(r - cy), int(r - cx) + w, int(r - cy) + h))

    def lut(ch):
        out = []
        for v in range(256):
            for (a, ca), (b, cb) in zip(NAVY_STOPS, NAVY_STOPS[1:]):
                if a <= v <= b:
                    out.append(round(ca[ch] + (cb[ch] - ca[ch]) * (v - a) / (b - a)))
                    break
        return out
    img = Image.merge("RGB", [g.point(lut(i)) for i in range(3)]).convert("RGBA")
    over = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    rnd = random.Random(seed)
    for _ in range(stars):
        a = int(rnd.uniform(0.1, 0.6) * 255)
        s = 2 if rnd.random() < 0.12 else 1
        x, y = rnd.uniform(0, w), rnd.uniform(0, h)
        d.rectangle((x, y, x + s, y + s), fill=(255, 255, 255, a))
    img = Image.alpha_composite(img, over)
    if glow:
        gl = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gl)
        for (x0, y0, x1, y1, alpha) in glow:
            gd.ellipse((x0, y0, x1, y1), fill=(*GOLD, alpha))
        img = Image.alpha_composite(img, gl.filter(ImageFilter.GaussianBlur(max(w, h) / 25)))
    return img


def emblem(size: int) -> Image.Image:
    """The chariot wheel with a peacock-feather hub, on a transparent background (drawn 4x, then smoothed)."""
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = S / 2
    R = S * 0.44                      # outer edge of the rim
    rim = S * 0.075
    # studs around the rim
    for k in range(16):
        a = 2 * math.pi * k / 16
        x, y = c + math.cos(a) * (R - rim / 2), c + math.sin(a) * (R - rim / 2)
        rs = S * 0.026
        d.ellipse((x - rs, y - rs, x + rs, y + rs), fill=GOLD_LIGHT)
    # rim: deep gold ring with a light inner edge
    d.ellipse((c - R, c - R, c + R, c + R), outline=GOLD, width=int(rim))
    d.ellipse((c - R + rim, c - R + rim, c + R - rim, c + R - rim), outline=GOLD_LIGHT, width=int(S * 0.012))
    d.ellipse((c - R + rim * 0.35, c - R + rim * 0.35, c + R - rim * 0.35, c + R - rim * 0.35), outline=GOLD_DEEP, width=int(S * 0.006))
    # 12 tapered spokes
    hub = S * 0.17
    inner = R - rim
    for k in range(12):
        a = 2 * math.pi * k / 12 + math.pi / 12
        ca, sa = math.cos(a), math.sin(a)
        px, py = -sa, ca
        w0, w1 = S * 0.030, S * 0.016
        pts = [(c + ca * hub + px * w0, c + sa * hub + py * w0), (c + ca * inner + px * w1, c + sa * inner + py * w1),
               (c + ca * inner - px * w1, c + sa * inner - py * w1), (c + ca * hub - px * w0, c + sa * hub - py * w0)]
        d.polygon(pts, fill=GOLD)
        d.line([(c + ca * hub, c + sa * hub), (c + ca * inner, c + sa * inner)], fill=GOLD_LIGHT, width=int(S * 0.005))
    # hub ring
    d.ellipse((c - hub, c - hub, c + hub, c + hub), fill=GOLD)
    # peacock-feather eye inside the hub: gold-green, teal, royal blue, a dark heart
    for scale, col in ((0.86, (176, 168, 52)), (0.72, (24, 150, 142)), (0.50, (34, 70, 170)), (0.26, (10, 16, 52))):
        rx, ry = hub * scale * 0.78, hub * scale
        dy = hub * (1 - scale) * 0.18
        d.ellipse((c - rx, c - ry + dy, c + rx, c + ry + dy), fill=col)
    d.ellipse((c - hub * 0.07, c - hub * 0.02, c + hub * 0.07, c + hub * 0.14), fill=(120, 200, 230))   # a glint
    d.ellipse((c - hub, c - hub, c + hub, c + hub), outline=GOLD_LIGHT, width=int(S * 0.008))
    return img.resize((size, size), Image.LANCZOS)


def with_glow(base: Image.Image, em: Image.Image, x: int, y: int, strength: int = 120) -> Image.Image:
    halo = Image.new("RGBA", base.size, (0, 0, 0, 0))
    hd = ImageDraw.Draw(halo)
    s = em.width
    hd.ellipse((x + s * 0.08, y + s * 0.08, x + s * 0.92, y + s * 0.92), fill=(*GOLD, strength))
    base = Image.alpha_composite(base, halo.filter(ImageFilter.GaussianBlur(s / 6)))
    base.alpha_composite(em, (x, y))
    return base


def spaced(text: str, n: int = 1) -> str:
    return (" " * n).join(text)


def avatar(F: Fonts) -> Image.Image:
    img = background(800, 800, 400, 400, 620, stars=160)
    em = emblem(640)
    return with_glow(img, em, 80, 80, 110).convert("RGB")


def watermark() -> Image.Image:
    em = emblem(150)
    return em


def banner(F: Fonts) -> Image.Image:
    W, H = 2560, 1440
    img = background(W, H, 1280, 720, 1900, glow=[(500, 450, 1300, 990, 60), (1100, 520, 2100, 920, 38)], stars=700)
    sx, sy, sw, sh = 507, 508, 1546, 423            # visible on every device
    em = emblem(380)
    img = with_glow(img, em, sx + 10, sy + (sh - 380) // 2, 100)
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    tx = sx + 10 + 380 + 70
    d.text((tx, sy + 22), "गीता सारथी", font=F("hindi_serif", 150), fill=GOLD, anchor="la")
    title_w = F("hindi_serif", 150).getlength("गीता सारथी")
    # LIVE 24/7 pill beside the title
    px, py = tx + title_w + 40, sy + 92
    d.rounded_rectangle((px, py, px + 250, py + 64), radius=32, fill=RED)
    d.ellipse((px + 24, py + 22, px + 44, py + 42), fill=INK)
    d.text((px + 58, py + 32), "LIVE 24/7", font=F("ui_bold", 34), fill=INK, anchor="lm")
    d.text((tx + 4, sy + 230), spaced("GITA SARATHI · BHAGAVAD GITA LIVE"), font=F("ui_semibold", 34), fill=(255, 255, 255, 200), anchor="la")
    d.text((tx + 4, sy + 292), "भगवद्गीता, हर श्लोक हर दिन  ·  Ask life's questions in chat", font=F("ui", 40), fill=(236, 230, 210), anchor="la")
    y = sy + 362
    x = tx + 4
    for tag in ("संस्कृत", "हिंदी", "English", "@GitaSarathiLive"):
        tf = F("ui_semibold", 28)
        tw = tf.getlength(tag) + 40
        d.rounded_rectangle((x, y, x + tw, y + 46), radius=23, fill=(255, 255, 255, 22), outline=(242, 181, 68, 140), width=2)
        d.text((x + tw / 2, y + 23), tag, font=tf, fill=INK, anchor="mm")
        x += tw + 14
    return Image.alpha_composite(img, lay).convert("RGB")


def thumbnail(F: Fonts) -> Image.Image:
    W, H = 1280, 720
    img = background(W, H, 420, 330, 1100, glow=[(40, 120, 760, 520, 70), (860, 60, 1240, 680, 50)], stars=260)
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    # left: LIVE pill, title, the ask
    d.rounded_rectangle((64, 58, 64 + 268, 58 + 66), radius=33, fill=RED)
    d.ellipse((90, 81, 110, 101), fill=INK)
    d.text((124, 91), "LIVE 24/7", font=F("ui_bold", 38), fill=INK, anchor="lm")
    d.text((58, 150), "भगवद्गीता", font=F("hindi_serif", 150), fill=GOLD, anchor="la")
    d.text((64, 360), "अपना सवाल पूछिए", font=F("ui_bold", 72), fill=INK, anchor="la")
    d.text((66, 460), "Ask the Gita  ·  Every verse, 24/7", font=F("ui_semibold", 40), fill=(220, 226, 245), anchor="la")
    img = Image.alpha_composite(img, lay)
    em = emblem(120)
    img = with_glow(img, em, 60, 560, 80)
    d = ImageDraw.Draw(img)
    d.text((196, 620), "गीता सारथी", font=F("hindi_serif", 56), fill=GOLD, anchor="lm")
    # right: a real frame of the stream, in a phone, slightly tilted
    r = Renderer(F, trigger="@GitaSarathiLive")
    r.set_queue(["Asha", "Ravi", "Priya"], ["Meera", "Arjun"])
    r.build_scene(SAMPLE)
    frame = Image.frombytes("RGB", (1080, 1920), r.frame(1.0, 0.3)).resize((342, 608), Image.LANCZOS)
    phone = Image.new("RGBA", (342 + 24, 608 + 24), (0, 0, 0, 0))
    pd = ImageDraw.Draw(phone)
    pd.rounded_rectangle((0, 0, phone.width - 1, phone.height - 1), radius=44, fill=(14, 16, 28), outline=(242, 181, 68, 210), width=3)
    mask = Image.new("L", frame.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, frame.width - 1, frame.height - 1), radius=34, fill=255)
    phone.paste(frame, (12, 12), mask)
    phone = phone.rotate(-5, resample=Image.BICUBIC, expand=True)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    px, py = 880, max(0, (H - phone.height) // 2)
    sd.rounded_rectangle((px + 18, py + 22, px + phone.width - 6, py + phone.height + 4), radius=50, fill=(0, 0, 0, 150))
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(18)))
    img.alpha_composite(phone, (px, py))
    return img.convert("RGB")


def main() -> int:
    F = Fonts(ensure(HERE / "fonts", log=print))
    OUT.mkdir(exist_ok=True)
    for name, im in (("avatar.png", avatar(F)), ("banner.png", banner(F)), ("thumbnail.png", thumbnail(F)),
                     ("watermark.png", watermark())):
        im.save(OUT / name, optimize=True)
        print(f"{name:14} {im.size[0]}x{im.size[1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
