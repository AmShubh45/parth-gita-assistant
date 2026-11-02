"""The headless renderer: draws the vertical 1080x1920 broadcast frame by frame, like EscapeArenaLive's game.js.

Three layers keep it cheap on a cloud CPU:
- static (built once): background, LIVE / 24/7 pills, the title, panels and the call to action;
- scene (built when something new goes on air): the verse or the answer, the progress panel, the question queue;
- dynamic (every frame, a few small shapes): the pulsing LIVE dot, a speaking waveform, the CTA border, "…" dots.
Text is laid out with Pillow + raqm (HarfBuzz), so Devanagari conjuncts render correctly."""
from __future__ import annotations

import colorsys
import logging
import math
import random
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

log = logging.getLogger("gitalive.render")

W, H = 1080, 1920
GOLD, SAFFRON, TEAL, RED = (242, 181, 68), (255, 153, 51), (92, 196, 203), (229, 32, 46)
INK, MUTED, DIM = (255, 255, 255), (178, 186, 214), (120, 128, 160)
PANEL = (255, 255, 255, 13)
PANEL_LINE = (255, 255, 255, 28)
SP_HI = {"Krishna": "श्रीकृष्ण", "Arjuna": "अर्जुन", "Sanjaya": "संजय", "Dhritarashtra": "धृतराष्ट्र"}
CHAPTERS = 18

# Layout boxes (EscapeArena's vertical grid)
TOP_Y = 44
STATS = (40, 290, 1000, 128)
STAGE = (40, 440, 1000, 862)        # y 440 .. 1302
NEXTQ = (40, 1326, 490, 384)
DONEQ = (550, 1326, 490, 384)
STRIP = (40, 1728, 1000, 70)
CTA_Y, CTA_H = 1820, 58


class Fonts:
    def __init__(self, paths: dict[str, Path]):
        self.paths = paths
        self._cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def __call__(self, name: str, size: float) -> ImageFont.FreeTypeFont:
        key = (name, max(8, int(round(size))))
        f = self._cache.get(key)
        if f is None:
            f = self._cache[key] = ImageFont.truetype(str(self.paths[name]), key[1], layout_engine=ImageFont.Layout.RAQM)
        return f


def wrap(text: str, font: ImageFont.FreeTypeFont, width: float) -> list[str]:
    """Greedy word wrap that respects the shaped width of each line."""
    out: list[str] = []
    for para in (text or "").split("\n"):
        words, line = para.split(), ""
        for w in words:
            trial = f"{line} {w}".strip()
            if not line or font.getlength(trial) <= width:
                line = trial
            else:
                out.append(line)
                line = w
        if line:
            out.append(line)
    return out


def ellipsize(lines: list[str], font, width: float, max_lines: int) -> list[str]:
    if len(lines) <= max_lines:
        return lines
    keep = lines[:max_lines]
    last = keep[-1]
    while last and font.getlength(last + "…") > width:
        last = last[:-1].rstrip()
    keep[-1] = last + "…"
    return keep


def rr(d: ImageDraw.ImageDraw, box, radius, fill=None, outline=None, width=1):
    x, y, w, h = box
    d.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=fill, outline=outline, width=width)


class Flow:
    """Measures a column of text and boxes first, so a scene can shrink until it fits, then draws it."""

    def __init__(self, fonts: Fonts, x: float, width: float, scale: float = 1.0):
        self.fonts, self.x, self.w, self.f = fonts, x, width, scale
        self.ops: list[tuple] = []
        self.h = 0.0

    def gap(self, px: float) -> None:
        self.h += px * self.f

    def text(self, s: str, font: str, size: float, color, align: str = "center", lh: float = 1.38,
             max_lines: int | None = None) -> None:
        if not s:
            return
        fnt = self.fonts(font, size * self.f)
        lines = wrap(s, fnt, self.w)
        if max_lines:
            lines = ellipsize(lines, fnt, self.w, max_lines)
        step = fnt.size * lh
        for ln in lines:
            if align == "center":
                self.ops.append(("text", self.x + self.w / 2, self.h, ln, fnt, color, "ma"))
            elif align == "right":
                self.ops.append(("text", self.x + self.w, self.h, ln, fnt, color, "ra"))
            else:
                self.ops.append(("text", self.x, self.h, ln, fnt, color, "la"))
            self.h += step

    def row(self, left: str, right: str, font: str, size: float, lcolor, rcolor) -> None:
        fnt = self.fonts(font, size * self.f)
        self.ops.append(("text", self.x, self.h, left, fnt, lcolor, "la"))
        self.ops.append(("text", self.x + self.w, self.h, right, fnt, rcolor, "ra"))
        self.h += fnt.size * 1.4

    def card(self, build, pad: float = 22, fill=PANEL, outline=PANEL_LINE, bar=None, radius: float = 20) -> None:
        p = pad * self.f
        inner = Flow(self.fonts, self.x + p + (6 if bar else 0), self.w - 2 * p - (6 if bar else 0), self.f)
        build(inner)
        top, height = self.h, inner.h + 2 * p
        self.ops.append(("box", self.x, top, self.w, height, fill, outline, bar, radius * self.f))
        for op in inner.ops:
            self.ops.append((op[0], op[1], op[2] + top + p, *op[3:]))
        self.h += height

    def draw(self, d: ImageDraw.ImageDraw, y0: float) -> None:
        for op in self.ops:
            if op[0] == "text":
                _, x, y, s, fnt, color, anchor = op
                d.text((x, y0 + y), s, font=fnt, fill=color, anchor=anchor)
            else:
                _, x, y, w, h, fill, outline, bar, radius = op
                rr(d, (x, y0 + y, w, h), radius, fill=fill, outline=outline, width=2)
                if bar:
                    d.rounded_rectangle((x, y0 + y + 10, x + 6, y0 + y + h - 10), radius=3, fill=bar)


class Renderer:
    def __init__(self, fonts: Fonts, trigger: str = "@gitalive"):
        if not features.check("raqm"):
            log.error("Pillow has no raqm text layout: Hindi and Sanskrit will render wrongly. "
                      "Install libraqm (Docker image does) or a Pillow build with raqm.")
        self.F = fonts
        self.trigger = trigger
        self.lock = threading.Lock()
        self.static = self._build_static()
        self.scene_rgb: Image.Image = self.static.convert("RGB")
        self.scene: dict = {"type": "idle"}
        self.waiting: list[str] = []
        self.answered: list[str] = []
        self.progress = (0, 701, 1)
        self.last_verse: dict | None = None
        self._scaled: dict[float, Image.Image] = {}
        self.cta_box = (0, 0, 0, 0)
        self.dots_at: tuple[float, float] | None = None
        self.build_scene({"type": "idle"})

    # ------------------------------------------------------------------ static layer
    def _build_static(self) -> Image.Image:
        cx, cy, radius = 540, 900, 1300
        g = Image.radial_gradient("L").resize((radius * 2, radius * 2))
        g = g.crop((radius - cx, radius - cy, radius - cx + W, radius - cy + H))
        stops = [(0, (27, 34, 86)), (128, (11, 15, 43)), (255, (3, 4, 11))]

        def lut(ch):
            out = []
            for v in range(256):
                for (a, ca), (b, cb) in zip(stops, stops[1:]):
                    if a <= v <= b:
                        t = (v - a) / (b - a)
                        out.append(round(ca[ch] + (cb[ch] - ca[ch]) * t))
                        break
            return out
        img = Image.merge("RGB", [g.point(lut(i)) for i in range(3)]).convert("RGBA")
        over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(over)
        rnd = random.Random(7)
        for _ in range(260):
            a = int(rnd.uniform(0.08, 0.55) * 255)
            s = 2 if rnd.random() < 0.1 else 1
            x, y = rnd.uniform(0, W), rnd.uniform(0, H)
            d.rectangle((x, y, x + s, y + s), fill=(255, 255, 255, a))
        img = Image.alpha_composite(img, over)
        # soft gold glow behind the title and the stage
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        gd.ellipse((240, 60, 840, 260), fill=(242, 181, 68, 46))
        gd.ellipse((140, 620, 940, 1140), fill=(242, 181, 68, 22))
        img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(70)))

        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        F = self.F
        # top bar: LIVE pill + 24/7 (the dot pulses in the dynamic layer)
        rr(d, (40, TOP_Y, 116, 46), 23, fill=RED)
        d.text((84, TOP_Y + 23), "LIVE", font=F("ui_bold", 26), fill=INK, anchor="lm")
        d.text((172, TOP_Y + 23), "24/7", font=F("ui_semibold", 26), fill=(255, 255, 255, 150), anchor="lm")
        # title
        d.text((540, 150), "गीता सारथी", font=F("hindi_serif", 96), fill=GOLD, anchor="mm")
        d.text((540, 222), "G I T A   S A R A T H I   ·   L I V E", font=F("ui_semibold", 24), fill=(255, 255, 255, 170), anchor="mm")
        d.text((540, 262), "भगवद्गीता, श्लोक दर श्लोक  ·  Ask anything in chat", font=F("ui", 26), fill=(255, 255, 255, 175), anchor="mm")
        # panels
        for box, r in ((STATS, 24), (STAGE, 28), (NEXTQ, 24), (DONEQ, 24), (STRIP, 35)):
            rr(d, box, r, fill=PANEL, outline=PANEL_LINE, width=2)
        lab = F("ui_bold", 20)
        d.text((NEXTQ[0] + 28, NEXTQ[1] + 30), "अगले प्रश्न · NEXT QUESTIONS", font=lab, fill=(255, 255, 255, 140), anchor="la")
        d.text((DONEQ[0] + 28, DONEQ[1] + 30), "अभी जवाब दिए · JUST ANSWERED", font=lab, fill=(255, 255, 255, 140), anchor="la")
        d.text((STRIP[0] + 32, STRIP[1] + 35), "18 अध्याय", font=F("ui_bold", 22), fill=(255, 255, 255, 150), anchor="lm")
        # call to action (border colour cycles in the dynamic layer)
        cta = f"चैट में लिखें  {self.trigger}  + अपना सवाल"
        cf = F("ui_bold", 30)
        tw = cf.getlength(cta)
        self.cta_box = (540 - tw / 2 - 34, CTA_Y, tw + 68, CTA_H)
        rr(d, self.cta_box, 29, fill=(255, 255, 255, 18))
        d.text((540, CTA_Y + CTA_H / 2), cta, font=cf, fill=INK, anchor="mm")
        d.text((540, 1904), "AI explanations are checked against the verses · In distress? Tele-MANAS 14416",
               font=F("ui", 17), fill=(255, 255, 255, 115), anchor="mm")
        return Image.alpha_composite(img, lay)

    # ------------------------------------------------------------------ scene layer
    def set_queue(self, waiting: list[str], answered: list[str] | None = None) -> None:
        with self.lock:
            self.waiting = list(waiting)[:6]
            if answered is not None:
                self.answered = list(answered)[:6]
        self.build_scene(self.scene)

    def build_scene(self, item: dict) -> None:
        # translucent shapes are drawn on a clear layer and composited (drawing them straight onto the
        # opaque background would punch holes that turn white)
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(lay)
        F = self.F
        kind = item.get("type", "idle")
        dots = None
        if kind == "verse":
            v = item["verse"]
            idx, total = item.get("progress", {}).get("index", 0), item.get("progress", {}).get("total", 701)
            self.progress = (idx, total, v.get("chapter", 1))
            self.last_verse = v
        idx, total, chapter = self.progress
        # top-right pill: verse count
        pill = f"श्लोक {idx} / {total}" if idx else "श्लोक · / 701"
        pf = F("ui_bold", 24)
        pw = pf.getlength(pill) + 44
        rr(d, (W - 40 - pw, TOP_Y, pw, 46), 23, fill=(255, 255, 255, 20), outline=(255, 255, 255, 38), width=2)
        d.text((W - 40 - pw / 2, TOP_Y + 23), pill, font=pf, fill=INK, anchor="mm")
        # stats panel: chapter and progress through the Gita
        x, y, w, h = STATS
        d.text((x + 32, y + 30), "अध्याय · CHAPTER", font=F("ui_bold", 20), fill=(255, 255, 255, 140), anchor="la")
        big = F("ui_bold", 66)
        d.text((x + 32, y + 112), str(chapter), font=big, fill=INK, anchor="ls")
        d.text((x + 40 + big.getlength(str(chapter)), y + 112), "/ 18", font=F("ui_semibold", 32), fill=(255, 255, 255, 115), anchor="ls")
        bx = x + 300
        lv = self.last_verse or {}
        d.text((bx, y + 34), f"{lv.get('chapter_name_sanskrit') or 'भगवद्गीता'}  ·  {lv.get('chapter_name') or 'Bhagavad Gita'}",
               font=F("ui_semibold", 28), fill=(255, 255, 255, 215), anchor="la")
        bw = x + w - 32 - bx
        rr(d, (bx, y + 82, bw, 18), 9, fill=(255, 255, 255, 26))
        if total and idx:
            rr(d, (bx, y + 82, max(18, bw * idx / total), 18), 9, fill=GOLD)
        # centre stage
        sx, sy, sw, sh = STAGE
        pad = 44
        avail = sh - 2 * pad - 40          # the bottom 40 px are the speaking waveform's
        flow = None
        for step in range(13):
            f = 1.0 - step * 0.05
            flow = Flow(F, sx + pad, sw - 2 * pad, f)
            dots = self._stage(flow, item)
            if flow.h <= avail:
                break
        self.last_fit = flow.f
        y0 = sy + pad + max(0, (avail - flow.h) / 2)
        flow.draw(d, y0)
        if dots is not None:
            dots = (dots[0], y0 + dots[1])
        # question queue and recent answers
        for (bx_, by_, bw_, bh_), names, empty in ((NEXTQ, self.waiting, f"{self.trigger} लिखकर पूछें"),
                                                  (DONEQ, self.answered, "अभी कोई नहीं")):
            nf = F("ui_semibold", 27)
            if not names:
                d.text((bx_ + 28, by_ + 92), empty, font=F("ui", 25), fill=(255, 255, 255, 95), anchor="la")
            for i, n in enumerate(names[:6]):
                ry = by_ + 92 + i * 47
                d.ellipse((bx_ + 28, ry + 4, bx_ + 52, ry + 28), fill=GOLD if names is self.waiting and i == 0 else (255, 255, 255, 40))
                d.text((bx_ + 40, ry + 16), str(i + 1), font=F("ui_bold", 16), fill=(20, 16, 4) if names is self.waiting and i == 0 else INK, anchor="mm")
                line = ellipsize([n], nf, bw_ - 100, 1)[0]
                d.text((bx_ + 66, ry + 2), line, font=nf, fill=INK, anchor="la")
        # chapter strip: 18 dots, the current one lit
        x, y, w, h = STRIP
        for c in range(1, CHAPTERS + 1):
            cx_ = x + 190 + (c - 1) * 44
            col = GOLD if c == chapter else (242, 181, 68, 120) if c < chapter else (255, 255, 255, 38)
            r = 15 if c == chapter else 11
            d.ellipse((cx_ - r, y + h / 2 - r, cx_ + r, y + h / 2 + r), fill=col)
            if c == chapter:
                d.text((cx_, y + h / 2), str(c), font=F("ui_bold", 16), fill=(20, 16, 4), anchor="mm")
        rgb = Image.alpha_composite(self.static, lay).convert("RGB")
        with self.lock:
            self.scene = item
            self.scene_rgb = rgb
            self._scaled = {}
            self.dots_at = dots

    def _stage(self, fl: Flow, item: dict):
        kind = item.get("type", "idle")
        if kind == "verse":
            v = item["verse"]
            fl.row(f"अध्याय {v['chapter']} · श्लोक {v['verse']}",
                   f"{v.get('speaker_hindi') or SP_HI.get(v['speaker'], v['speaker'])}, {v.get('listener_hindi') or SP_HI.get(v['addressed_to'], v['addressed_to'])} से",
                   "ui_semibold", 30, GOLD, MUTED)
            fl.gap(18)
            fl.text(v["sanskrit"].replace("।।", "॥"), "sanskrit", 60, (250, 243, 222), lh=1.5)
            fl.gap(10)
            fl.text(v.get("transliteration", ""), "sanskrit_italic", 28, MUTED, lh=1.45)
            fl.gap(26)
            if v.get("translation"):
                fl.card(lambda c: (c.text(v["translation"], "ui", 33, INK, align="left", lh=1.42),
                                   c.gap(6), c.text(f"Translation · {v.get('translation_source', '')}", "ui", 20, DIM, align="left")),
                        fill=(255, 255, 255, 16), bar=GOLD)
            else:
                fl.text("अनुवाद की जाँच चल रही है · translation under review", "ui", 26, DIM)
            return None
        if kind == "asking":
            fl.text("प्रश्न · QUESTION", "ui_bold", 26, GOLD)
            fl.gap(10)
            fl.text(f"{item.get('name', 'Viewer')} पूछते हैं", "ui_semibold", 40, MUTED)
            fl.gap(22)
            fl.text(item.get("question", ""), "ui_semibold", 54, INK, lh=1.35, max_lines=6)
            fl.gap(46)
            fl.text("गीता में उत्तर खोज रहे हैं · Finding the verses", "ui", 30, MUTED)
            fl.gap(30)
            return (fl.x + fl.w / 2, fl.h)
        if kind == "answer":
            a = item.get("answer", {})
            lang = a.get("lang", "hi")
            fl.card(lambda c: (c.text(f"{item.get('name', 'Viewer')} पूछते हैं", "ui_semibold", 24, TEAL, align="left"),
                               c.text(item.get("question", ""), "ui_semibold", 34, INK, align="left", max_lines=3)),
                    fill=(92, 196, 203, 30), outline=(92, 196, 203, 70), pad=20)
            fl.gap(18)
            if a.get("kind") in ("crisis", "harm_others"):
                fl.card(lambda c: (c.text(a.get("opening", ""), "ui", 32, INK, align="left"), c.gap(10),
                                   c.text("Tele-MANAS 14416  ·  KIRAN 1800-599-0019  ·  112", "ui_bold", 34, (255, 170, 180), align="left")),
                        fill=(242, 122, 140, 40), outline=(242, 122, 140, 160))
                return None
            fl.text(a.get("opening", ""), "ui", 32, INK, lh=1.38)
            for c_ in a.get("verses", [])[:2]:
                fl.gap(16)
                head_l = f"{c_.get('id', '')} · {'Chapter' if lang == 'en' else 'अध्याय'} {c_.get('chapter', '')}"
                head_r = (f"{c_.get('speaker', '')} to {c_.get('addressed_to', '')}" if lang == "en" else
                          f"{SP_HI.get(c_.get('speaker', ''), c_.get('speaker', ''))}, {SP_HI.get(c_.get('addressed_to', ''), c_.get('addressed_to', ''))} से")

                def card(cf, c_=c_, head_l=head_l, head_r=head_r):
                    cf.row(head_l, head_r, "ui_semibold", 22, GOLD, MUTED)
                    cf.text(c_.get("sanskrit", "").replace("।।", "॥"), "sanskrit", 32, (250, 243, 222), lh=1.45)
                    cf.gap(6)
                    cf.text(c_.get("meaning") or c_.get("translation", ""), "ui", 28, INK, align="left", lh=1.38)
                    if c_.get("application"):
                        cf.gap(8)
                        cf.card(lambda z: z.text(c_["application"], "ui", 27, INK, align="left", lh=1.36),
                                fill=(92, 196, 203, 32), outline=None, pad=14, radius=14)
                fl.card(card)
            if a.get("closing"):
                fl.gap(16)
                fl.text(a["closing"], "ui", 29, (236, 228, 205), lh=1.38)
            return None
        # idle: before the first verse
        fl.text("ॐ", "sanskrit", 120, GOLD)
        fl.gap(10)
        fl.text("भगवद्गीता का पाठ शुरू हो रहा है · The recitation is starting", "ui", 32, MUTED)
        return None

    # ------------------------------------------------------------------ dynamic layer
    def frame(self, t: float, level: float = 0.0, scale: float = 1.0) -> bytes:
        """One RGB frame at the given scale."""
        with self.lock:
            base = self.scene_rgb
            dots = self.dots_at
            if scale != 1.0:
                if scale not in self._scaled:
                    self._scaled[scale] = base.resize((even(W * scale), even(H * scale)), Image.LANCZOS)
                base = self._scaled[scale]
        img = base.copy()
        d = ImageDraw.Draw(img)
        s = scale
        # pulsing LIVE dot
        a = 0.55 + 0.45 * math.sin(t * 4)
        dot = tuple(int(RED[i] + (255 - RED[i]) * a) for i in range(3))
        d.ellipse(((67 - 8) * s, (TOP_Y + 23 - 8) * s, (67 + 8) * s, (TOP_Y + 23 + 8) * s), fill=dot)
        # call-to-action border cycling through hues
        r, g, b = colorsys.hsv_to_rgb((t * 25 % 360) / 360, 0.65, 1.0)
        x, y, w, h = self.cta_box
        d.rounded_rectangle((x * s, y * s, (x + w) * s, (y + h) * s), radius=29 * s, outline=(int(r * 255), int(g * 255), int(b * 255)), width=max(1, round(2 * s)))
        # speaking waveform at the bottom of the stage
        sx, sy, sw, sh = STAGE
        cx, cy = sx + sw / 2, sy + sh - 26
        for i in range(-6, 7):
            amp = level * (0.55 + 0.45 * math.sin(t * 9 + i * 1.7)) if level > 0.004 else 0.0
            bh = 4 + min(1.0, amp * 7) * 30
            bx = cx + i * 13
            d.rounded_rectangle(((bx - 3) * s, (cy - bh / 2) * s, (bx + 3) * s, (cy + bh / 2) * s), radius=3 * s,
                                fill=GOLD if amp else (90, 96, 130))
        # "finding the verses" dots while a question is being answered
        if dots:
            for i in range(3):
                k = 0.5 + 0.5 * math.sin(t * 5 - i * 0.9)
                col = tuple(int(30 + (GOLD[j] - 30) * k) for j in range(3))
                px = dots[0] + (i - 1) * 34
                d.ellipse(((px - 9) * s, (dots[1] - 9) * s, (px + 9) * s, (dots[1] + 9) * s), fill=col)
        return img.tobytes()

    def jpeg(self, quality: int = 80, t: float = 0.0) -> bytes:
        import io
        img = Image.frombytes("RGB", (W, H), self.frame(t))
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality)
        return buf.getvalue()


def even(v: float) -> int:
    return int(round(v / 2) * 2)
