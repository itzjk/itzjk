"""El fantasma encapuchado en ASCII: capucha y hombros sombreados, sin cara (la capucha esta vacia) y la parte
de abajo deshaciendose en estatica. Se calcula, no se copia de ningun sitio: misma semilla, mismo dibujo."""
import math
import random

RAMPA = " .,:;-=+*#%@"


def _capucha(x, y):
    """(dentro, normal) de la capucha: elipse con la punta un poco alzada."""
    cx, cy, rx, ry = 0.0, 0.36, 0.62, 0.30
    if y < cy:
        rx *= 1 - 0.22 * ((cy - y) / ry) ** 2           # se estrecha hacia la punta
    nx, ny = (x - cx) / rx, (y - cy) / ry
    d = nx * nx + ny * ny
    return d <= 1, (nx, ny, math.sqrt(max(0.0, 1 - d)))


def _hueco(x, y):
    """Distancia normalizada al borde del hueco de la cara (< 1 dentro)."""
    return ((x / 0.30) ** 2 + ((y - 0.39) / 0.16) ** 2) ** 0.5


def _cuerpo(x, y):
    if y < 0.52:
        return False, None
    w = 0.40 + 0.58 * min(1.0, ((y - 0.52) / 0.26)) ** 0.5     # hombros redondos
    nx = x / w
    return abs(nx) <= 1, (nx, -0.15, math.sqrt(max(0.0, 1 - nx * nx)))


def dibujar(columnas=34, filas=25, semilla=7):
    """Lineas de texto (todas de `columnas` caracteres) del fantasma. Coordenadas: x en [-1, 1], y en [0, 1]."""
    rnd = random.Random(semilla)
    luz = (-0.5, -0.55, 0.67)
    n = math.sqrt(sum(c * c for c in luz)); luz = tuple(c / n for c in luz)
    lineas = []
    for f in range(filas):
        y = (f + 0.5) / filas
        fila = []
        for c in range(columnas):
            x = ((c + 0.5) / columnas) * 2 - 1
            dentro_c, nc = _capucha(x, y)
            dentro_b, nb = _cuerpo(x, y)
            if not (dentro_c or dentro_b):
                # estatica suelta alrededor de la parte baja
                fila.append("." if y > 0.82 and rnd.random() < 0.04 else " ")
                continue
            h = _hueco(x, y)
            if dentro_c and h < 1:
                fila.append(":" if rnd.random() < 0.02 else " ")   # sin cara: el hueco esta vacio
                continue
            nrm = nc if dentro_c else nb
            difusa = max(0.0, sum(a * b for a, b in zip(nrm, luz)))
            v = 0.18 + 0.82 * difusa
            if dentro_c and h < 1.45:
                v *= 0.35 + 0.65 * (h - 1) / 0.45                  # sombra dentro de la capucha
            if abs(abs(x) - 0.13) < 0.03 and 0.58 < y < 0.76:
                fila.append("|"); continue                          # cordones de la capucha
            if dentro_b and not dentro_c and abs(x) < 0.02 and y > 0.70:
                v = min(v, 0.3)                                     # cremallera
            if y > 0.80:                                            # se deshace en estatica
                v *= max(0.0, 1 - (y - 0.80) / 0.20) if rnd.random() > (y - 0.80) * 3 else 0.0
            i = min(len(RAMPA) - 1, max(0, int(v * (len(RAMPA) - 1) + rnd.uniform(-0.6, 0.6))))
            fila.append(RAMPA[i])
        lineas.append("".join(fila))
    return lineas


if __name__ == "__main__":
    print("\n".join(dibujar()))
