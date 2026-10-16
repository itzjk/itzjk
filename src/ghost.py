"""The hooded figure, drawn procedurally in ASCII.

A cowl seen from the side, facing right (towards the card), with the profile only hinted by a thin rim of light
under the hood: no eyes, no mouth, no features, nothing recognizable. The cloak dissolves into static at the
bottom and a couple of rows are glitched sideways. Same seed, same drawing.

Each cell is a (char, kind) pair: kind "body" is the figure, "rim" is the accent light (drawn in the accent colour).
"""
import math
import random

# characters from little ink to a lot, for a monospace font
RAMP = " .`':,;-~^=+*?%#&@"

COLS, ROWS = 60, 44
CELL_W, CELL_H = 5.49, 11.3           # px of a cell at the size the wide card draws it (9 px font, 11.3 px line)
W, H = COLS * CELL_W, ROWS * CELL_H   # canvas in px: all shapes below are in these units

# light from the front (right), above, towards the viewer
LIGHT = (0.62, -0.42, 0.66)


def _norm(v):
    n = math.sqrt(sum(c * c for c in v))
    return tuple(c / n for c in v)


LIGHT = _norm(LIGHT)


def _ellipsoid(px, py, cx, cy, rx, ry):
    """(inside, normal) of an ellipsoid cap seen from the front."""
    nx, ny = (px - cx) / rx, (py - cy) / ry
    d = nx * nx + ny * ny
    return d <= 1.0, (nx, ny, math.sqrt(max(0.0, 1.0 - d)))


def _hood(px, py):
    """The cowl: a big rounded volume leaning back, with a soft tip at the top-left."""
    inside, n = _ellipsoid(px, py, 160, 172, 104, 130)
    tip = ((px - 120) / 60) ** 2 + ((py - 76) / 52) ** 2 <= 1.0       # the cowl's tip, pulled back
    return inside or tip, n


# the face profile under the hood, facing right: x of the silhouette edge for a given y (px). It is a smooth,
# generic curve (brow, a short nose, chin) used only as the edge of the rim light.
PROFILE = [(120, 212), (138, 214), (150, 219), (159, 229), (167, 241), (174, 229), (182, 232), (190, 226),
           (200, 230), (213, 219), (228, 204), (246, 186)]


def _profile_x(py):
    for (y0, x0), (y1, x1) in zip(PROFILE, PROFILE[1:]):
        if y0 <= py <= y1:
            t = (py - y0) / (y1 - y0)
            t = t * t * (3 - 2 * t)                  # smoothstep: no kinks in the edge
            return x0 + (x1 - x0) * t
    return None


def _opening(px, py):
    """How deep inside the hood opening a point is: < 1 inside (0 at its centre)."""
    return math.sqrt(((px - 216) / 42) ** 2 + ((py - 184) / 70) ** 2)


def _cloak(px, py):
    """Shoulders and cloak below the hood: widens fast, then falls straight, with folds."""
    if py < 228:
        return False, None
    t = min(1.0, (py - 228) / 120)
    half = 58 + 98 * math.sqrt(t)
    cx = 150 + 6 * t
    nx = (px - cx) / half
    if abs(nx) > 1:
        return False, None
    fold = 0.22 * math.sin(px / 8.5 + py / 55) + 0.12 * math.sin(px / 3.7 - py / 31)
    return True, (nx + fold * 0.35, -0.25 + 0.1 * t, math.sqrt(max(0.05, 1 - nx * nx)))


def intensity(px, py, rnd):
    """(value 0..1, kind) of one point of the figure, or (0, None) outside."""
    in_hood, nh = _hood(px, py)
    in_cloak, nc = _cloak(px, py)
    if not (in_hood or in_cloak):
        return 0.0, None
    if in_hood:
        o = _opening(px, py)
        if o < 1.0:
            edge = _profile_x(py)
            if edge is not None and px < edge:
                # inside the profile: almost black, except a thin rim where the light catches its edge
                return (0.16 + 0.10 * rnd.random(), "body")      # the face in shadow: texture, no features
            return (0.0, "body")                         # in front of the face: the hood's darkness
        n = nh
    else:
        n = nc
    diffuse = max(0.0, sum(a * b for a, b in zip(n, LIGHT)))
    v = 0.10 + 0.9 * diffuse ** 1.25
    if in_hood:
        o = _opening(px, py)
        if o < 1.55:                                     # ambient occlusion around the opening
            v *= 0.25 + 0.75 * ((o - 1.0) / 0.55) ** 1.4
        if 1.0 <= o < 1.16 and px > 200:                 # the lit lip of the hood, facing the light
            return 0.6, "body"
    else:
        v *= 0.55 + 0.45 * min(1.0, (py - 228) / 60)     # the hood shadows the shoulders
    # back edge rim light (cool accent) where the silhouette meets the dark on the left
    left_x = px - CELL_W * 1.2
    if not (_hood(left_x, py)[0] or _cloak(left_x, py)[0]) and py < 430:
        return 0.75, "rim"
    if py > 420:                                         # dissolve into static
        keep = max(0.0, 1 - (py - 420) / (H - 420))
        if rnd.random() > keep:
            return (0.12 if rnd.random() < 0.25 else 0.0), "body"
        v *= keep
    return v, "body"


GLITCH_ROWS = {24: 3, 25: 3, 33: -2}


def _stroke(dx):
    """Contour character for an edge that moves `dx` px to the right per row going down."""
    if abs(dx) < CELL_W * 0.4:
        return "|"
    return "\\" if dx > 0 else "/"


def _opening_front(py):
    """x of the hood's front lip (right edge of the opening) at height py, or None."""
    t = (py - 184) / 70
    return 216 + 42 * math.sqrt(1 - t * t) if abs(t) < 1 else None


def _contours(rows):
    """Crisp lines in the accent colour: the profile under the hood and the hood's lit front lip."""
    for edge_at in (_profile_x, _opening_front):
        for r in range(ROWS):
            py = (r + 0.5) * CELL_H
            x, below = edge_at(py), edge_at(py + CELL_H)
            if x is None:
                continue
            if edge_at is _profile_x and _opening(x, py) >= 1.0:
                continue
            c = int(x / CELL_W)
            if 0 <= c < COLS:
                dx = (below - x) if below is not None else 0.0
                rows[r][c] = (_stroke(dx), "rim")                    # rows shifted sideways (in cells)


def draw(seed=7):
    """ROWS rows, each a list of COLS (char, kind) cells."""
    rnd = random.Random(seed)
    rows = []
    for r in range(ROWS):
        py = (r + 0.5) * CELL_H
        row = []
        for c in range(COLS):
            px = (c + 0.5) * CELL_W
            v, kind = intensity(px, py, rnd)
            if kind is None:
                stray = py > 440 and rnd.random() < 0.035
                row.append(("." if stray else " ", "body"))
                continue
            v = min(1.0, max(0.0, v + rnd.uniform(-0.045, 0.045)))
            i = int(round(v ** 0.9 * (len(RAMP) - 1)))
            row.append((RAMP[i], kind))
        rows.append(row)
    _contours(rows)
    out = []
    for r, row in enumerate(rows):
        shift = GLITCH_ROWS.get(r, 0)
        if shift:
            blank = [(" ", "body")] * abs(shift)
            row = (blank + row[:-shift]) if shift > 0 else (row[-shift:] + blank)
            row = [(ch, "rim" if ch != " " and rnd.random() < 0.35 else kind) for ch, kind in row]
        out.append(row)
    return out


def as_text(rows=None):
    return ["".join(ch for ch, _ in row) for row in (rows or draw())]


if __name__ == "__main__":
    print("\n".join(as_text()))
