"""Tests for the card generator. Offline: API data comes from tests/fixture.json, which also carries fake
personal fields (SENTINEL) to check they never reach the SVG.
    python3 -m unittest discover -s tests"""
import datetime, json, os, re, sys, tempfile, unittest
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))
import generate  # noqa: E402
import ghost  # noqa: E402

TODAY = datetime.date(2026, 10, 15)
RAW = json.load(open(os.path.join(ROOT, "tests", "fixture.json"), encoding="utf-8"))
PROFILE = generate.read_profile()
KEYS = ["OS", "Host", "Kernel", "IDE", "Uptime", "Languages.Programming", "Languages.Real", "Hobbies",
        "GitHub", "X", "Repos", "Contributed", "Stars", "Commits", "Lines of Code"]
# Spanish that must never show up in what the repo publishes (the card, the workflow, the README)
SPANISH = ["año", "años", "mes", "meses", "día", "días", "datos", "ficha", "perfil", "fantasma", "pruebas",
           "generar", "capturas", "oscuro", "claro", "móvil", "movil", "cambio", "cambios", "sin", "solo", "del",
           "para", "hoy", "Español", "Inglés", "Francés", "Uptime de"]


def cards():
    d = generate.summary(RAW, TODAY)
    return {k: generate.svg(d, PROFILE, *k) for k in generate.OUTPUTS}


def values(svg):
    return re.findall(r'<tspan class="value">([^<]*)</tspan>', svg)


def visible_text(svg):
    """Text a person can read: the contents of <text>/<tspan>/<title>, without markup or attributes."""
    return " ".join(re.findall(r">([^<>]+)<", re.sub(r"<style>.*?</style>", "", svg, flags=re.S)))


class Numbers(unittest.TestCase):
    def test_come_from_the_api(self):
        d = generate.summary(RAW, TODAY)
        self.assertEqual((d["repos"], d["contributed"], d["stars"]), (7, 13, 5))
        self.assertEqual((d["commits"], d["additions"], d["deletions"]), (321, 123456, 20456))
        for k, s in cards().items():
            v = values(s)
            for expected in ("7", "13", "5", "321", "103,000"):
                self.assertIn(expected, v, (k, expected))
            self.assertIn('<tspan class="add">123,456++</tspan>', s)
            self.assertIn('<tspan class="del">20,456--</tspan>', s)

    def test_languages_by_bytes_without_markup(self):
        self.assertEqual(generate.summary(RAW, TODAY)["languages"], ["TypeScript", "Python", "Luau", "C", "SQL"])

    def test_uptime_in_english(self):
        self.assertEqual(generate.uptime(datetime.date(2024, 11, 22), TODAY), "1 year, 10 months, 23 days")
        self.assertEqual(generate.uptime(datetime.date(2025, 1, 1), datetime.date(2026, 2, 2)), "1 year, 1 month, 1 day")
        self.assertEqual(generate.uptime(datetime.date(2026, 1, 31), datetime.date(2026, 3, 1)), "0 years, 1 month, 1 day")
        self.assertEqual(generate.uptime(datetime.date(2023, 3, 3), datetime.date(2026, 3, 3)), "3 years, 0 months, 0 days")


class Fields(unittest.TestCase):
    def test_none_missing(self):
        for k, s in cards().items():
            keys = re.findall(r'<tspan class="key">([^<]*)</tspan>', s)
            for c in KEYS:
                self.assertIn(c, keys, (k, c))
            self.assertNotIn("Followers", s)
            self.assertNotIn("987654321", s); self.assertNotIn("987,654,321", s)

    def test_profile_texts(self):
        for s in cards().values():
            text = s.replace("&amp;", "&")
            for key, variants in PROFILE.items():
                for v in variants:
                    for word in v.replace(",", " ").replace("·", " ").split():
                        self.assertIn(word, text, (key, v))

    def test_bad_profile_json(self):
        good = json.load(open(generate.PROFILE, encoding="utf-8"))
        for bad in ({k: v for k, v in good.items() if k != "IDE"},
                    {**good, "Followers": "1"},
                    {**good, "Kernel": ["a", "b"], "Hobbies": ["a", "b", "c"]},
                    {**good, "Host": []}):
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
                json.dump(bad, fh)
            with self.assertRaises(ValueError):
                generate.read_profile(fh.name)
            os.unlink(fh.name)


class English(unittest.TestCase):
    def check(self, name, text):
        for w in SPANISH:
            self.assertIsNone(re.search(rf"(?<![\w]){re.escape(w)}(?![\w])", text, re.I), f"{name}: '{w}'")

    def test_cards_are_english(self):
        for k, s in cards().items():
            self.check(str(k), visible_text(s))

    def test_published_files_are_english(self):
        for rel in (".github/workflows/card.yml", "README.md", "profile.json"):
            self.check(rel, open(os.path.join(ROOT, rel), encoding="utf-8").read())

    def test_the_check_catches_spanish(self):
        with self.assertRaises(AssertionError):
            self.check("example", "1 año, 10 meses")


class Privacy(unittest.TestCase):
    def test_no_personal_data(self):
        for k, s in cards().items():
            for sentinel in ("SENTINEL", "sentinel", "example.invalid", "avatars"):
                self.assertNotIn(sentinel, s, k)
            self.assertIsNone(re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", s), k)          # no email
            self.assertNotIn("<script", s)
            self.assertNotIn("<image", s)                                           # no photo
            self.assertIsNone(re.search(r"(?<!xlink:)(?<![\w-])(src|href)=\"(?!#)", s), k)   # nothing external

    def test_query_asks_for_nothing_personal(self):
        q = re.sub(r"\s+", " ", generate.USER_FIELDS).replace("name stargazerCount", "").replace("node { name }", "")
        for field in ("name", "email", "location", "bio", "company", "avatarUrl", "websiteUrl", "twitterUsername",
                      "followers", "socialAccounts", "pronouns", "status"):
            self.assertIsNone(re.search(rf"(?<![\w.]){field}(?!\w)", q), field)

    def test_contact_only_github_and_x(self):
        self.assertEqual(generate.CONTACT, [("GitHub", "github.com/itzjk"), ("X", "x.com/Izkszk")])


class Figure(unittest.TestCase):
    def test_hooded_figure_with_a_profile_and_no_face(self):
        rows = ghost.draw()
        self.assertEqual((len(rows), len(rows[0])), (ghost.ROWS, ghost.COLS))
        self.assertTrue(all(len(r) == ghost.COLS for r in rows))
        rim = sum(k == "rim" and ch != " " for r in rows for ch, k in r)
        self.assertGreater(rim, 40)                            # lit edges: hood lip, profile, back
        # under the hood, in front of the profile, it is dark: no features drawn there
        for py in range(140, 220, 8):
            edge = ghost._profile_x(py)
            for px in range(int(edge) + 8, 250, 6):
                if ghost._opening(px, py) < 0.9:
                    self.assertEqual(ghost.intensity(px, py, __import__("random").Random(0))[0], 0.0, (px, py))

    def test_same_seed_same_drawing(self):
        self.assertEqual(ghost.as_text(), ghost.as_text())


class Svg(unittest.TestCase):
    def test_valid_and_light(self):
        for k, s in cards().items():
            ET.fromstring(s)
            self.assertLess(len(s.encode()), 100_000, k)

    def test_without_animation_variant_a_is_whole(self):
        """What a renderer without SMIL paints is the attribute: A at full width, B and C at width 0."""
        for k, s in cards().items():
            clips = re.findall(r'<clipPath id="t(\d+)_(\d+)_(\d+)"><rect class="typing" [^>]*width="([\d.]+)"', s)
            self.assertTrue(clips, k)
            for row, var, line, width in clips:
                self.assertEqual(float(width) > 0, var == "0", (k, row, var, line))
            a = re.findall(r'<text class="value varA" clip-path="url\(#t\d+_0_\d+\)"[^>]*>([^<]*)</text>', s)
            self.assertIn(PROFILE["Kernel"][0], " ".join(a).replace("&amp;", "&"))
            self.assertIn("@media (prefers-reduced-motion:reduce)", s)

    def test_typing_starts_with_a_and_rotates(self):
        rot = generate.card_rows(generate.summary(RAW, TODAY), 60, PROFILE)[1]
        slot, total = generate.slots(rot)
        self.assertEqual(len(slot), 3)
        self.assertEqual(slot[0][0], 0.0)
        self.assertAlmostEqual(sum(s[2] for s in slot), total)


class Cache(unittest.TestCase):
    def test_only_fetches_history_of_repos_that_moved(self):
        asked = []
        user = json.loads(json.dumps(RAW["user"]))
        user["repositories"]["nodes"].append(dict(user["repositories"]["nodes"][0], name=generate.LOGIN))

        def fake(token, query, **v):
            if query == generate.Q_USER:
                return {"user": user}
            asked.append(v["name"])
            return {"repository": {"defaultBranchRef": {"target": {"history": {
                "totalCount": 1, "pageInfo": {"hasNextPage": False, "endCursor": None},
                "nodes": [{"additions": 10, "deletions": 1}]}}}}}

        original = generate.graphql
        generate.graphql = fake
        try:
            cache = {"one": RAW["histories"]["one"], "two": dict(RAW["histories"]["two"], oid="old"), "gone": {}}
            raw = generate.read_api("t", cache)
        finally:
            generate.graphql = original
        self.assertEqual(asked, ["two"])                          # not "one" (cached) nor this card's repo
        self.assertNotIn(generate.LOGIN, raw["histories"])
        self.assertEqual(raw["histories"]["one"], RAW["histories"]["one"])
        self.assertEqual(raw["histories"]["two"], dict(oid="b2", commits=1, additions=10, deletions=1))
        self.assertNotIn("gone", raw["histories"])


if __name__ == "__main__":
    unittest.main()
