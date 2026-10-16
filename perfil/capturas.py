"""Capturas de la ficha renderizada en Chrome, para revisarla antes de darla por buena (no van al repo).

    python3 perfil/capturas.py            # -> capturas/: escritorio y movil (claro y oscuro), estatico,
                                           #    reduced-motion, tira del ciclo y GIF del ciclo

- escritorio-*.png / movil-*.png: el SVG que elige el <picture> del README para ese ancho y tema (lo comprueba
  eleccion()), a 1280 y a 375 px (columna de 343 px, la de GitHub en movil), parado con la variante A tecleada.
- estatico-*.png: el SVG sin sus <animate>, que es lo que ve quien no reproduce SMIL: tiene que salir la A entera.
- reduced-motion-*.png: Chrome con prefers-reduced-motion: la A entera, sin cursor ni B/C.
- ciclo.gif y ciclo-tira.png: el ciclo A -> B -> C de Kernel y Hobbies, fotograma a fotograma (setCurrentTime).
"""
import os, re, shutil, subprocess, sys, tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "perfil"))
CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SALIDA = os.path.join(RAIZ, "capturas")
ASSETS = os.path.join(RAIZ, "assets")


def chrome(html, png, ancho, alto, extra=(), tiempo=2500):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, dir=SALIDA) as fh:
        fh.write(html)
    try:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--window-size={ancho},{alto}",
                        f"--virtual-time-budget={tiempo}", f"--screenshot={png}", *extra, "file://" + fh.name],
                       check=True, capture_output=True, timeout=60)
    finally:
        os.unlink(fh.name)


def pagina(fondo, cuerpo, ancho_max):
    return f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<style>body{{margin:0;background:{fondo};font:14px -apple-system,sans-serif}}
.readme{{max-width:{ancho_max}px;margin:24px auto;padding:0 16px}}img{{max-width:100%;height:auto;display:block}}</style>
<div class="readme">{cuerpo}</div>"""


def readme_html():
    """El <picture> del README, apuntando a los SVG locales."""
    md = open(os.path.join(RAIZ, "README.md"), encoding="utf-8").read()
    pic = re.search(r"<picture>.*?</picture>", md, re.S).group(0)
    return pic.replace("https://raw.githubusercontent.com/itzjk/itzjk/main/assets/", "file://" + ASSETS + "/")


def sin_animar(svg):
    return re.sub(r"<animate\b[^>]*/>", "", svg)


def en_el_tiempo(svg, t, fondo="#0d1117", ancho=None):
    """HTML con el SVG en linea parado en el segundo t del ciclo SMIL (ancho: columna en px, escalado)."""
    caja = f"width:{ancho}px;margin:24px 16px" if ancho else "margin:0"
    return (f'<!doctype html><meta charset="utf-8"><style>body{{margin:0;background:{fondo}}}'
            f'div{{{caja}}}svg{{display:block;{"width:100%;height:auto" if ancho else ""}}}</style><div>{svg}</div>'
            f'<script>const s=document.querySelector("svg");s.pauseAnimations();s.setCurrentTime({t});</script>')


def eleccion(ancho, esquema):
    """El SVG que el <picture> del README elige en Chrome con ese ancho y ese tema."""
    html = pagina("#fff", readme_html(), 1012) + \
        '<script>addEventListener("load",()=>{document.body.dataset.src=document.querySelector("img").currentSrc})</script>'
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, dir=SALIDA) as fh:
        fh.write(html)
    try:
        dom = subprocess.run([CHROME, "--headless=new", "--disable-gpu", f"--window-size={ancho},800", *esquema,
                              "--virtual-time-budget=1000", "--dump-dom", "file://" + fh.name],
                             check=True, capture_output=True, text=True, timeout=60).stdout
    finally:
        os.unlink(fh.name)
    return os.path.basename(re.search(r'data-src="([^"]+)"', dom).group(1))


def a_tecleada(svg):
    """Segundo del ciclo en que la variante A ya esta escrita entera (justo antes de que empiece a borrar)."""
    sys.path.insert(0, os.path.join(RAIZ, "perfil"))
    import generar
    perfil = generar.leer_perfil()
    largo = max(sum(len(l) for l in generar.partir(v[0], 40)) for v in perfil.values() if len(v) > 1)
    return largo * generar.TECLA + generar.QUIETO * 0.5


def duracion(svg):
    m = re.search(r'<animate [^>]*dur="([\d.]+)s"', svg)
    return float(m.group(1))


def main():
    os.makedirs(SALIDA, exist_ok=True)
    oscuro = ("--force-dark-mode", "--blink-settings=preferredColorScheme=0")
    claro = ("--blink-settings=preferredColorScheme=1",)
    # momento del ciclo con la A ya escrita: la A dura lo que tarda en teclearse mas la pausa
    for nombre, esquema, fondo in (("oscuro", oscuro, "#0d1117"), ("claro", claro, "#ffffff")):
        for vista, (ancho, alto, columna) in (("escritorio", (1280, 640, 980)), ("movil", (375, 1000, 343))):
            elegido = eleccion(ancho, esquema)
            print(f"{vista} {nombre}: el <picture> elige {elegido}")
            svg_v = open(f"{ASSETS}/{elegido}", encoding="utf-8").read()
            chrome(en_el_tiempo(svg_v, a_tecleada(svg_v), fondo, columna), f"{SALIDA}/{vista}-{nombre}.png", ancho, alto, tiempo=50)
        svg = open(f"{ASSETS}/{nombre}.svg", encoding="utf-8").read()
        est = os.path.join(SALIDA, f"_estatico-{nombre}.svg")
        open(est, "w", encoding="utf-8").write(sin_animar(svg))
        chrome(pagina(fondo, f'<img src="file://{est}">', 1012), f"{SALIDA}/estatico-{nombre}.png", 1280, 600, esquema, tiempo=100)
        os.unlink(est)
        chrome(pagina(fondo, f'<img src="file://{ASSETS}/{nombre}.svg">', 1012), f"{SALIDA}/reduced-motion-{nombre}.png",
               1280, 600, (*esquema, "--force-prefers-reduced-motion"), tiempo=1500)
    # ciclo: un fotograma cada 0,25 s del SVG ancho oscuro
    svg = open(f"{ASSETS}/oscuro.svg", encoding="utf-8").read()
    total = duracion(svg)
    tmp = tempfile.mkdtemp(dir=SALIDA)
    n = int(total / 0.25)
    for i in range(n):
        chrome(en_el_tiempo(svg, i * 0.25), f"{tmp}/f{i:04d}.png", 1012, 560, tiempo=50)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "4", "-i", f"{tmp}/f%04d.png", "-vf",
                    "scale=760:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=64[p];[b][p]paletteuse",
                    f"{SALIDA}/ciclo.gif"], check=True)
    # tira: 8 momentos repartidos por el ciclo, recortados a la ficha
    idx = [int(n * k / 8) for k in range(8)]
    entradas = sum((["-i", f"{tmp}/f{i:04d}.png"] for i in idx), [])
    filtro = "".join(f"[{k}:v]crop=600:500:360:0[c{k}];" for k in range(8)) + "".join(f"[c{k}]" for k in range(8)) + \
        "xstack=inputs=8:layout=0_0|w0_0|w0+w1_0|w0+w1+w2_0|0_h0|w0_h0|w0+w1_h0|w0+w1+w2_h0,scale=1600:-1"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *entradas, "-filter_complex", filtro, f"{SALIDA}/ciclo-tira.png"],
                   check=True)
    shutil.rmtree(tmp)
    print("\n".join(sorted(os.path.join(SALIDA, f) for f in os.listdir(SALIDA))))
    print(f"ciclo {total:.1f} s, {n} fotogramas")


if __name__ == "__main__":
    main()
