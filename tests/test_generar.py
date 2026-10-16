"""Pruebas del generador de la ficha. Sin red: los datos de la API salen de tests/fixture.json, que lleva
ademas campos personales falsos (CENTINELA) para comprobar que nunca llegan al SVG.
    python3 -m unittest discover -s tests"""
import datetime, json, os, re, sys, tempfile, unittest
import xml.etree.ElementTree as ET

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RAIZ, "perfil"))
import generar  # noqa: E402

HOY = datetime.date(2026, 10, 15)
CRUDO = json.load(open(os.path.join(RAIZ, "tests", "fixture.json"), encoding="utf-8"))
PERFIL = generar.leer_perfil()
CLAVES = ["OS", "Host", "Kernel", "IDE", "Uptime", "Languages.Programming", "Languages.Real", "Hobbies",
          "GitHub", "X", "Repos", "Contributed", "Stars", "Commits", "Lines of Code"]


def todos():
    d = generar.resumen(CRUDO, HOY)
    return {k: generar.svg(d, PERFIL, *k) for k in generar.SALIDAS}


def valores(svg):
    return re.findall(r'<tspan class="valor">([^<]*)</tspan>', svg)


class Numeros(unittest.TestCase):
    def test_salen_de_la_api(self):
        d = generar.resumen(CRUDO, HOY)
        self.assertEqual((d["repos"], d["contribuidos"], d["estrellas"]), (7, 13, 5))
        self.assertEqual((d["commits"], d["suma"], d["resta"]), (321, 123456, 20456))
        for k, s in todos().items():
            v = valores(s)
            for esperado in ("7", "13", "5", "321", "103,000"):
                self.assertIn(esperado, v, (k, esperado))
            self.assertIn('<tspan class="suma">123,456++</tspan>', s)
            self.assertIn('<tspan class="resta">20,456--</tspan>', s)

    def test_lenguajes_por_bytes_sin_marcado(self):
        d = generar.resumen(CRUDO, HOY)
        self.assertEqual(d["lenguajes"], ["TypeScript", "Python", "Luau", "C", "SQL"])   # sin HTML ni CSS, 5 como mucho

    def test_uptime(self):
        self.assertEqual(generar.uptime(datetime.date(2024, 11, 22), HOY), "1 año, 10 meses, 23 días")
        self.assertEqual(generar.uptime(datetime.date(2025, 1, 1), datetime.date(2026, 2, 2)), "1 año, 1 mes, 1 día")
        self.assertEqual(generar.uptime(datetime.date(2026, 1, 31), datetime.date(2026, 3, 1)), "0 años, 1 mes, 1 día")


class Campos(unittest.TestCase):
    def test_no_falta_ninguno(self):
        for k, s in todos().items():
            claves = re.findall(r'<tspan class="clave">([^<]*)</tspan>', s)
            for c in CLAVES:
                self.assertIn(c, claves, (k, c))
            self.assertNotIn("Followers", s)
            self.assertNotIn("987654321", s); self.assertNotIn("987,654,321", s)

    def test_textos_de_perfil_json(self):
        for s in todos().values():
            for clave, variantes in PERFIL.items():
                for v in variantes:
                    for palabra in v.replace(",", " ").replace("·", " ").split():
                        self.assertIn(palabra, s.replace("&amp;", "&"), (clave, v))

    def test_perfil_json_mal_formado(self):
        bien = json.load(open(generar.PERFIL, encoding="utf-8"))
        for malo in ({k: v for k, v in bien.items() if k != "IDE"},
                     {**bien, "Followers": "1"},
                     {**bien, "Kernel": ["a", "b"], "Hobbies": ["a", "b", "c"]},
                     {**bien, "Host": []}):
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
                json.dump(malo, fh)
            with self.assertRaises(ValueError):
                generar.leer_perfil(fh.name)
            os.unlink(fh.name)


class Privacidad(unittest.TestCase):
    def test_no_hay_datos_personales(self):
        for k, s in todos().items():
            for centinela in ("CENTINELA", "centinela", "example.invalid", "avatars"):
                self.assertNotIn(centinela, s, k)
            self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", s), k)          # ningun correo
            self.assertNotIn("<script", s)
            self.assertNotIn("<image", s)                                           # ninguna foto
            self.assertIsNone(re.search(r"(href|src)=", s), k)                      # nada externo

    def test_la_consulta_no_pide_datos_personales(self):
        consulta = re.sub(r"\s+", " ", generar.CAMPOS_API)
        for campo in ("name", "email", "location", "bio", "company", "avatarUrl", "websiteUrl", "twitterUsername",
                      "followers", "socialAccounts", "pronouns", "status"):
            self.assertIsNone(re.search(rf"(?<![\w.]){campo}(?![\w])(?!:)", consulta.replace("name stargazerCount", "")
                                        .replace("node { name }", "")), campo)

    def test_contacto_solo_github_y_x(self):
        self.assertEqual(generar.CONTACTO, [("GitHub", "github.com/itzjk"), ("X", "x.com/Izkszk")])


class Svg(unittest.TestCase):
    def test_valido_y_ligero(self):
        for k, s in todos().items():
            ET.fromstring(s)
            self.assertLess(len(s.encode()), 100_000, k)

    def test_sin_animacion_se_ve_la_variante_a_entera(self):
        """Lo que pinta quien no reproduce SMIL es el atributo: A con su ancho entero, B y C a ancho 0."""
        for k, s in todos().items():
            recortes = re.findall(r'<clipPath id="t(\d+)_(\d+)_(\d+)"><rect class="tecla" [^>]*width="([\d.]+)"', s)
            self.assertTrue(recortes, k)
            for fila, var, linea, ancho in recortes:
                self.assertEqual(float(ancho) > 0, var == "0", (k, fila, var, linea))
            textos_a = re.findall(r'<text class="valor varA" clip-path="url\(#t\d+_0_\d+\)"[^>]*>([^<]*)</text>', s)
            kernel_a = PERFIL["Kernel"][0]
            self.assertIn(kernel_a, " ".join(textos_a).replace("&amp;", "&"))
            self.assertIn("@media (prefers-reduced-motion:reduce)", s)

    def test_el_tecleo_empieza_por_la_a_y_rota(self):
        rot = generar.filas_ficha(generar.resumen(CRUDO, HOY), 60, PERFIL)[1]
        tramo, total = generar.tramos(rot)
        self.assertEqual(len(tramo), 3)
        self.assertEqual(tramo[0][0], 0.0)
        self.assertAlmostEqual(sum(t[2] for t in tramo), total)


class Cache(unittest.TestCase):
    def test_solo_pide_la_historia_de_los_repos_que_cambiaron(self):
        pedidas = []
        usuario = json.loads(json.dumps(CRUDO["user"]))
        usuario["repositories"]["nodes"].append(dict(usuario["repositories"]["nodes"][0], name=generar.LOGIN))

        def falsa(token, consulta, **v):
            if consulta == generar.Q_USUARIO:
                return {"user": usuario}
            pedidas.append(v["name"])
            return {"repository": {"defaultBranchRef": {"target": {"history": {
                "totalCount": 1, "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [{"additions": 10, "deletions": 1}]}}}}}

        original = generar.graphql
        generar.graphql = falsa
        try:
            cache = {"uno": CRUDO["historias"]["uno"], "dos": dict(CRUDO["historias"]["dos"], oid="viejo"), "borrado": {}}
            crudo = generar.leer_api("t", cache)
        finally:
            generar.graphql = original
        self.assertEqual(pedidas, ["dos"])                       # ni "uno" (en cache) ni el repo de la ficha
        self.assertNotIn(generar.LOGIN, crudo["historias"])
        self.assertEqual(crudo["historias"]["uno"], CRUDO["historias"]["uno"])
        self.assertEqual(crudo["historias"]["dos"], dict(oid="b2", commits=1, additions=10, deletions=1))
        self.assertNotIn("borrado", crudo["historias"])


if __name__ == "__main__":
    unittest.main()
