#!/usr/bin/env python3
"""Les tests unitaires du collector REST fomo (scripts/fomo_rest_collector.py),
hors réseau et hors DB de prod.

Couvre : jwt_exp (payload valide/expiré/malformé), read_jwt sur des caches
temporaires (le plus frais des deux gagne, marge exp > now+600), la fenêtre de
fraîcheur fresh() (cadence × 30 min × 0,9), snap/cursor_load/cursor_save sur
sqlite :memory:, le filtre EVM de pre_graduated_mints (mints 0x exclus), le
décapsulage _rows_of (responseObject liste vs dict) et col_token_trades sur
un client factice (walk du feed global — le filtre &tokenAddress= est ignoré
par l'API —, mint = item.tokenAddress, idempotence par item.id, curseur
lastId, cycle neuf, skip de fraîcheur).

    .venv/bin/python -m unittest tests.test_fomo_rest_collector -v
"""
import base64
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fomo_rest_collector as col


def make_jwt(exp: int) -> str:
    """Un JWT factice : seul le segment payload est décodé par jwt_exp."""
    head = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
    pay = base64.urlsafe_b64encode(
        json.dumps({"exp": exp}).encode()).rstrip(b"=").decode()
    return f"{head}.{pay}.sig"


def memory_db() -> sqlite3.Connection:
    """Les tables snapshots + token_trades, même DDL que le collector (main)."""
    con = sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE fomo_rest_snapshots (
                     captured_at INTEGER, endpoint TEXT, entity_id TEXT,
                     data TEXT, PRIMARY KEY (endpoint, entity_id))""")
    con.execute("""CREATE TABLE fomo_rest_token_trades (
                     trade_id TEXT PRIMARY KEY, mint TEXT, user_id TEXT,
                     captured_at INTEGER, data TEXT)""")
    return con


class FakeCli:
    """Client sans réseau ni pacing : pages en file, URLs enregistrées."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.urls = []
        self.n = 0

    def get(self, path):
        self.urls.append(path)
        self.n += 1
        return self.pages.pop(0) if self.pages \
            else {"items": [], "hasNextPage": False}


def feed_item(i: int, mint: str = "MintAAA", **over) -> dict:
    """Un item /feed/tradingActivity réduit aux champs porteurs."""
    it = {"id": f"id-{i}", "tradeId": f"trade-{i}", "tokenAddress": mint,
          "userId": f"user-{i}", "type": "swap_buy",
          "usdAmount": 1000.0 + i, "marketCap": 164623.0,
          "price": 0.000168349, "createdAt": "2026-09-29T20:00:00.000Z"}
    it.update(over)
    return it


class JwtExpTests(unittest.TestCase):
    """Le décodage du payload : exp lisible, tout le reste = 0."""

    def test_payload_valide(self):
        exp = int(time.time()) + 3600
        self.assertEqual(col.jwt_exp(make_jwt(exp)), exp)

    def test_sans_exp_zero(self):
        head = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
        pay = base64.urlsafe_b64encode(b'{"sub":"x"}').rstrip(b"=").decode()
        self.assertEqual(col.jwt_exp(f"{head}.{pay}.sig"), 0)

    def test_malforme_zero(self):
        for bad in ("", "garbage", "a.b", "x.!!!pas-du-base64!.y",
                    "..", f"a.{'z' * 40}.c"):
            self.assertEqual(col.jwt_exp(bad), 0, bad)

    def test_expire_renvoie_son_exp(self):
        """jwt_exp décode : la fraîcheur est décidée par read_jwt, pas lui."""
        past = int(time.time()) - 7200
        self.assertEqual(col.jwt_exp(make_jwt(past)), past)


class ReadJwtTests(unittest.TestCase):
    """Le plus frais des 2 caches temporaires gagne ; marge exp > now + 600."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        for target, value in (("ROOT", self.tmp),
                              ("JWT_CACHE", self.tmp / "ws_jwt_cache.txt")):
            p = mock.patch.object(col, target, value)
            p.start()
            self.addCleanup(p.stop)
        self.json_cache = self.tmp / "data" / "fomo" / "jwt_cache.json"

    def write_txt(self, jwt):
        col.JWT_CACHE.write_text(jwt)

    def write_json(self, jwt, key="jwt"):
        self.json_cache.parent.mkdir(parents=True, exist_ok=True)
        self.json_cache.write_text(json.dumps({key: jwt}))

    def test_txt_frais_gagne(self):
        jwt = make_jwt(int(time.time()) + 3600)
        self.write_txt(jwt)
        self.assertEqual(col.read_jwt(), jwt)

    def test_txt_perime_none(self):
        self.write_txt(make_jwt(int(time.time()) - 100))
        self.assertIsNone(col.read_jwt())

    def test_marge_600s(self):
        """exp = now+500 → périmé ; exp = now+700 → frais."""
        self.write_txt(make_jwt(int(time.time()) + 500))
        self.assertIsNone(col.read_jwt())
        jwt = make_jwt(int(time.time()) + 700)
        self.write_txt(jwt)
        self.assertEqual(col.read_jwt(), jwt)

    def test_json_frais_gagne(self):
        jwt = make_jwt(int(time.time()) + 3600)
        self.write_json(jwt)
        self.assertEqual(col.read_jwt(), jwt)

    def test_json_clef_token(self):
        """Le cache mobula peut porter la clef 'token' au lieu de 'jwt'."""
        jwt = make_jwt(int(time.time()) + 3600)
        self.write_json(jwt, key="token")
        self.assertEqual(col.read_jwt(), jwt)

    def test_mixte_le_plus_frais_gagne(self):
        vieux, frais = make_jwt(int(time.time()) + 1200), \
            make_jwt(int(time.time()) + 7200)
        self.write_txt(vieux)
        self.write_json(frais)
        self.assertEqual(col.read_jwt(), frais)
        # inverse : le txt le plus frais reprend la main
        self.write_txt(frais)
        self.write_json(vieux)
        self.assertEqual(col.read_jwt(), frais)

    def test_mixte_un_seul_frais(self):
        """Un cache périmé ne masque pas l'autre."""
        jwt = make_jwt(int(time.time()) + 3600)
        self.write_txt(make_jwt(int(time.time()) - 50))
        self.write_json(jwt)
        self.assertEqual(col.read_jwt(), jwt)

    def test_les_deux_perimes_none(self):
        self.write_txt(make_jwt(int(time.time()) - 50))
        self.write_json(make_jwt(int(time.time()) - 50))
        self.assertIsNone(col.read_jwt())

    def test_cache_corrompu_saute(self):
        """Un cache illisible ne doit pas masquer l'autre."""
        self.write_txt("{{{ pas du json ni du jwt")
        jwt = make_jwt(int(time.time()) + 3600)
        self.write_json(jwt)
        self.assertEqual(col.read_jwt(), jwt)

    def test_fichiers_absents_none(self):
        self.assertIsNone(col.read_jwt())

    def test_guillemets_decores(self):
        jwt = make_jwt(int(time.time()) + 3600)
        self.write_txt(f'"{jwt}"')
        self.assertEqual(col.read_jwt(), jwt)


class FreshCadenceTests(unittest.TestCase):
    """La fenêtre de skip : cadence × PASS_SECONDS × 0,9 ; cadence 1 = jamais."""

    def setUp(self):
        self.con = memory_db()
        self.addCleanup(self.con.close)

    def test_cadence_1_jamais_frais(self):
        """Cadence 1 = comportement historique : collecte à chaque passe."""
        col.snap(self.con, "feed", "latest", {"a": 1})
        self.assertFalse(col.fresh(self.con, "feed", "latest", 1))
        self.assertFalse(col.fresh(self.con, "feed", "latest", 0))

    def test_sans_ligne_pas_frais(self):
        self.assertFalse(col.fresh(self.con, "verified", "latest", 6))

    def test_snapshot_recent_frais(self):
        col.snap(self.con, "verified", "latest", {"a": 1})
        self.assertTrue(col.fresh(self.con, "verified", "latest", 6))

    def test_bornes_fenetre(self):
        """Frais strictement sous cadence×30×0,9 ; périmé au-delà."""
        fenetre = 6 * col.PASS_SECONDS * 0.9          # 6 × 1800 × 0,9 = 9720 s
        self.con.execute(
            "INSERT INTO fomo_rest_snapshots VALUES (?,?,?,?)",
            (int(time.time() - (fenetre - 60)), "verified", "latest", "{}"))
        self.assertTrue(col.fresh(self.con, "verified", "latest", 6))
        self.con.execute(
            "UPDATE fomo_rest_snapshots SET captured_at=? "
            "WHERE endpoint='verified' AND entity_id='latest'",
            (int(time.time() - (fenetre + 60)),))
        self.assertFalse(col.fresh(self.con, "verified", "latest", 6))

    def test_cle_exacte(self):
        """(endpoint, entity_id) : une autre entité ne compte pas."""
        col.snap(self.con, "verified", "autre", {"a": 1})
        self.assertFalse(col.fresh(self.con, "verified", "latest", 6))


class SnapCursorTests(unittest.TestCase):
    """snap = upsert par (endpoint, entity_id) ; les curseurs roundtrippent."""

    def setUp(self):
        self.con = memory_db()
        self.addCleanup(self.con.close)

    def test_snap_upsert_meme_cle(self):
        col.snap(self.con, "leaderboard", "24h", [1, 2, 3])
        t0 = int(time.time()) - 100
        self.con.execute("UPDATE fomo_rest_snapshots SET captured_at=?",
                         (t0,))
        col.snap(self.con, "leaderboard", "24h", [4, 5])
        rows = self.con.execute(
            "SELECT captured_at, data FROM fomo_rest_snapshots").fetchall()
        self.assertEqual(len(rows), 1)
        captured, data = rows[0]
        self.assertGreater(captured, t0)          # captured_at rafraîchi
        self.assertEqual(json.loads(data), [4, 5])  # data remplacée

    def test_snap_deux_entites(self):
        col.snap(self.con, "verified", "a", [1])
        col.snap(self.con, "verified", "b", [2])
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM fomo_rest_snapshots").fetchone()[0], 2)

    def test_cursor_roundtrip(self):
        col.cursor_save(self.con, "swaps", "uid1", "abc123", 3, False)
        st = col.cursor_load(self.con, "swaps", "uid1")
        self.assertEqual(st["cursor"], "abc123")
        self.assertEqual(st["pages"], 3)
        self.assertFalse(st["exhausted"])
        self.assertIsInstance(st["updated_at"], int)

    def test_cursor_vide(self):
        self.assertEqual(col.cursor_load(self.con, "swaps", "ghost"), {})

    def test_cursor_non_dict(self):
        """Un snapshot non-dict à la place du curseur → {} (pas de crash)."""
        col.snap(self.con, "cursor_swaps_uid1", "uid1", ["pas", "un", "dict"])
        self.assertEqual(col.cursor_load(self.con, "swaps", "uid1"), {})

    def test_cursor_exhausted(self):
        col.cursor_save(self.con, "trades", "uid2", "t9", 2, True)
        st = col.cursor_load(self.con, "trades", "uid2")
        self.assertTrue(st["exhausted"])
        self.assertEqual(st["cursor"], "t9")


class PreGraduatedMintsTests(unittest.TestCase):
    """Le filtre EVM : les mints 0x (faux mints de cotation) sont exclus."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = Path(tmp.name) / "fomo.db"
        con = sqlite3.connect(str(self.db))
        con.execute("CREATE TABLE fomo_pre_graduated "
                    "(mint TEXT, captured_at INTEGER)")
        con.executemany("INSERT INTO fomo_pre_graduated VALUES (?,?)", [
            ("0xevm_recent", 3000),        # le plus récent ET EVM → exclu
            ("So1solana_moyen", 2000),
            ("0xevm_vieux", 1500),
            ("So2solana_vieux", 1000),
            ("So1solana_moyen", 2500),     # doublon : MAX(captured_at) gagne
        ])
        con.commit()
        con.close()
        p = mock.patch.object(col, "FOMO_DB", self.db)
        p.start()
        self.addCleanup(p.stop)

    def test_filtre_evm_et_ordre(self):
        mints = col.pre_graduated_mints(10)
        self.assertEqual(mints, ["So1solana_moyen", "So2solana_vieux"])
        for m in mints:
            self.assertFalse(m.startswith("0x"), m)

    def test_limit(self):
        self.assertEqual(len(col.pre_graduated_mints(1)), 1)

    def test_db_absente_vide(self):
        p = mock.patch.object(col, "FOMO_DB", self.db.parent / "rien.db")
        p.start()
        self.addCleanup(p.stop)
        self.assertEqual(col.pre_graduated_mints(5), [])


class RowsOfTests(unittest.TestCase):
    """Le décapsulage des réponses : {leaderboard:[…]} ou liste brute → lignes."""

    def test_dict_leaderboard(self):
        self.assertEqual(col._rows_of({"leaderboard": [1, 2]}), [1, 2])

    def test_liste_brute(self):
        rows = [1, 2]
        self.assertIs(col._rows_of(rows), rows)

    def test_none_vide(self):
        self.assertEqual(col._rows_of(None), [])

    def test_dict_sans_leaderboard(self):
        self.assertEqual(col._rows_of({"autre": []}), [])


class TokenTradesTests(unittest.TestCase):
    """col_token_trades : &tokenAddress= est IGNORÉ par l'API (sonde du
    29/09) → walk du feed GLOBAL, mint = item.tokenAddress (jamais celui
    demandé), INSERT OR IGNORE par item.id, curseur lastId persisté."""

    def setUp(self):
        self.con = memory_db()
        self.addCleanup(self.con.close)

    def run_col(self, cli, cadence=1):
        return col.col_token_trades(self.con, cli, cadence, {})

    def test_attribution_mint_par_item(self):
        """Le mint vient de l'ITEM : deux tokens dans une même page."""
        page = {"items": [feed_item(1, "MintAAA"), feed_item(2, "MintBBB")],
                "hasNextPage": False}
        self.run_col(FakeCli([page]))
        mints = [r[0] for r in self.con.execute(
            "SELECT mint FROM fomo_rest_token_trades ORDER BY trade_id")]
        self.assertEqual(mints, ["MintAAA", "MintBBB"])
        users = dict(self.con.execute(
            "SELECT trade_id, user_id FROM fomo_rest_token_trades"))
        self.assertEqual(users, {"id-1": "user-1", "id-2": "user-2"})

    def test_data_json_integral(self):
        """data = l'item intégral (MC, fdv, price, equity… au trade)."""
        it = feed_item(7, marketCap=50000.0, price=1e-6, equity=999.0)
        self.run_col(FakeCli([{"items": [it], "hasNextPage": False}]))
        data = self.con.execute(
            "SELECT data FROM fomo_rest_token_trades "
            "WHERE trade_id='id-7'").fetchone()[0]
        self.assertEqual(json.loads(data), it)

    def test_idempotent_append_only(self):
        page = {"items": [feed_item(1), feed_item(2)], "hasNextPage": False}
        self.run_col(FakeCli([page]))
        self.run_col(FakeCli([page]))             # les mêmes items re-servis
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM fomo_rest_token_trades").fetchone()[0], 2)

    def test_pagination_lastid(self):
        """Page 2 = &lastId=<id du dernier item page 1> ; +n = nouveaux."""
        p1 = {"items": [feed_item(i) for i in range(4)], "hasNextPage": True}
        p2 = {"items": [feed_item(10 + i) for i in range(4)],
              "hasNextPage": False}
        cli = FakeCli([p1, p2])
        out = self.run_col(cli)
        self.assertEqual(len(cli.urls), 2)
        self.assertNotIn("lastId", cli.urls[0])
        self.assertIn("lastId=id-3", cli.urls[1])
        self.assertIn("+8", out)

    def test_cycle_neuf_apres_epuisement(self):
        """Flux épuisé → le curseur repart de None à la passe suivante."""
        page = {"items": [feed_item(1)], "hasNextPage": False}
        self.run_col(FakeCli([page]))
        cli2 = FakeCli([page])
        self.run_col(cli2)
        self.assertNotIn("lastId", cli2.urls[0])

    def test_item_sans_id_saute(self):
        page = {"items": [{"tradeId": "t-sans-id"}, feed_item(2)],
                "hasNextPage": False}
        out = self.run_col(FakeCli([page]))
        self.assertEqual(self.con.execute(
            "SELECT COUNT(*) FROM fomo_rest_token_trades"
        ).fetchone()[0], 1)
        self.assertIn("+1", out)

    def test_fraicheur_skip(self):
        """Cadence > 1 et snapshot frais → 0 appel (le garde-fou existe)."""
        col.snap(self.con, "token_trades", "latest", {})
        cli = FakeCli([])
        self.assertIn("skip", self.run_col(cli, cadence=6))
        self.assertEqual(cli.n, 0)


class CollectesTests(unittest.TestCase):
    """La structure déclarative COLLECTES : (nom, cadence, fn), sans doublon."""

    def test_structure(self):
        noms = []
        for nom, cadence, fn in col.COLLECTES:
            self.assertIsInstance(nom, str)
            self.assertIsInstance(cadence, int)
            self.assertGreaterEqual(cadence, 1)
            self.assertTrue(callable(fn))
            noms.append(nom)
        self.assertEqual(len(noms), len(set(noms)))


if __name__ == "__main__":
    unittest.main()
