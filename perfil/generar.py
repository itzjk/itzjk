"""Genera la ficha del perfil (estilo neofetch) en cuatro SVG: claro y oscuro, ancho y movil.

Los numeros salen de la API de GitHub (GraphQL, solo datos publicos). Los textos fijos (OS, Host, Kernel, IDE,
Languages.Real, Hobbies) estan en perfil.json, en la raiz: se cambian ahi, una linea cada uno, sin tocar codigo.
De la API solo se leen los campos de CAMPOS_API: nunca nombre, correo, ubicacion, biografia ni foto.

    GITHUB_TOKEN=... python3 perfil/generar.py            # en el Action, con el token del propio repo
    python3 perfil/generar.py --datos fixture.json        # sin red: los datos ya leidos (pruebas)

Lineas de codigo +/-: se suman las additions/deletions de los commits del usuario en la rama principal de cada
repo publico suyo. Es lo caro, asi que va en cache por repo (cache/repos.json): si el ultimo commit de la rama
no ha cambiado, no se vuelve a pedir. Este repo (itzjk/itzjk) no cuenta: sus commits los hace el Action cada dia
y la ficha se inflaria sola.
"""
import argparse, datetime, json, os, sys, urllib.request
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fantasma import dibujar

LOGIN = "itzjk"
RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(RAIZ, "cache", "repos.json")
API = "https://api.github.com/graphql"

PERFIL = os.path.join(RAIZ, "perfil.json")
TEXTOS = ("OS", "Host", "Kernel", "IDE", "Languages.Real", "Hobbies")   # los que tiene que traer perfil.json
CONTACTO = [("GitHub", "github.com/itzjk"), ("X", "x.com/Izkszk")]
NO_PROGRAMACION = {"HTML", "CSS", "SCSS", "Less", "Jupyter Notebook", "Dockerfile", "Makefile"}
MAX_LENGUAJES = 5

CAMPOS_API = """
  id createdAt
  repositoriesContributedTo(includeUserRepositories: true, first: 1,
      contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, PULL_REQUEST_REVIEW, REPOSITORY]) { totalCount }
  repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100) {
    totalCount
    nodes { name stargazerCount
      languages(first: 20) { edges { size node { name } } }
      defaultBranchRef { target { ... on Commit { oid } } } }
  }
"""
Q_USUARIO = "query($login: String!) { user(login: $login) { %s } }" % CAMPOS_API
Q_HISTORIA = """query($owner: String!, $name: String!, $autor: ID!, $tras: String) {
  repository(owner: $owner, name: $name) { defaultBranchRef { target { ... on Commit {
    history(first: 100, after: $tras, author: {id: $autor}) {
      totalCount pageInfo { hasNextPage endCursor } nodes { additions deletions } } } } } } }"""


# --- API -------------------------------------------------------------------------------------------------------
def graphql(token, consulta, **variables):
    req = urllib.request.Request(API, json.dumps({"query": consulta, "variables": variables}).encode(),
                                 {"Authorization": f"bearer {token}", "Content-Type": "application/json",
                                  "User-Agent": "itzjk-perfil"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)
    if res.get("errors"):
        raise RuntimeError(f"GraphQL: {res['errors']}")
    return res["data"]


def historia(token, repo, autor):
    """(commits, additions, deletions) del autor en la rama principal de `repo`."""
    commits = add = dele = 0
    tras = None
    while True:
        d = graphql(token, Q_HISTORIA, owner=LOGIN, name=repo, autor=autor, tras=tras)
        h = d["repository"]["defaultBranchRef"]["target"]["history"]
        commits = h["totalCount"]
        for n in h["nodes"]:
            add += n["additions"]; dele += n["deletions"]
        if not h["pageInfo"]["hasNextPage"]:
            return commits, add, dele
        tras = h["pageInfo"]["endCursor"]


def leer_api(token, cache):
    """Datos crudos: el usuario y, por repo, su historia (de la cache si la rama no ha cambiado)."""
    usuario = graphql(token, Q_USUARIO, login=LOGIN)["user"]
    repos = {}
    for r in usuario["repositories"]["nodes"]:
        if r["name"] == LOGIN:              # el repo de esta ficha: commits automaticos, no cuentan
            continue
        ref = r["defaultBranchRef"]
        oid = ref["target"]["oid"] if ref else None
        viejo = cache.get(r["name"])
        if oid is None:
            repos[r["name"]] = dict(oid=None, commits=0, additions=0, deletions=0)
        elif viejo and viejo["oid"] == oid:
            repos[r["name"]] = viejo
        else:
            c, a, d = historia(token, r["name"], usuario["id"])
            repos[r["name"]] = dict(oid=oid, commits=c, additions=a, deletions=d)
    return {"user": usuario, "historias": repos}


# --- datos para la ficha ---------------------------------------------------------------------------------------
def uptime(creada, hoy):
    """'1 año, 10 meses, 23 días' entre dos fechas (date). Los meses se cuentan de fecha a fecha (del 31 de enero
    al 28 de febrero es un mes) y los dias son lo que queda desde ahi."""
    meses = (hoy.year - creada.year) * 12 + hoy.month - creada.month - (hoy.day < creada.day)
    a, m = divmod(creada.month - 1 + meses, 12)
    a += creada.year
    ultimo = (datetime.date(a + (m == 11), (m + 1) % 12 + 1, 1) - datetime.timedelta(days=1)).day
    dias = (hoy - datetime.date(a, m + 1, min(creada.day, ultimo))).days
    parte = lambda n, uno, varios: f"{n} {uno if n == 1 else varios}"
    return ", ".join([parte(meses // 12, "año", "años"), parte(meses % 12, "mes", "meses"), parte(dias, "día", "días")])


def resumen(crudo, hoy):
    """Todo lo que la ficha enseña, sacado solo de los campos leidos de la API."""
    u = crudo["user"]
    nodos = u["repositories"]["nodes"]
    bytes_ = {}
    for r in nodos:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            if n not in NO_PROGRAMACION:
                bytes_[n] = bytes_.get(n, 0) + e["size"]
    lenguajes = [n for n, _ in sorted(bytes_.items(), key=lambda kv: (-kv[1], kv[0]))][:MAX_LENGUAJES]
    h = crudo["historias"].values()
    creada = datetime.date.fromisoformat(u["createdAt"][:10])
    return dict(uptime=uptime(creada, hoy), lenguajes=lenguajes,
                repos=u["repositories"]["totalCount"], contribuidos=u["repositoriesContributedTo"]["totalCount"],
                estrellas=sum(r["stargazerCount"] for r in nodos),
                commits=sum(x["commits"] for x in h), suma=sum(x["additions"] for x in h),
                resta=sum(x["deletions"] for x in h))


# --- perfil.json ------------------------------------------------------------------------------------------------
def leer_perfil(ruta=PERFIL):
    """Textos fijos de la ficha: {clave: [variantes]}. Una cadena es una lista de una. Las claves con varias
    variantes rotan tecleando y borrando (A -> B -> C -> A); todas las que roten tienen que tener las mismas
    variantes para ir a la vez. Falta o sobra una clave, o una lista vacia: error, no una ficha a medias."""
    with open(ruta, encoding="utf-8") as fh:
        crudo = json.load(fh)
    falta, sobra = set(TEXTOS) - set(crudo), set(crudo) - set(TEXTOS)
    if falta or sobra:
        raise ValueError(f"perfil.json: faltan {sorted(falta)}, sobran {sorted(sobra)}")
    p = {k: [v] if isinstance(v, str) else list(v) for k, v in crudo.items()}
    if any(not v or not all(isinstance(x, str) and x.strip() for x in v) for v in p.values()):
        raise ValueError("perfil.json: cada clave necesita un texto o una lista de textos no vacios")
    largos = {len(v) for v in p.values() if len(v) > 1}
    if len(largos) > 1:
        raise ValueError(f"perfil.json: las claves que rotan tienen que tener las mismas variantes, no {sorted(largos)}")
    return p


# --- filas de la ficha ------------------------------------------------------------------------------------------
def _num(n):
    return f"{n:,}"


def partir(valor, ancho):
    """Lineas de como mucho `ancho` caracteres, cortando por ' · ', ', ' o espacios (el separador se queda al
    final de la linea). Nunca corta una palabra salvo que no quepa sola."""
    sep = " · " if " · " in valor else ", " if ", " in valor else " "
    trozos = valor.split(sep)
    lineas, actual = [], ""
    for i, t in enumerate(trozos):
        pieza = t + (sep.rstrip() if i < len(trozos) - 1 else "")
        prueba = pieza if not actual else actual + " " + pieza
        if not actual or len(prueba) <= ancho:
            actual = prueba
        else:
            lineas.append(actual); actual = pieza
    lineas.append(actual)
    salida = []
    for l in lineas:                       # una palabra mas larga que el ancho: se corta a pelo
        while len(l) > ancho:
            salida.append(l[:ancho]); l = l[ancho:]
        salida.append(l)
    return salida


def fila_fija(clave, valor, columnas):
    """'Clave: ..... valor' alineado a la derecha; si no cabe, el valor sigue en filas sin clave."""
    lineas = partir(valor, columnas - len(clave) - 2 - 3)
    filas = [[("clave", clave), ("puntos", ": " + "." * (columnas - len(clave) - 3 - len(lineas[0])) + " "),
              ("valor", lineas[0])]]
    for l in lineas[1:]:
        filas.append([("texto", " " * (columnas - len(l))), ("valor", l)])
    return filas


class Rotacion:
    """Una clave cuyo valor rota: los puntos son fijos y cada variante se teclea a partir de la misma columna."""

    def __init__(self, clave, variantes, columnas, puntos_min=2):
        self.clave = clave
        largo = max(len(v) for v in variantes)
        self.col = min(columnas - largo, len(clave) + 2 + 12) if largo <= columnas - len(clave) - 2 - puntos_min \
            else len(clave) + 2 + puntos_min + 1
        self.col = max(self.col, len(clave) + 2 + puntos_min + 1)
        self.lineas = [partir(v, columnas - self.col) for v in variantes]
        self.alto = max(len(l) for l in self.lineas)

    def filas(self):
        """La fila de la clave y las de continuacion (vacias: los valores van aparte, animados)."""
        cab = [("clave", self.clave), ("puntos", ": " + "." * (self.col - len(self.clave) - 3) + " ")]
        return [cab] + [[] for _ in range(self.alto - 1)]


def filas_ficha(d, columnas, perfil):
    """(filas, rotaciones): filas es una lista de filas [(clase, texto)]; rotaciones, {indice de fila: Rotacion}."""
    filas, rot = [], {}

    def poner(clave, variantes=None, valor=None):
        if variantes and len(variantes) > 1:
            r = Rotacion(clave, variantes, columnas)
            rot[len(filas)] = r
            filas.extend(r.filas())
        else:
            filas.extend(fila_fija(clave, valor if valor is not None else variantes[0], columnas))

    filas.append([("clave", LOGIN), ("texto", "@"), ("clave", "zerack"), ("puntos", " " + "—" * (columnas - len(LOGIN) - 8))])
    for k in ("OS", "Host", "Kernel", "IDE"):
        poner(k, perfil[k])
    poner("Uptime", valor=d["uptime"])
    filas.append([])
    poner("Languages.Programming", valor=", ".join(d["lenguajes"]))
    poner("Languages.Real", perfil["Languages.Real"])
    filas.append([])
    poner("Hobbies", perfil["Hobbies"])
    filas.append([])
    filas.append([("texto", "- Contact "), ("puntos", "—" * (columnas - 10))])
    for k, v in CONTACTO:
        poner(k, valor=v)
    filas.append([])
    filas.append([("texto", "- GitHub Stats "), ("puntos", "—" * (columnas - 15))])
    filas.append(_repos_y_estrellas(d, columnas))
    poner("Commits", valor=_num(d["commits"]))
    filas.append(_lineas_de_codigo(d, columnas))
    return filas, rot


def _repos_y_estrellas(d, columnas):
    """'Repos: ... 4 {Contributed: 5} | Stars: ..... 0' a `columnas` caracteres."""
    repos, contrib, estrellas = _num(d["repos"]), _num(d["contribuidos"]), _num(d["estrellas"])
    mitad = columnas // 2 + 4
    p1 = max(1, mitad - len("Repos: ") - len(repos) - len(" {Contributed: }") - len(contrib) - 1)
    p2 = max(1, columnas - mitad - len(" | Stars: ") - len(estrellas) - 1)
    return [("clave", "Repos"), ("puntos", ": " + "." * p1 + " "), ("valor", repos), ("texto", " {"),
            ("clave", "Contributed"), ("puntos", ": "), ("valor", contrib), ("texto", "}"),
            ("puntos", " | "), ("clave", "Stars"), ("puntos", ": " + "." * p2 + " "), ("valor", estrellas)]


def _lineas_de_codigo(d, columnas):
    total, mas, menos = _num(d["suma"] - d["resta"]), _num(d["suma"]) + "++", _num(d["resta"]) + "--"
    clave = "Lines of Code"
    cola = len(" ( ") + len(mas) + len(", ") + len(menos) + len(" )")
    p = max(1, columnas - len(clave) - 3 - len(total) - cola)
    return [("clave", clave), ("puntos", ": " + "." * p + " "), ("valor", total), ("texto", " ( "),
            ("suma", mas), ("puntos", ", "), ("resta", menos), ("texto", " )")]


# --- tecleo -----------------------------------------------------------------------------------------------------
TECLA, BORRA, QUIETO, HUECO = 0.045, 0.022, 3.2, 0.35     # s por caracter al teclear y al borrar; pausas


def tramos(rotaciones):
    """Para cada variante, (inicio, empieza a borrar, duracion), iguales para todas las claves que rotan: teclean
    a la vez, esperan a que acabe la mas larga, se quedan QUIETO s y borran a la vez. Y la duracion del ciclo."""
    n = len(next(iter(rotaciones.values())).lineas)
    tramo, inicio = [], 0.0
    for v in range(n):
        car = max(sum(len(l) for l in r.lineas[v]) for r in rotaciones.values())
        borrar = inicio + car * TECLA + QUIETO
        dur = car * TECLA + QUIETO + car * BORRA + HUECO
        tramo.append((inicio, borrar, dur)); inicio += dur
    return tramo, inicio


def anchos_en_el_tiempo(lineas_variante, inicio, fin_quieto, total):
    """Para cada linea de una variante: [(t/total, caracteres visibles)] en saltos de un caracter. Teclea de la
    primera linea a la ultima desde `inicio`, y desde `fin_quieto` borra de la ultima a la primera."""
    n = sum(len(l) for l in lineas_variante)
    pasos = [(0.0, 0), (inicio, 0)]
    pasos += [(inicio + (k + 1) * TECLA, k + 1) for k in range(n)]
    pasos += [(fin_quieto + (k + 1) * BORRA, n - k - 1) for k in range(n)]
    pasos.append((total, 0))
    offs, acc = [], 0
    for l in lineas_variante:
        offs.append(acc); acc += len(l)
    por_linea = []
    for l, o in zip(lineas_variante, offs):
        serie = []
        for t, c in pasos:
            v = max(0, min(len(l), c - o))
            if serie and serie[-1][1] == v:
                continue
            serie.append((min(1.0, t / total), v))
        if serie[-1][0] < 1.0:
            serie.append((1.0, serie[-1][1]))
        por_linea.append(serie)
    return por_linea


# --- SVG -------------------------------------------------------------------------------------------------------
TEMAS = {
    "oscuro": dict(fondo="#161b22", borde="#30363d", texto="#c9d1d9", clave="#ffa657", valor="#a5d6ff",
                   puntos="#616e7f", suma="#3fb950", resta="#f85149", fantasma="#c9d1d9", brillo="#a5d6ff"),
    "claro": dict(fondo="#f6f8fa", borde="#d0d7de", texto="#24292f", clave="#953800", valor="#0a3069",
                  puntos="#a0aab6", suma="#1a7f37", resta="#cf222e", fantasma="#57606a", brillo="#0969da"),
}
FORMATOS = {
    "ancho": dict(letra=16, linea=20, letra_f=16, linea_f=20, columnas=60),
    "movil": dict(letra=12, linea=16, letra_f=11, linea_f=13.5, columnas=50),
}
ANCHO_CHAR = 0.61   # em de un caracter monoespaciado (Menlo/DejaVu ~0,60; Consolas 0,55): de sobra para recortes


def _tspans(fila):
    return "".join(f'<tspan class="{c}">{escape(t)}</tspan>' for c, t in fila if t)


def _animacion(serie, total, cw, atributo, base):
    """<animate> discreto que va de salto en salto (keyTimes del 0 al 1)."""
    tiempos = ";".join(f"{t:.4f}".rstrip("0").rstrip(".") if t not in (0.0, 1.0) else str(int(t)) for t, _ in serie)
    valores = ";".join(f"{base + v * cw:.1f}" for _, v in serie)
    return (f'<animate attributeName="{atributo}" dur="{total:.2f}s" repeatCount="indefinite" calcMode="discrete" '
            f'keyTimes="{tiempos}" values="{valores}"/>')


def _rotaciones(rot, tx, base_t, f, cw, total, tramo):
    """Valores que rotan. Sin animacion (SMIL apagado o la app de GitHub), cada recorte vale lo de su atributo:
    la variante A entera y B, C a ancho 0. Con reduced-motion, el CSS fija A entera y esconde el resto."""
    defs, cuerpo = [], []
    for fila, r in rot.items():
        x = tx + r.col * cw
        for v, lineas in enumerate(r.lineas):
            series = anchos_en_el_tiempo(lineas, tramo[v][0], tramo[v][1], total)
            for j, (l, serie) in enumerate(zip(lineas, series)):
                y = base_t + (fila + j) * f["linea"]
                cid = f"t{fila}_{v}_{j}"
                ancho0 = (len(l) + 1) * cw if v == 0 else 0
                defs.append(f'<clipPath id="{cid}"><rect class="tecla" x="{x - 1:.1f}" y="{y - f["letra"]:.1f}" '
                            f'width="{ancho0:.1f}" height="{f["linea"]:.1f}">{_animacion(serie, total, cw, "width", 0)}</rect></clipPath>')
                clase = "valor varA" if v == 0 else "valor varB"
                cuerpo.append(f'<text class="{clase}" clip-path="url(#{cid})" x="{x:.1f}" y="{y:.1f}">{escape(l)}</text>')
        # cursor de bloque: sigue al tecleo de la linea que se esta escribiendo; quieto, no se ve
        cuerpo.append(_cursor(r, fila, x, base_t, f, cw, total, tramo))
    return defs, cuerpo


def _cursor(r, fila, x, base_t, f, cw, total, tramo):
    puntos = []      # (t, x, y, visible)
    for v, lineas in enumerate(r.lineas):
        inicio, fin_q, dur = tramo[v]
        n = sum(len(l) for l in lineas)
        pos = []
        for j, l in enumerate(lineas):
            pos += [(j, k) for k in range(len(l) + 1)][(1 if j else 0):]
        # pos[c] = (linea, columna) del cursor con c caracteres escritos
        for c in range(n + 1):
            j, k = pos[min(c, len(pos) - 1)]
            puntos.append((inicio + c * TECLA, x + k * cw, base_t + (fila + j) * f["linea"], True))
        for c in range(n, -1, -1):
            j, k = pos[min(c, len(pos) - 1)]
            puntos.append((fin_q + (n - c) * BORRA, x + k * cw, base_t + (fila + j) * f["linea"], True))
        puntos.append((inicio + dur - HUECO, x, base_t + fila * f["linea"], False))
    serie = [(0.0, x, base_t + fila * f["linea"], False)] + puntos
    serie = [(min(1.0, t / total), a, b, c) for t, a, b, c in serie]
    lim = [p for i, p in enumerate(serie) if i == 0 or p[1:] != serie[i - 1][1:]]
    if lim[-1][0] < 1:
        lim.append((1.0,) + lim[-1][1:])
    kt = ";".join(f"{t:.4f}" for t, *_ in lim).replace("0.0000", "0").replace("1.0000", "1")
    an = lambda attr, vals: (f'<animate attributeName="{attr}" dur="{total:.2f}s" repeatCount="indefinite" '
                             f'calcMode="discrete" keyTimes="{kt}" values="{";".join(vals)}"/>')
    alto = f["letra"] * 0.95
    return (f'<rect class="cursor" x="{x:.1f}" y="{base_t + fila * f["linea"] - f["letra"] * 0.78:.1f}" width="{cw * 0.9:.1f}" '
            f'height="{alto:.1f}" opacity="0">'
            + an("x", [f"{a:.1f}" for _, a, _, _ in lim])
            + an("y", [f"{b - f['letra'] * 0.78:.1f}" for _, _, b, _ in lim])
            + an("opacity", [".85" if c else "0" for *_, c in lim]) + "</rect>")


def svg(d, perfil, tema="oscuro", formato="ancho"):
    t, f = TEMAS[tema], FORMATOS[formato]
    fant = dibujar()
    filas, rot = filas_ficha(d, f["columnas"], perfil)
    cw, cwf = f["letra"] * ANCHO_CHAR, f["letra_f"] * ANCHO_CHAR
    m = 16
    ancho_f, alto_f = len(fant[0]) * cwf, len(fant) * f["linea_f"]
    ancho_t, alto_t = f["columnas"] * cw, len(filas) * f["linea"]
    if formato == "ancho":
        W = round(m * 3 + ancho_f + ancho_t); H = round(m * 2 + max(alto_f, alto_t) + 6)
        fx, fy, tx, ty = m, m + (max(alto_f, alto_t) - alto_f) / 2, m * 2 + ancho_f, m + (max(alto_f, alto_t) - alto_t) / 2
    else:
        W = round(m * 2 + max(ancho_f, ancho_t)); H = round(m * 3 + alto_f + alto_t + 6)
        fx, fy, tx, ty = (W - ancho_f) / 2, m, m, m * 2 + alto_f
    base_f, base_t = fy + f["linea_f"] * 0.8, ty + f["linea"] * 0.8
    ghost = "".join(f'<tspan x="{fx:.1f}" y="{base_f + i * f["linea_f"]:.1f}">{escape(l)}</tspan>' for i, l in enumerate(fant))
    texto = "".join(f'<tspan x="{tx:.1f}" y="{base_t + i * f["linea"]:.1f}">{_tspans(fila)}</tspan>'
                    for i, fila in enumerate(filas) if fila)
    defs, rotando = [], []
    if rot:
        tramo, total = tramos(rot)
        defs, rotando = _rotaciones(rot, tx, base_t, f, cw, total, tramo)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{LOGIN}@zerack">
<title>{LOGIN}@zerack</title>
<style>
text,tspan{{white-space:pre;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"DejaVu Sans Mono","Liberation Mono",monospace}}
.clave{{fill:{t['clave']}}}.valor{{fill:{t['valor']}}}.puntos{{fill:{t['puntos']}}}.texto{{fill:{t['texto']}}}
.suma{{fill:{t['suma']}}}.resta{{fill:{t['resta']}}}.cursor{{fill:{t['valor']}}}
.g{{fill:{t['fantasma']}}}.eco{{fill:{t['brillo']};opacity:0;animation:eco 7s steps(1) infinite}}
.scan{{animation:scan 5s linear infinite}}
@keyframes scan{{from{{transform:translateY(0)}}to{{transform:translateY({alto_f + 44:.0f}px)}}}}
@keyframes eco{{0%{{opacity:0;transform:translateX(0)}}62%{{opacity:.55;transform:translateX(3px)}}64%{{opacity:0;transform:translateX(0)}}88%{{opacity:.4;transform:translateX(-2px)}}89%{{opacity:0;transform:translateX(0)}}}}
@media (prefers-reduced-motion:reduce){{.scan,.eco{{animation:none;opacity:0}}.varA{{clip-path:none!important}}.varB,.cursor{{display:none!important}}}}
</style>
<defs><linearGradient id="haz" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t['brillo']}" stop-opacity="0"/><stop offset=".8" stop-color="{t['brillo']}" stop-opacity=".10"/><stop offset="1" stop-color="{t['brillo']}" stop-opacity=".22"/></linearGradient>
<clipPath id="caja"><rect x="{fx - 4:.1f}" y="{fy:.1f}" width="{ancho_f + 8:.1f}" height="{alto_f:.1f}"/></clipPath>
{"".join(defs)}</defs>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="{t['fondo']}" stroke="{t['borde']}"/>
<g clip-path="url(#caja)" font-size="{f['letra_f']}">
<text class="eco">{ghost}</text>
<text class="g">{ghost}</text>
<rect class="scan" x="{fx - 4:.1f}" y="{fy - 44:.1f}" width="{ancho_f + 8:.1f}" height="40" fill="url(#haz)"/>
</g>
<g font-size="{f['letra']}"><text>{texto}</text>
{"".join(rotando)}</g>
</svg>
"""


SALIDAS = {("oscuro", "ancho"): "oscuro.svg", ("claro", "ancho"): "claro.svg",
           ("oscuro", "movil"): "oscuro-movil.svg", ("claro", "movil"): "claro-movil.svg"}


def escribir(d, perfil, carpeta):
    os.makedirs(carpeta, exist_ok=True)
    for (tema, formato), nombre in SALIDAS.items():
        with open(os.path.join(carpeta, nombre), "w", encoding="utf-8") as fh:
            fh.write(svg(d, perfil, tema, formato))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--datos", help="JSON con lo que devolveria leer_api (sin red)")
    p.add_argument("--salida", default=os.path.join(RAIZ, "assets"))
    p.add_argument("--hoy", help="AAAA-MM-DD (por defecto, hoy en UTC)")
    p.add_argument("--perfil", default=PERFIL)
    a = p.parse_args(argv)
    perfil = leer_perfil(a.perfil)          # antes de gastar API si perfil.json esta mal
    hoy = datetime.date.fromisoformat(a.hoy) if a.hoy else datetime.datetime.now(datetime.timezone.utc).date()
    if a.datos:
        with open(a.datos, encoding="utf-8") as fh:
            crudo = json.load(fh)
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("falta GITHUB_TOKEN")
        cache = {}
        if os.path.exists(CACHE):
            with open(CACHE) as fh:
                cache = json.load(fh)
        crudo = leer_api(token, cache)
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w") as fh:
            json.dump(crudo["historias"], fh, indent=1, sort_keys=True)
            fh.write("\n")
    d = resumen(crudo, hoy)
    escribir(d, perfil, a.salida)
    print(json.dumps(d, ensure_ascii=False))


if __name__ == "__main__":
    main()
