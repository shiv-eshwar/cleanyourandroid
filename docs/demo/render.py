"""Render annotated stills from capture.py. Usage: render.py ARTIFACT_DIR OUTPUT_DIR."""

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 1200, 552
PAPER, INK, TEAL = "#f7f7f1", "#162d2a", "#096653"
CONSOLE, WHITE, MUTED = "#172a29", "#fafcf9", "#b3c6be"
STEPS = [
    ("preview", "Preview the light plan", ["cleanyourandroid plan --light", "  --out plan.json"]),
    ("applied", "Apply the reviewed plan", ["cleanyourandroid apply plan.json", "  --approve \"$digest\" --journal journal.json"]),
    ("restored", "Restore the original settings", ["cleanyourandroid restore journal.json"]),
]


def font(kind, size):
    names = {
        "sans": ("Arial.ttf", "DejaVuSans.ttf"),
        "bold": ("Arial Bold.ttf", "DejaVuSans-Bold.ttf"),
        "mono": ("Menlo.ttc", "DejaVuSansMono.ttf"),
    }
    for name in names[kind]:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    raise SystemExit("Install DejaVu Sans and DejaVu Sans Mono to render the demo.")


def frame(folder, entry, index):
    key, title, command = STEPS[index]
    if entry["stage"] != key:
        raise ValueError("Unexpected capture order")
    canvas = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    d = ImageDraw.Draw(canvas)

    def text(x, y, value, kind="sans", size=22, color=INK):
        d.text((x, y), value, font=font(kind, size), fill=color, anchor="lt")

    text(36, 24, "CleanYourAndroid", "bold", 23)
    d.line((256, 26, 256, 46), fill="#b9c4bc", width=1)
    text(274, 26, "Android 16 emulator", size=20, color="#4a615a")
    text(1082, 26, f"0{index+1} / 03", "mono", 18, TEAL)
    text(34, 72, title, "bold", 45)

    # The transcript is typeset; the Android preference rows are screencap pixels.
    d.rounded_rectangle((32, 146, 646, 454), radius=13, fill=CONSOLE)
    text(53, 169, "COMMAND", "bold", 16, MUTED)
    for i, line in enumerate(command):
        prefix = "$ " if i == 0 else "  "
        suffix = " \\" if i < len(command) - 1 else ""
        text(53, 210 + 32*i, prefix + line + suffix, "mono", 19, WHITE)
    d.line((53, 284, 624, 284), fill="#52635f", width=1)
    text(53, 304, "REQUESTED SETTING" if not index else "JOURNAL ENTRY", "bold", 16, MUTED)
    text(497, 304, "VALUE" if not index else "STATE", "bold", 16, MUTED)
    for i, op in enumerate(entry["operations"]):
        text(53, 341 + 33*i, op["target"], "mono", 21, WHITE)
        text(497, 341 + 33*i, op["value"] if not index else op["state"], "mono", 21, "#a6ecc6")

    text(676, 165, "ANDROID SETTINGS", "bold", 16, TEAL)
    with Image.open(folder / f"{key}.png") as src:
        x0, y0, x1, y1 = entry["crop"]
        native_width = round((y1 - y0) * 494 / 251)
        crop = src.convert("RGB").crop((x0, y0, min(x1, x0 + native_width), y1))
        crop.thumbnail((494, 251), Image.Resampling.LANCZOS)
        x, y = 676, 200
        d.rounded_rectangle((x-1, y-1, x+crop.width, y+crop.height), radius=4, fill="#d4dcd5")
        canvas.paste(crop, (x, y))

    for i, name in enumerate(("Preview", "Apply", "Restore")):
        x = 34 + 387*i
        color = TEAL if i == index else "#c9d1c9"
        d.rectangle((x, 484, x + 362, 488), fill=color)
        text(x, 503, f"0{i+1}   {name}", "bold" if i == index else "sans", 21,
             TEAL if i == index else "#4a615a")
    return canvas


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    session = json.loads((args.artifact / "session.json").read_bytes())
    if len(session) != len(STEPS):
        raise ValueError("Incomplete capture")
    frames = [frame(args.artifact, item, i) for i, item in enumerate(session)]
    args.output.mkdir(parents=True, exist_ok=True)
    frames[1].save(args.output / "light-plan.png", optimize=True)
    frames[0].save(args.output / "light-plan.gif", save_all=True, append_images=frames[1:],
                   duration=[4200, 4400, 4400], loop=0, optimize=True, disposal=1)


if __name__ == "__main__":
    main()
