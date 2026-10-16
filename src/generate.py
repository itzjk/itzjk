"""Builds the profile card (neofetch style) as four SVGs: light and dark, wide and mobile.

Numbers come from the GitHub API (GraphQL, public data only). Fixed texts (OS, Host, Kernel, IDE, Languages.Real,
Hobbies) live in profile.json at the repo root: one line each, edit them there without touching code. A value
can be a list: then it rotates on the card, typed and erased (A -> B -> C -> A). Only the fields in USER_FIELDS
are read from the API: never name, email, location, bio or avatar.

    GITHUB_TOKEN=... python3 src/generate.py         # in the Action, with the repo's own token
    python3 src/generate.py --data fixture.json      # offline: data already fetched (tests)

Lines of code +/-: additions/deletions of the user's commits on the default branch of each public repo. That is
the expensive part, so it is cached per repo in cache/repos.json and only fetched again when the branch head
moves. This repo (itzjk/itzjk) does not count: the Action commits to it every day and the card would inflate itself.
"""
import argparse, datetime, json, os, sys, urllib.request
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghost

LOGIN = "itzjk"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache", "repos.json")
PROFILE = os.path.join(ROOT, "profile.json")
API = "https://api.github.com/graphql"

TEXTS = ("OS", "Host", "Kernel", "IDE", "Languages.Real", "Hobbies")   # the keys profile.json must have
CONTACT = [("GitHub", "github.com/itzjk"), ("X", "x.com/Izkszk")]
NOT_PROGRAMMING = {"HTML", "CSS", "SCSS", "Less", "Jupyter Notebook", "Dockerfile", "Makefile"}
MAX_LANGUAGES = 5

USER_FIELDS = """
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
Q_USER = "query($login: String!) { user(login: $login) { %s } }" % USER_FIELDS
Q_HISTORY = """query($owner: String!, $name: String!, $author: ID!, $after: String) {
  repository(owner: $owner, name: $name) { defaultBranchRef { target { ... on Commit {
    history(first: 100, after: $after, author: {id: $author}) {
      totalCount pageInfo { hasNextPage endCursor } nodes { additions deletions } } } } } } }"""


# --- API --------------------------------------------------------------------------------------------------------
def graphql(token, query, **variables):
    req = urllib.request.Request(API, json.dumps({"query": query, "variables": variables}).encode(),
                                 {"Authorization": f"bearer {token}", "Content-Type": "application/json",
                                  "User-Agent": "itzjk-profile-card"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)
    if res.get("errors"):
        raise RuntimeError(f"GraphQL: {res['errors']}")
    return res["data"]


def history(token, repo, author):
    """(commits, additions, deletions) of the author on the default branch of `repo`."""
    commits = adds = dels = 0
    after = None
    while True:
        d = graphql(token, Q_HISTORY, owner=LOGIN, name=repo, author=author, after=after)
        h = d["repository"]["defaultBranchRef"]["target"]["history"]
        commits = h["totalCount"]
        for n in h["nodes"]:
            adds += n["additions"]; dels += n["deletions"]
        if not h["pageInfo"]["hasNextPage"]:
            return commits, adds, dels
        after = h["pageInfo"]["endCursor"]


def read_api(token, cache):
    """Raw data: the user and, per repo, its history (from the cache when the branch head has not moved)."""
    user = graphql(token, Q_USER, login=LOGIN)["user"]
    repos = {}
    for r in user["repositories"]["nodes"]:
        if r["name"] == LOGIN:              # this card's repo: automatic commits, they do not count
            continue
        ref = r["defaultBranchRef"]
        oid = ref["target"]["oid"] if ref else None
        old = cache.get(r["name"])
        if oid is None:
            repos[r["name"]] = dict(oid=None, commits=0, additions=0, deletions=0)
        elif old and old["oid"] == oid:
            repos[r["name"]] = old
        else:
            c, a, d = history(token, r["name"], user["id"])
            repos[r["name"]] = dict(oid=oid, commits=c, additions=a, deletions=d)
    return {"user": user, "histories": repos}


# --- what the card shows ------------------------------------------------------------------------------------------
def uptime(created, today):
    """'1 year, 10 months, 23 days' between two dates. Months go date to date (Jan 31 -> Feb 28 is one month)
    and days are what is left from there."""
    months = (today.year - created.year) * 12 + today.month - created.month - (today.day < created.day)
    y, m = divmod(created.month - 1 + months, 12)
    y += created.year
    last = (datetime.date(y + (m == 11), (m + 1) % 12 + 1, 1) - datetime.timedelta(days=1)).day
    days = (today - datetime.date(y, m + 1, min(created.day, last))).days
    part = lambda n, one: f"{n} {one}" + ("" if n == 1 else "s")
    return ", ".join([part(months // 12, "year"), part(months % 12, "month"), part(days, "day")])


def summary(raw, today):
    """Everything the card shows, taken only from the fields read from the API."""
    u = raw["user"]
    nodes = u["repositories"]["nodes"]
    size = {}
    for r in nodes:
        for e in r["languages"]["edges"]:
            n = e["node"]["name"]
            if n not in NOT_PROGRAMMING:
                size[n] = size.get(n, 0) + e["size"]
    languages = [n for n, _ in sorted(size.items(), key=lambda kv: (-kv[1], kv[0]))][:MAX_LANGUAGES]
    h = raw["histories"].values()
    created = datetime.date.fromisoformat(u["createdAt"][:10])
    return dict(uptime=uptime(created, today), languages=languages,
                repos=u["repositories"]["totalCount"], contributed=u["repositoriesContributedTo"]["totalCount"],
                stars=sum(r["stargazerCount"] for r in nodes),
                commits=sum(x["commits"] for x in h), additions=sum(x["additions"] for x in h),
                deletions=sum(x["deletions"] for x in h))


def read_profile(path=PROFILE):
    """Fixed texts: {key: [variants]}. A string is a list of one. Keys with several variants rotate together, so
    they must all have the same number. A missing or extra key, or an empty value, is an error: never half a card."""
    with open(path, encoding="utf-8") as fh:
        raw = json.load(fh)
    missing, extra = set(TEXTS) - set(raw), set(raw) - set(TEXTS)
    if missing or extra:
        raise ValueError(f"profile.json: missing {sorted(missing)}, unexpected {sorted(extra)}")
    p = {k: [v] if isinstance(v, str) else list(v) for k, v in raw.items()}
    if any(not v or not all(isinstance(x, str) and x.strip() for x in v) for v in p.values()):
        raise ValueError("profile.json: every key needs a non-empty text or list of texts")
    counts = {len(v) for v in p.values() if len(v) > 1}
    if len(counts) > 1:
        raise ValueError(f"profile.json: rotating keys need the same number of variants, not {sorted(counts)}")
    return p


# --- rows of the card ---------------------------------------------------------------------------------------------
def _n(x):
    return f"{x:,}"


def wrap(value, width):
    """Lines of at most `width` chars, cut at ' · ', ', ' or spaces (the separator stays at the end of the line).
    A word is only cut when it does not fit on its own."""
    sep = " · " if " · " in value else ", " if ", " in value else " "
    pieces = value.split(sep)
    lines, current = [], ""
    for i, t in enumerate(pieces):
        piece = t + (sep.rstrip() if i < len(pieces) - 1 else "")
        attempt = piece if not current else current + " " + piece
        if not current or len(attempt) <= width:
            current = attempt
        else:
            lines.append(current); current = piece
    lines.append(current)
    out = []
    for l in lines:
        while len(l) > width:
            out.append(l[:width]); l = l[width:]
        out.append(l)
    return out


def fixed_row(key, value, cols):
    """'Key: ..... value' right-aligned; when it does not fit, the value continues on rows without a key."""
    lines = wrap(value, cols - len(key) - 2 - 3)
    rows = [[("key", key), ("dots", ": " + "." * (cols - len(key) - 3 - len(lines[0])) + " "), ("value", lines[0])]]
    for l in lines[1:]:
        rows.append([("text", " " * (cols - len(l))), ("value", l)])
    return rows


class Rotation:
    """A key whose value rotates: the dots are fixed and every variant is typed from the same column."""

    def __init__(self, key, variants, cols, min_dots=2):
        self.key = key
        longest = max(len(v) for v in variants)
        self.col = max(min(cols - longest, len(key) + 2 + 12), len(key) + 2 + min_dots + 1)
        self.lines = [wrap(v, cols - self.col) for v in variants]
        self.height = max(len(l) for l in self.lines)

    def rows(self):
        head = [("key", self.key), ("dots", ": " + "." * (self.col - len(self.key) - 3) + " ")]
        return [head] + [[] for _ in range(self.height - 1)]


def card_rows(d, cols, profile):
    """(rows, rotations): rows is a list of [(class, text)]; rotations, {row index: Rotation}."""
    rows, rot = [], {}

    def put(key, variants=None, value=None):
        if variants and len(variants) > 1:
            r = Rotation(key, variants, cols)
            rot[len(rows)] = r
            rows.extend(r.rows())
        else:
            rows.extend(fixed_row(key, value if value is not None else variants[0], cols))

    def rule(title):
        rows.append([("text", f"- {title} "), ("dots", "—" * (cols - len(title) - 3))])

    rows.append([("key", LOGIN), ("text", "@"), ("key", "zerack"), ("dots", " " + "—" * (cols - len(LOGIN) - 8))])
    for k in ("OS", "Host", "Kernel", "IDE"):
        put(k, profile[k])
    put("Uptime", value=d["uptime"])
    rows.append([])
    put("Languages.Programming", value=", ".join(d["languages"]))
    put("Languages.Real", profile["Languages.Real"])
    rows.append([])
    put("Hobbies", profile["Hobbies"])
    rows.append([])
    rule("Contact")
    for k, v in CONTACT:
        put(k, value=v)
    rows.append([])
    rule("GitHub Stats")
    rows.append(_repos_and_stars(d, cols))
    put("Commits", value=_n(d["commits"]))
    rows.append(_lines_of_code(d, cols))
    return rows, rot


def _repos_and_stars(d, cols):
    """'Repos: ... 4 {Contributed: 5} | Stars: ..... 0' in `cols` chars."""
    repos, contrib, stars = _n(d["repos"]), _n(d["contributed"]), _n(d["stars"])
    half = cols // 2 + 4
    p1 = max(1, half - len("Repos: ") - len(repos) - len(" {Contributed: }") - len(contrib) - 1)
    p2 = max(1, cols - half - len(" | Stars: ") - len(stars) - 1)
    return [("key", "Repos"), ("dots", ": " + "." * p1 + " "), ("value", repos), ("text", " {"),
            ("key", "Contributed"), ("dots", ": "), ("value", contrib), ("text", "}"),
            ("dots", " | "), ("key", "Stars"), ("dots", ": " + "." * p2 + " "), ("value", stars)]


def _lines_of_code(d, cols):
    total, plus, minus = _n(d["additions"] - d["deletions"]), _n(d["additions"]) + "++", _n(d["deletions"]) + "--"
    key = "Lines of Code"
    tail = len(" ( ") + len(plus) + len(", ") + len(minus) + len(" )")
    p = max(1, cols - len(key) - 3 - len(total) - tail)
    return [("key", key), ("dots", ": " + "." * p + " "), ("value", total), ("text", " ( "),
            ("add", plus), ("dots", ", "), ("del", minus), ("text", " )")]


# --- typing -------------------------------------------------------------------------------------------------------
TYPE, ERASE, HOLD, GAP = 0.045, 0.022, 3.2, 0.35     # s per char typing and erasing; pauses


def slots(rotations):
    """Per variant, (start, erase from, duration), the same for every rotating key: they type together, wait for
    the longest, hold HOLD s and erase together. And the length of the whole cycle."""
    n = len(next(iter(rotations.values())).lines)
    out, start = [], 0.0
    for v in range(n):
        chars = max(sum(len(l) for l in r.lines[v]) for r in rotations.values())
        erase = start + chars * TYPE + HOLD
        dur = chars * TYPE + HOLD + chars * ERASE + GAP
        out.append((start, erase, dur)); start += dur
    return out, start


def widths_over_time(lines, start, erase_from, total):
    """For each line of a variant: [(t/total, visible chars)] in one-char steps. Types from the first line to the
    last from `start`, and from `erase_from` erases from the last line back to the first."""
    n = sum(len(l) for l in lines)
    steps = [(0.0, 0), (start, 0)]
    steps += [(start + (k + 1) * TYPE, k + 1) for k in range(n)]
    steps += [(erase_from + (k + 1) * ERASE, n - k - 1) for k in range(n)]
    steps.append((total, 0))
    offsets, acc = [], 0
    for l in lines:
        offsets.append(acc); acc += len(l)
    per_line = []
    for l, o in zip(lines, offsets):
        series = []
        for t, c in steps:
            v = max(0, min(len(l), c - o))
            if series and series[-1][1] == v:
                continue
            series.append((min(1.0, t / total), v))
        if series[-1][0] < 1.0:
            series.append((1.0, series[-1][1]))
        per_line.append(series)
    return per_line


# --- SVG ----------------------------------------------------------------------------------------------------------
THEMES = {
    "dark": dict(bg="#0d1117", panel="#161b22", border="#30363d", text="#c9d1d9", key="#ffa657", value="#a5d6ff",
                 dots="#616e7f", add="#3fb950", deleted="#f85149", figure="#8b949e", rim="#79c0ff", glow="#58a6ff",
                 palette=["#484f58", "#ff7b72", "#3fb950", "#d29922", "#58a6ff", "#bc8cff", "#39c5cf", "#b1bac4"]),
    "light": dict(bg="#ffffff", panel="#f6f8fa", border="#d0d7de", text="#24292f", key="#953800", value="#0a3069",
                  dots="#a0aab6", add="#1a7f37", deleted="#cf222e", figure="#57606a", rim="#0969da", glow="#0969da",
                  palette=["#24292f", "#cf222e", "#1a7f37", "#9a6700", "#0969da", "#8250df", "#1b7c83", "#6e7781"]),
}
LAYOUTS = {
    "wide": dict(font=16, line=20, fig_font=9, fig_line=11.3, cols=60),
    "mobile": dict(font=12, line=16, fig_font=7, fig_line=8.8, cols=50),
}
CHAR_EM = 0.61   # em of a monospace char (Menlo/DejaVu ~0.60, Consolas 0.55): generous for clip widths


def _tspans(row):
    return "".join(f'<tspan class="{c}">{escape(t)}</tspan>' for c, t in row if t)


def _figure_tspans(rows, x, y0, line):
    """One <tspan> per row; accent cells (rim light) go in their own nested tspans."""
    out = []
    for i, row in enumerate(rows):
        parts, cur, kind = [], "", None
        for ch, k in row:
            k = "rim" if (k == "rim" and ch != " ") else "body"
            if k != kind and cur:
                parts.append((kind, cur)); cur = ""
            kind = k; cur += ch
        parts.append((kind, cur))
        body = "".join(escape(t) if k == "body" else f'<tspan class="rim">{escape(t)}</tspan>' for k, t in parts)
        out.append(f'<tspan x="{x:.1f}" y="{y0 + i * line:.1f}">{body}</tspan>')
    return "".join(out)


def _animate(series, total, cw, attribute):
    """Discrete <animate> jumping from step to step (keyTimes 0..1)."""
    times = ";".join("0" if t == 0 else "1" if t == 1 else f"{t:.4f}".rstrip("0") for t, _ in series)
    values = ";".join(f"{v * cw:.1f}" for _, v in series)
    return (f'<animate attributeName="{attribute}" dur="{total:.2f}s" repeatCount="indefinite" calcMode="discrete" '
            f'keyTimes="{times}" values="{values}"/>')


def _rotations(rot, tx, base_y, L, cw, total, slot):
    """Rotating values. Without animation (SMIL off, the GitHub mobile app) each clip keeps its attribute:
    variant A whole, B and C at width 0. With reduced motion, CSS shows A whole and hides the rest."""
    defs, body = [], []
    for row, r in rot.items():
        x = tx + r.col * cw
        for v, lines in enumerate(r.lines):
            series = widths_over_time(lines, slot[v][0], slot[v][1], total)
            for j, (l, s) in enumerate(zip(lines, series)):
                y = base_y + (row + j) * L["line"]
                cid = f"t{row}_{v}_{j}"
                w0 = (len(l) + 1) * cw if v == 0 else 0
                defs.append(f'<clipPath id="{cid}"><rect class="typing" x="{x - 1:.1f}" y="{y - L["font"]:.1f}" '
                            f'width="{w0:.1f}" height="{L["line"]:.1f}">{_animate(s, total, cw, "width")}</rect></clipPath>')
                cls = "value varA" if v == 0 else "value varB"
                body.append(f'<text class="{cls}" clip-path="url(#{cid})" x="{x:.1f}" y="{y:.1f}">{escape(l)}</text>')
        body.append(_cursor(r, row, x, base_y, L, cw, total, slot))
    return defs, body


def _cursor(r, row, x, base_y, L, cw, total, slot):
    """Block cursor following the typing; hidden while still (so a static render shows no cursor)."""
    points = []      # (t, x, y, visible)
    for v, lines in enumerate(r.lines):
        start, erase_from, dur = slot[v]
        n = sum(len(l) for l in lines)
        pos = []
        for j, l in enumerate(lines):
            pos += [(j, k) for k in range(len(l) + 1)][(1 if j else 0):]
        for c in range(n + 1):
            j, k = pos[min(c, len(pos) - 1)]
            points.append((start + c * TYPE, x + k * cw, base_y + (row + j) * L["line"], True))
        for c in range(n, -1, -1):
            j, k = pos[min(c, len(pos) - 1)]
            points.append((erase_from + (n - c) * ERASE, x + k * cw, base_y + (row + j) * L["line"], True))
        points.append((start + dur - GAP, x, base_y + row * L["line"], False))
    series = [(0.0, x, base_y + row * L["line"], False)] + points
    series = [(min(1.0, t / total), a, b, c) for t, a, b, c in series]
    kept = [p for i, p in enumerate(series) if i == 0 or p[1:] != series[i - 1][1:]]
    if kept[-1][0] < 1:
        kept.append((1.0,) + kept[-1][1:])
    kt = ";".join("0" if t == 0 else "1" if t == 1 else f"{t:.4f}" for t, *_ in kept)
    anim = lambda attr, vals: (f'<animate attributeName="{attr}" dur="{total:.2f}s" repeatCount="indefinite" '
                               f'calcMode="discrete" keyTimes="{kt}" values="{";".join(vals)}"/>')
    return (f'<rect class="cursor" x="{x:.1f}" y="{base_y + row * L["line"] - L["font"] * 0.78:.1f}" '
            f'width="{cw * 0.9:.1f}" height="{L["font"] * 0.95:.1f}" opacity="0">'
            + anim("x", [f"{a:.1f}" for _, a, _, _ in kept])
            + anim("y", [f"{b - L['font'] * 0.78:.1f}" for _, _, b, _ in kept])
            + anim("opacity", [".85" if c else "0" for *_, c in kept]) + "</rect>")


def svg(d, profile, theme="dark", layout="wide"):
    t, L = THEMES[theme], LAYOUTS[layout]
    fig = ghost.draw()
    rows, rot = card_rows(d, L["cols"], profile)
    cw, fcw = L["font"] * CHAR_EM, L["fig_font"] * CHAR_EM
    m = 18
    fig_w, fig_h = len(fig[0]) * fcw, len(fig) * L["fig_line"]
    txt_w = L["cols"] * cw
    txt_h = (len(rows) + 2) * L["line"]                    # + a blank row and the colour palette
    if layout == "wide":
        W = round(m * 3 + fig_w + txt_w); H = round(m * 2 + max(fig_h, txt_h))
        fx, fy = m, m + (max(fig_h, txt_h) - fig_h) / 2
        tx, ty = m * 2 + fig_w, m + (max(fig_h, txt_h) - txt_h) / 2
    else:
        W = round(m * 2 + max(fig_w, txt_w)); H = round(m * 3 + fig_h + txt_h)
        fx, fy, tx, ty = (W - fig_w) / 2, m, m, m * 2 + fig_h
    base_f, base_y = fy + L["fig_line"] * 0.8, ty + L["line"] * 0.8
    figure = _figure_tspans(fig, fx, base_f, L["fig_line"])
    text = "".join(f'<tspan x="{tx:.1f}" y="{base_y + i * L["line"]:.1f}">{_tspans(r)}</tspan>'
                   for i, r in enumerate(rows) if r)
    py = base_y + (len(rows) + 1) * L["line"] - L["font"] * 0.78
    sw = cw * 3
    palette = "".join(f'<rect x="{tx + i * sw:.1f}" y="{py:.1f}" width="{sw:.1f}" height="{L["font"] * 0.95:.1f}" fill="{c}"/>'
                      for i, c in enumerate(t["palette"]))
    defs, rotating = [], []
    if rot:
        slot, total = slots(rot)
        defs, rotating = _rotations(rot, tx, base_y, L, cw, total, slot)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{LOGIN}@zerack profile card">
<title>{LOGIN}@zerack</title>
<style>
text,tspan{{white-space:pre;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,"DejaVu Sans Mono","Liberation Mono",monospace}}
.key{{fill:{t['key']}}}.value{{fill:{t['value']}}}.dots{{fill:{t['dots']}}}.text{{fill:{t['text']}}}
.add{{fill:{t['add']}}}.del{{fill:{t['deleted']}}}.cursor{{fill:{t['value']}}}
.fig{{fill:{t['figure']}}}.rim{{fill:{t['rim']}}}.echo{{fill:{t['glow']};opacity:0;animation:echo 7s steps(1) infinite}}
.scan{{animation:scan 6s linear infinite}}
@keyframes scan{{from{{transform:translateY(0)}}to{{transform:translateY({fig_h + 48:.0f}px)}}}}
@keyframes echo{{0%{{opacity:0;transform:translateX(0)}}62%{{opacity:.5;transform:translateX(3px)}}63.5%{{opacity:0;transform:translateX(0)}}88%{{opacity:.35;transform:translateX(-2px)}}89%{{opacity:0;transform:translateX(0)}}}}
@media (prefers-reduced-motion:reduce){{.scan,.echo{{animation:none;opacity:0}}.varA{{clip-path:none!important}}.varB,.cursor{{display:none!important}}}}
</style>
<defs><linearGradient id="beam" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t['glow']}" stop-opacity="0"/><stop offset=".8" stop-color="{t['glow']}" stop-opacity=".08"/><stop offset="1" stop-color="{t['glow']}" stop-opacity=".2"/></linearGradient>
<radialGradient id="halo" cx=".5" cy=".4" r=".5"><stop offset="0" stop-color="{t['glow']}" stop-opacity=".09"/><stop offset="1" stop-color="{t['glow']}" stop-opacity="0"/></radialGradient>
<clipPath id="figbox"><rect x="{fx - 4:.1f}" y="{fy:.1f}" width="{fig_w + 8:.1f}" height="{fig_h:.1f}"/></clipPath>
<text id="figure" font-size="{L['fig_font']}">{figure}</text>
{"".join(defs)}</defs>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="12" fill="{t['panel']}" stroke="{t['border']}"/>
<rect x="{fx - 6:.1f}" y="{fy - 6:.1f}" width="{fig_w + 12:.1f}" height="{fig_h + 12:.1f}" rx="8" fill="url(#halo)"/>
<g clip-path="url(#figbox)">
<use href="#figure" class="echo"/>
<use href="#figure" class="fig"/>
<rect class="scan" x="{fx - 4:.1f}" y="{fy - 48:.1f}" width="{fig_w + 8:.1f}" height="44" fill="url(#beam)"/>
</g>
<g font-size="{L['font']}"><text>{text}</text>
{"".join(rotating)}</g>
{palette}
</svg>
"""


OUTPUTS = {("dark", "wide"): "dark.svg", ("light", "wide"): "light.svg",
           ("dark", "mobile"): "dark-mobile.svg", ("light", "mobile"): "light-mobile.svg"}


def write(d, profile, folder):
    os.makedirs(folder, exist_ok=True)
    for (theme, layout), name in OUTPUTS.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as fh:
            fh.write(svg(d, profile, theme, layout))


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--data", help="JSON with what read_api would return (offline)")
    p.add_argument("--out", default=os.path.join(ROOT, "assets"))
    p.add_argument("--today", help="YYYY-MM-DD (default: today in UTC)")
    p.add_argument("--profile", default=PROFILE)
    a = p.parse_args(argv)
    profile = read_profile(a.profile)          # before spending API calls if profile.json is wrong
    today = datetime.date.fromisoformat(a.today) if a.today else datetime.datetime.now(datetime.timezone.utc).date()
    if a.data:
        with open(a.data, encoding="utf-8") as fh:
            raw = json.load(fh)
    else:
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            sys.exit("GITHUB_TOKEN is not set")
        cache = {}
        if os.path.exists(CACHE):
            with open(CACHE) as fh:
                cache = json.load(fh)
        raw = read_api(token, cache)
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE, "w") as fh:
            json.dump(raw["histories"], fh, indent=1, sort_keys=True)
            fh.write("\n")
    d = summary(raw, today)
    write(d, profile, a.out)
    print(json.dumps(d, ensure_ascii=False))


if __name__ == "__main__":
    main()
