#!/usr/bin/env python3
"""Generate the animated chronograph GIF used in the ChronoPulse README.

Requires Pillow (pip install pillow). Run: python3 tools/generate_demo.py
"""

import math
import os

from PIL import Image, ImageDraw, ImageFont

SIZE = 480
CENTER = SIZE // 2
FRAMES = 16
AMBER = (245, 158, 11)
AMBER_LIGHT = (253, 230, 138)
TEAL = (20, 184, 166)
EMERALD = (16, 185, 129)
MUTED = (141, 154, 177)
BG = (7, 9, 14)

FONT_DIR = "/usr/share/fonts/truetype/dejavu"


def font(name, size):
    path = os.path.join(FONT_DIR, name)
    try:
        return ImageFont.truetype(path, size)
    except OSError:
        return ImageFont.load_default()


MONO_BIG = font("DejaVuSansMono-Bold.ttf", 52)
MONO_SMALL = font("DejaVuSansMono.ttf", 15)
SANS_BOLD = font("DejaVuSans-Bold.ttf", 15)
SANS_SMALL = font("DejaVuSans.ttf", 12)


def point(radius, degrees):
    angle = math.radians(degrees - 90)
    return CENTER + radius * math.cos(angle), CENTER + radius * math.sin(angle)


def frame(index):
    img = Image.new("RGB", (SIZE, SIZE), BG)
    d = ImageDraw.Draw(img)

    # subtle dot matrix
    for x in range(12, SIZE, 22):
        for y in range(12, SIZE, 22):
            d.ellipse((x, y, x + 1, y + 1), fill=(23, 31, 47))

    # ambient glow rings
    for radius, color in ((205, (28, 24, 12)), (190, (18, 35, 35))):
        d.ellipse((CENTER - radius, CENTER - radius, CENTER + radius, CENTER + radius),
                  outline=color, width=2)

    # 60 tick marks
    for i in range(60):
        major = i % 5 == 0
        inner, outer = (178, 192) if major else (185, 192)
        color = (170, 110, 25) if major else (52, 63, 82)
        d.line((point(inner, i * 6), point(outer, i * 6)), fill=color, width=2 if major else 1)

    # seconds progress arc
    span = (index + 1) / FRAMES * 360
    d.arc((CENTER - 172, CENTER - 172, CENTER + 172, CENTER + 172),
          start=-90, end=-90 + span, fill=AMBER, width=9)
    d.arc((CENTER - 148, CENTER - 148, CENTER + 148, CENTER + 148),
          start=-90, end=-90 + span * 0.55, fill=TEAL, width=4)

    # rotating chronograph needle
    needle_angle = index * (360 / FRAMES)
    d.line((point(-24, needle_angle + 180), point(160, needle_angle)),
           fill=AMBER_LIGHT, width=4)
    d.ellipse((point(160, needle_angle)[0] - 5, point(160, needle_angle)[1] - 5,
               point(160, needle_angle)[0] + 5, point(160, needle_angle)[1] + 5), fill=AMBER_LIGHT)

    # center dial
    d.ellipse((CENTER - 120, CENTER - 120, CENTER + 120, CENTER + 120),
              fill=(11, 16, 26), outline=(80, 62, 25), width=2)

    def center_text(text, y, fnt, color):
        box = d.textbbox((0, 0), text, font=fnt)
        d.text((CENTER - (box[2] - box[0]) / 2, y), text, font=fnt, fill=color)

    center_text("CHRONOPULSE", CENTER - 78, SANS_BOLD, MUTED)
    center_text(f"00:00:{index:02d}", CENTER - 38, MONO_BIG, (255, 255, 255))
    center_text("LIVE SESSION", CENTER + 26, SANS_BOLD, EMERALD)
    center_text("PRECISION WORKHORSE", CENTER + 74, SANS_SMALL, MUTED)

    center_text("TRACK EVERY MINUTE · BILL EVERY HOUR", SIZE - 26, SANS_SMALL, AMBER)
    return img


def main():
    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "static", "assets")
    os.makedirs(out_dir, exist_ok=True)
    frames = [frame(i) for i in range(FRAMES)]
    target = os.path.join(out_dir, "chronopulse-demo.gif")
    frames[0].save(target, save_all=True, append_images=frames[1:],
                   duration=150, loop=0, optimize=True)
    print("Wrote", target, "(" + str(os.path.getsize(target) // 1024) + " KB)")


if __name__ == "__main__":
    main()
