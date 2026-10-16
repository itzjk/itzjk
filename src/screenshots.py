"""Screenshots of the card rendered in Chrome, to review it before shipping (not committed: screenshots/).

    python3 src/screenshots.py

- desktop-*.png / mobile-*.png: the SVG the README <picture> picks for that width and theme (checked with
  picked()), at 1280 px and at 375 px (343 px column, GitHub's on mobile), paused with variant A typed.
- static-*.png: the SVG without its <animate> elements, which is what a viewer without SMIL gets: A must be whole.
- reduced-motion-*.png: Chrome with prefers-reduced-motion: A whole, no cursor, no B/C.
- cycle.gif and cycle-strip.png: the Kernel/Hobbies cycle A -> B -> C, frame by frame (setCurrentTime).
"""
import os, re, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import generate  # noqa: E402

CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
OUT = os.path.join(ROOT, "screenshots")
ASSETS = os.path.join(ROOT, "assets")
RAW = "https://raw.githubusercontent.com/itzjk/itzjk/main/assets/"
DARK = ("--force-dark-mode", "--blink-settings=preferredColorScheme=0")
LIGHT = ("--blink-settings=preferredColorScheme=1",)


def chrome(html, png, width, height, extra=(), budget=2500):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, dir=OUT) as fh:
        fh.write(html)
    try:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={width},{height}",
                        f"--virtual-time-budget={budget}", f"--screenshot={png}", *extra, "file://" + fh.name],
                       check=True, capture_output=True, timeout=60)
    finally:
        os.unlink(fh.name)


def page(bg, body, column):
    return f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>body{{margin:0;background:{bg};font:14px -apple-system,sans-serif}}
.readme{{width:{column}px;margin:24px 16px}}img{{max-width:100%;height:auto;display:block}}</style>
<div class="readme">{body}</div>"""


def readme_picture():
    md = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    return re.search(r"<picture>.*?</picture>", md, re.S).group(0).replace(RAW, "file://" + ASSETS + "/")


def picked(width, scheme):
    """The SVG the README <picture> picks in Chrome at that width and theme."""
    html = page("#fff", readme_picture(), min(width - 32, 980)) + \
        '<script>addEventListener("load",()=>{document.body.dataset.src=document.querySelector("img").currentSrc})</script>'
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, dir=OUT) as fh:
        fh.write(html)
    try:
        dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", f"--window-size={width},800", *scheme,
                              "--virtual-time-budget=1000", "--dump-dom", "file://" + fh.name],
                             check=True, capture_output=True, text=True, timeout=60).stdout
    finally:
        os.unlink(fh.name)
    return os.path.basename(re.search(r'data-src="([^"]+)"', dom).group(1))


def without_animation(svg):
    return re.sub(r"<animate\b[^>]*/>", "", svg)


def at_time(svg, t, bg="#0d1117", column=None):
    """HTML with the SVG inline, paused at second t of the SMIL cycle (column: px, scaled)."""
    box = f"width:{column}px;margin:24px 16px" if column else "margin:0"
    return (f'<!doctype html><meta charset="utf-8"><style>body{{margin:0;background:{bg}}}'
            f'div{{{box}}}svg{{display:block;{"width:100%;height:auto" if column else ""}}}</style><div>{svg}</div>'
            f'<script>const s=document.querySelector("svg");s.pauseAnimations();s.setCurrentTime({t});</script>')


def a_typed():
    """Second of the cycle when variant A is fully typed (before it starts erasing)."""
    p = generate.read_profile()
    longest = max(sum(len(l) for l in generate.wrap(v[0], 40)) for v in p.values() if len(v) > 1)
    return longest * generate.TYPE + generate.HOLD * 0.5


def cycle_length(svg):
    return float(re.search(r'<animate [^>]*dur="([\d.]+)s"', svg).group(1))


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, scheme, bg in (("dark", DARK, "#0d1117"), ("light", LIGHT, "#ffffff")):
        for view, (width, height, column) in (("desktop", (1280, 640, 980)), ("mobile", (375, 1000, 343))):
            chosen = picked(width, scheme)
            print(f"{view} {name}: <picture> picks {chosen}")
            svg = open(f"{ASSETS}/{chosen}", encoding="utf-8").read()
            chrome(at_time(svg, a_typed(), bg, column), f"{OUT}/{view}-{name}.png", width, height, budget=50)
        svg = open(f"{ASSETS}/{name}.svg", encoding="utf-8").read()
        static = os.path.join(OUT, f"_static-{name}.svg")
        open(static, "w", encoding="utf-8").write(without_animation(svg))
        chrome(page(bg, f'<img src="file://{static}">', 980), f"{OUT}/static-{name}.png", 1280, 640, scheme, budget=100)
        os.unlink(static)
        chrome(page(bg, f'<img src="file://{ASSETS}/{name}.svg">', 980), f"{OUT}/reduced-motion-{name}.png",
               1280, 640, (*scheme, "--force-prefers-reduced-motion"), budget=1500)
    svg = open(f"{ASSETS}/dark.svg", encoding="utf-8").read()
    total = cycle_length(svg)
    W = int(re.search(r'width="(\d+)"', svg).group(1))
    H = int(re.search(r'height="(\d+)"', svg).group(1))
    tmp = tempfile.mkdtemp(dir=OUT)
    n = int(total / 0.25)
    for i in range(n):
        chrome(at_time(svg, i * 0.25), f"{tmp}/f{i:04d}.png", W, H, budget=50)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "4", "-i", f"{tmp}/f%04d.png", "-vf",
                    "scale=760:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=96[p];[b][p]paletteuse",
                    f"{OUT}/cycle.gif"], check=True)
    idx = [int(n * k / 8) for k in range(8)]
    inputs = sum((["-i", f"{tmp}/f{i:04d}.png"] for i in idx), [])
    x0 = W - 640
    crop = "".join(f"[{k}:v]crop=632:{H}:{x0}:0[c{k}];" for k in range(8))
    grid = "".join(f"[c{k}]" for k in range(8)) + \
        "xstack=inputs=8:layout=0_0|w0_0|w0+w1_0|w0+w1+w2_0|0_h0|w0_h0|w0+w1_h0|w0+w1+w2_h0,scale=1800:-1"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", crop + grid, f"{OUT}/cycle-strip.png"],
                   check=True)
    shutil.rmtree(tmp)
    print(f"cycle {total:.1f} s, {n} frames -> {OUT}")


if __name__ == "__main__":
    main()
