"""Logo for the 'Two Hours to First Call' BUIDL.

A 12-hour dial with two hours burned. The arc is the two hours spent before the
first call succeeded; the single green tick is the call landing. Deliberately
distinct from sama's verdict grid, since KeeperHub asked for the two entries to
be told apart.
"""
import math
from PIL import Image, ImageDraw, ImageFont

S, SS = 480, 4                      # supersample for clean curves
W = S * SS
img = Image.new("RGB", (W, W), "#0d1117")
d = ImageDraw.Draw(img)

cx = cy = W // 2
r = int(W * 0.34)
th = int(W * 0.075)

box = [cx - r, cy - r, cx + r, cy + r]
d.arc(box, 0, 360, fill="#20262e", width=th)          # the remaining ten hours
d.arc(box, -90, -90 + 60, fill="#d98026", width=th)   # two hours of twelve

# The call landing: a green tick at the end of the burned arc.
a = math.radians(-90 + 60)
tx, ty = cx + r * math.cos(a), cy + r * math.sin(a)
rr = int(W * 0.048)
d.ellipse([tx - rr, ty - rr, tx + rr, ty + rr], fill="#0d1117")
rr = int(W * 0.032)
d.ellipse([tx - rr, ty - rr, tx + rr, ty + rr], fill="#3fb950")


def font(px):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(p, px)
        except OSError:
            continue
    return ImageFont.load_default()


def centered(text, f, y, fill):
    l, t, rt, b = d.textbbox((0, 0), text, font=f)
    d.text((cx - (rt - l) / 2 - l, y - (b - t) / 2 - t), text, font=f, fill=fill)


centered("2h", font(int(W * 0.20)), cy - int(W * 0.035), "#e6edf3")
centered("TO FIRST CALL", font(int(W * 0.052)), cy + int(W * 0.085), "#7d8590")

img.resize((S, S), Image.LANCZOS).save("site/onboarding-logo.png")
print("wrote site/onboarding-logo.png")
