#!/usr/bin/env python3
"""Le GATE DE SIGNATURE, execute contre un faux GitHub.

## Ce que ce fichier protege

`scripts/ci/verify-github-commit-signature.sh` est le seul controle qui
se trouve entre « un commit est sur main » et « une cle GitLab en
écriture est materialisee ». Si ce script dit oui a tort, n'importe quel
commit non signe est publie sur le miroir ; s'il dit non a tort, le
miroir s'arrete (genant, mais sans danger).

Le sens de l'erreur compte donc : ce script doit etre FAIL-CLOSED.

## Pourquoi des tests d'execution et pas de lecture de source

Les tests de ce fichier lancent le VRAI script contre un serveur HTTP
local qui joue le role de l'API GitHub, et verifient les six champs du
JSON de sortie. Lire le source et chercher la chaine « RATE_LIMITED »
prouverait seulement que la chaine existe — pas qu'elle est produite au
bon moment, ni que le script sort en 1.

Le serveur verifie aussi que la requete est bien un GET sur
`/repos/<repo>/commits/<sha>` avec les en-tetes attendus : un script qui
interrogerait le mauvais point d'API pourrait renvoyer « verified » en
lisant autre chose que la verification de signature.

## Portage

Porte depuis `v2/tests/ci/r169-signature-runtime.test.ts` (1162 lignes,
vitest) d'Ariad. Deux ecarts assumés :

  1. Les tests « pas de fichier temporaire orphelin » ne sont pas portes.
     Ils comptent les fichiers de `$TMPDIR` avant/apres — non
     deterministe sur une machine de developpement partagee. Ils
     resteraient verts par chance ou rouges sans cause.
  2. Le watchdog est un `timeout` de subprocess (le script ne doit jamais
     bloquer), pas un timer en boucle d'evenements.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci" / "verify-github-commit-signature.sh"

MANQUANT = [n for n in ("bash", "curl") if shutil.which(n) is None]


class TestOutilsRequis(unittest.TestCase):
    """En CI, un outil manquant doit ECHOUER, pas faire sauter des tests.

    Un test saute ne compte PAS dans le total : le ratchet verrait 3099
    au lieu de 3140 et accuserait « des tests ont disparu » — en
    designant le mauvais coupable, sans jamais nommer l'outil.
    """

    def test_les_outils_sont_presents_en_ci(self):
        # Pas de `skipTest` ici, expres : un test saute ne compte pas
        # dans le total, donc le compte local et celui de la CI
        # divergeraient — et le ratchet signalerait un ecart fantome.
        if os.environ.get("GITHUB_ACTIONS") != "true":
            return  # hors CI : le skipIf des classes fait foi
        self.assertEqual(MANQUANT, [],
                         f"outils absents en CI : {MANQUANT} — le gate de "
                         f"signature ne peut pas s'executer")

CIBLE = "a" * 40
AUTRE = "b" * 40
TS = "2026-07-13T10:00:00Z"
TS_OFFSET = "2026-07-13T10:00:00+00:00"

A_PURGER = (
    "TARGET_SHA", "GITHUB_API_URL", "GITHUB_REPOSITORY", "GITHUB_TOKEN",
    "OUTPUT_FILE", "SIGNATURE_RETRY_DELAY_SCALE", "CBM_SIGNATURE_TEST_MODE",
    "GITHUB_ACTIONS",
)


# ─────────────────────────────────────────────────────────────────────
# Le faux GitHub
# ─────────────────────────────────────────────────────────────────────

class FauxGitHub:
    """Rend les reponses fournies, dans l'ordre, puis repete la derniere.

    Repeter la derniere est important : un script qui boucle sur une
    erreur persistante doit finir par s'arreter (apres 3 tentatives), et
    le test doit pouvoir compter EXACTEMENT combien de requetes ont ete
    faites. Une liste qui s'epuise masquerait la difference entre
    « 3 tentatives » et « 10 ».
    """

    def __init__(self, reponses: list[dict]):
        self.reponses = reponses
        self.requetes: list[dict] = []
        self._n = 0
        faux = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                faux.requetes.append({
                    "method": self.command,
                    "path": self.path,
                    "headers": {k.lower(): v for k, v in self.headers.items()},
                })
                i = min(faux._n, len(faux.reponses) - 1)
                faux._n += 1
                r = faux.reponses[i]
                corps = r["body"].encode("utf-8")
                self.send_response(r["status"])
                for k, v in {**{"Content-Type": "application/json"},
                             **r.get("headers", {})}.items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(corps)))
                self.end_headers()
                self.wfile.write(corps)

            def log_message(self, *a):
                pass

        self._srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.port = self._srv.server_address[1]
        self._fil = threading.Thread(target=self._srv.serve_forever,
                                     daemon=True)
        self._fil.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._srv.shutdown()
        self._srv.server_close()


# ─────────────────────────────────────────────────────────────────────
# Execution du script
# ─────────────────────────────────────────────────────────────────────

class Sortie:
    def __init__(self, code, stdout, stderr, champs):
        self.code = code
        self.stdout = stdout
        self.stderr = stderr
        self.champs = champs or {}

    def __getitem__(self, k):
        return self.champs.get(k)

    def diagnostic(self) -> str:
        return (f"exit={self.code}\nchamps={json.dumps(self.champs, indent=2)}\n"
                f"--- stdout ---\n{self.stdout[-1500:]}\n"
                f"--- stderr ---\n{self.stderr[-1500:]}")


def _env_propre() -> dict:
    """Aucune variable heritee.

    SIG-R6-TEST-ENV-01 : si on ne retirait que GITHUB_ACTIONS, le test
    « GITHUB_REPOSITORY manquant » heriterait du depot REEL de la CI et
    passerait en vert sans rien tester. C'est un faux positif
    particulierement vicieux : il ne se voit que sur la machine ou la
    variable existe.
    """
    return {k: v for k, v in os.environ.items() if k not in A_PURGER}


def lance(**env_sup) -> Sortie:
    """Execute le script avec EXACTEMENT l'environnement demande."""
    tmp = Path(tempfile.mkdtemp(prefix="sig-gate-"))
    try:
        sortie = tmp / "outputs.json"
        env = _env_propre()
        env.update({
            "OUTPUT_FILE": str(sortie),
            "SIGNATURE_RETRY_DELAY_SCALE": "0",
            "CBM_SIGNATURE_TEST_MODE": "1",
            **env_sup,
        })
        r = subprocess.run(["bash", str(SCRIPT)], env=env,
                           capture_output=True, text=True, timeout=60)
        champs = None
        if sortie.exists():
            try:
                champs = json.loads(sortie.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                champs = None
        return Sortie(r.returncode, r.stdout, r.stderr, champs)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def sur_serveur(faux: FauxGitHub, cible: str = CIBLE) -> Sortie:
    return lance(TARGET_SHA=cible, GITHUB_API_URL=faux.url,
                 GITHUB_REPOSITORY="test/repo", GITHUB_TOKEN="fake-token")


# ─────────────────────────────────────────────────────────────────────
# Corps de reponse : le VRAI contrat de l'API GitHub
# ─────────────────────────────────────────────────────────────────────

def corps_valide(sha: str = CIBLE, ts: str = TS) -> str:
    """Succes : signature/payload/verified_at sont des CHAINES."""
    return json.dumps({"sha": sha, "commit": {"verification": {
        "verified": True, "reason": "valid", "signature": "pgp-sig",
        "payload": "payload", "verified_at": ts}}})


def corps_refus(reason: str, ts=None, sha: str = CIBLE) -> str:
    """Refus : signature=null, payload=null — c'est ce que renvoie GitHub.

    Le `verified_at: null` est le point subtil : un script naif le
    recopierait tel quel dans sa sortie JSON, et le workflow lirait la
    chaine "None" ou "null" comme un horodatage valide.
    """
    return json.dumps({"sha": sha, "commit": {"verification": {
        "verified": False, "reason": reason, "signature": None,
        "payload": None, "verified_at": ts}}})


@unittest.skipIf(MANQUANT, f"outils absents : {', '.join(MANQUANT)}")
class BaseGate(unittest.TestCase):

    def verifie(self, cond, s: Sortie, msg=""):
        if not cond:
            self.fail(f"{msg}\n{s.diagnostic()}")

    def attend(self, s: Sortie, code: int, categorie: str, essais: str,
               msg=""):
        self.verifie(s.code == code, s,
                     f"{msg}\nexit attendu {code}")
        self.verifie(s["error_category"] == categorie, s,
                     f"{msg}\ncategorie attendue {categorie}")
        self.verifie(s["attempts"] == essais, s,
                     f"{msg}\nessais attendus {essais}")


class TestFichier(unittest.TestCase):

    def test_le_script_existe_et_est_executable(self):
        self.assertTrue(SCRIPT.exists())
        self.assertTrue(os.access(SCRIPT, os.X_OK))


class TestSucces(BaseGate):
    """Ce qui doit PASSER — et le format exact de la sortie."""

    def test_signature_valide(self):
        with FauxGitHub([{"status": 200, "body": corps_valide()}]) as f:
            s = sur_serveur(f)
        self.verifie(s.code == 0, s, "une signature valide doit passer")
        self.verifie(s.champs.get("verified") == "true", s)
        self.verifie(s.champs.get("reason") == "valid", s)
        self.verifie(s.champs.get("api_sha") == CIBLE, s)
        self.verifie(s.champs.get("error_category") == "none", s)
        self.verifie(s.champs.get("attempts") == "1", s)
        self.verifie(s.champs.get("verified_at") == TS, s)

    def test_horodatage_avec_decalage_explicite(self):
        """`+00:00` doit etre accepte au meme titre que `Z`."""
        with FauxGitHub([{"status": 200,
                          "body": corps_valide(ts=TS_OFFSET)}]) as f:
            s = sur_serveur(f)
        self.verifie(s.code == 0, s)
        self.verifie(s.champs.get("verified_at") == TS_OFFSET, s,
                     "l'horodatage doit etre recopie SANS reecriture")

    def test_429_puis_valide(self):
        with FauxGitHub([
            {"status": 429, "body": "{}"},
            {"status": 200, "body": corps_valide()},
        ]) as f:
            s = sur_serveur(f)
        self.verifie(s.code == 0, s, "un 429 transitoire doit etre reessaye")
        self.verifie(s.champs.get("verified") == "true", s)
        self.verifie(s.champs.get("attempts") == "2", s)

    def test_429_avec_retry_after_court(self):
        with FauxGitHub([
            {"status": 429, "body": "{}", "headers": {"Retry-After": "1"}},
            {"status": 200, "body": corps_valide()},
        ]) as f:
            s = sur_serveur(f)
        self.verifie(s.code == 0, s)
        self.verifie(s.champs.get("attempts") == "2", s)

    def test_403_limite_secondaire_puis_valide(self):
        with FauxGitHub([
            {"status": 403, "body": json.dumps(
                {"message": "You have exceeded a secondary rate limit"})},
            {"status": 200, "body": corps_valide()},
        ]) as f:
            s = sur_serveur(f)
        self.verifie(s.code == 0, s)
        self.verifie(s.champs.get("attempts") == "2", s)

    def test_gpgverify_unavailable_puis_valide(self):
        """Une panne du verificateur de GitHub n'est pas un refus."""
        with FauxGitHub([
            {"status": 200, "body": corps_refus("gpgverify_unavailable",
                                                ts=None)},
            {"status": 200, "body": corps_valide()},
        ]) as f:
            s = sur_serveur(f)
        self.verifie(s.code == 0, s,
                     "une erreur transitoire du verificateur GitHub ne doit "
                     "pas disqualifier un commit")
        self.verifie(s.champs.get("attempts") == "2", s)


class TestRefus(BaseGate):
    """Ce qui doit ÉCHOUER — et pourquoi le nom de la categorie compte."""

    def test_non_signe(self):
        with FauxGitHub([{"status": 200,
                          "body": corps_refus("unsigned", ts=None)}]) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_UNSIGNED", "1")
        self.verifie(s.champs.get("verified") == "false", s)
        self.verifie(s.champs.get("reason") == "unsigned", s)
        self.verifie(s.champs.get("api_sha") == CIBLE, s)
        self.verifie(s.champs.get("verified_at") == "", s,
                     "un verified_at a null doit devenir une chaine VIDE, "
                     "jamais le texte 'null' ou 'None' — le workflow lit "
                     "ce champ comme une date")

    def test_signature_invalide(self):
        with FauxGitHub([{"status": 200,
                          "body": corps_refus("invalid", ts=None)}]) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_INVALID", "1")
        self.verifie(s.champs.get("verified_at") == "", s)

    def test_signature_malformee(self):
        with FauxGitHub([{"status": 200, "body": corps_refus(
                "malformed_signature", ts=None)}]) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_INVALID", "1")

    def test_cle_inconnue(self):
        with FauxGitHub([{"status": 200,
                          "body": corps_refus("unknown_key", ts=None)}]) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_UNVERIFIED", "1")

    def test_sha_different(self):
        """L'API repond « valide » mais pour un AUTRE commit.

        C'est le scenario de la substitution : on presente un commit
        signe par quelqu'un d'autre en esperant que le gate ne compare
        pas le sha retourne a celui demande.
        """
        with FauxGitHub([{"status": 200,
                          "body": corps_valide(sha=AUTRE)}]) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_SHA_MISMATCH", "1")
        self.verifie(s.champs.get("api_sha") == AUTRE, s,
                     "le sha REEL doit apparaitre dans le diagnostic")
        self.verifie(s.champs.get("reason") == "valid", s)
        self.verifie(s.champs.get("verified_at") == TS, s)

    def test_coherence_verifie_mais_raison_non_valide(self):
        with FauxGitHub([{"status": 200, "body": json.dumps(
                {"sha": CIBLE, "commit": {"verification": {
                    "verified": True, "reason": "unsigned",
                    "signature": "s", "payload": "p",
                    "verified_at": TS}}})}]) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_API_SCHEMA_ERROR", "1",
                    "verified=true avec reason=unsigned est incoherent : "
                    "le script ne doit pas choisir lequel croire")

    def test_coherence_non_verifie_mais_raison_valide(self):
        with FauxGitHub([{"status": 200, "body": json.dumps(
                {"sha": CIBLE, "commit": {"verification": {
                    "verified": False, "reason": "valid",
                    "signature": "s", "payload": "p",
                    "verified_at": TS}}})}]) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_API_SCHEMA_ERROR", "1")

    def test_raison_hors_enumeration(self):
        """Une raison inconnue ne doit jamais passer — sur les DEUX branches.

        Le piege de ce test : poser `verified: true` avec une raison
        inconnue ne prouve RIEN sur l'enumeration, parce que le controle
        de coherence (« verified=true exige reason=valid ») refuse avant.
        Une mutation qui supprime l'enumeration survit alors au test, qui
        a l'air de la couvrir.

        C'est `verified: false` + raison inconnue qui isole vraiment
        l'enumeration : la coherence est satisfaite, et seul le controle
        d'enumeration peut refuser.
        """
        for verifie in (True, False):
            with self.subTest(verified=verifie):
                with FauxGitHub([{"status": 200, "body": json.dumps(
                        {"sha": CIBLE, "commit": {"verification": {
                            "verified": verifie, "reason": "trust-me-bro",
                            "signature": "s", "payload": "p",
                            "verified_at": TS}}})}]) as f:
                    s = sur_serveur(f)
                self.attend(
                    s, 1, "GITHUB_SIGNATURE_API_SCHEMA_ERROR", "1",
                    "une raison inconnue doit etre refusee : l'enumeration "
                    "est ce qui empeche une valeur FUTURE de GitHub "
                    "(ou fabriquee) de passer pour un verdict lisible")

    def test_gpgverify_error_est_transitoire_et_retente(self):
        with FauxGitHub([{"status": 200, "body": corps_refus(
                "gpgverify_error", ts=None)}] * 3) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_TRANSIENT_VERIFIER_ERROR", "3")
        self.verifie(s.champs.get("verified_at") == "", s)


class TestErreursHTTP(BaseGate):
    """Le script doit distinguer « reessaie » de « n'insiste pas »."""

    def test_500_est_retente_trois_fois(self):
        with FauxGitHub([{"status": 500, "body": "{}"}]) as f:
            s = sur_serveur(f)
            n = len(f.requetes)
        self.attend(s, 1, "GITHUB_SIGNATURE_API_HTTP_ERROR", "3")
        self.assertEqual(n, 3, "500 doit etre retente exactement 3 fois")

    def test_502_503_504_sont_retentes(self):
        for code in (502, 503, 504):
            with self.subTest(status=code):
                with FauxGitHub([{"status": code, "body": "{}"}]) as f:
                    s = sur_serveur(f)
                self.verifie(s.code == 1, s)
                self.verifie(s.champs.get("attempts") == "3", s)

    def test_429_permanent_finit_en_rate_limited(self):
        with FauxGitHub([{"status": 429, "body": "{}"}]) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_API_RATE_LIMITED", "3")

    def test_401_et_404_ne_sont_pas_retentes(self):
        """Un token invalide ou un sha absent ne s'arrangent pas en attendant."""
        for code in (401, 404):
            with self.subTest(status=code):
                with FauxGitHub([{"status": code, "body": "{}"}]) as f:
                    s = sur_serveur(f)
                    n = len(f.requetes)
                self.attend(s, 1, "GITHUB_SIGNATURE_API_HTTP_ERROR", "1")
                self.assertEqual(n, 1, f"{code} ne doit PAS etre retente")

    def test_403_non_rate_limit_nest_pas_retente(self):
        with FauxGitHub([{"status": 403, "body": json.dumps(
                {"message": "Forbidden"})}]) as f:
            s = sur_serveur(f)
            n = len(f.requetes)
        self.attend(s, 1, "GITHUB_SIGNATURE_API_HTTP_ERROR", "1")
        self.assertEqual(n, 1)

    def test_403_quota_epuise_echoue_sans_retenter(self):
        """SIG-R4-RATE-01 : quota primaire a zero = inutile d'insister."""
        with FauxGitHub([{"status": 403, "body": "{}",
                          "headers": {"x-ratelimit-remaining": "0"}}]) as f:
            s = sur_serveur(f)
            n = len(f.requetes)
        self.attend(s, 1, "GITHUB_SIGNATURE_API_RATE_LIMITED", "1")
        self.assertEqual(n, 1, "un quota epuise ne se recharge pas en "
                               "quelques secondes")

    def test_429_retry_after_trop_long_echoue_sans_attendre(self):
        """SIG-R4-RATE-01 : attendre 60 s depasserait le budget du job."""
        with FauxGitHub([{"status": 429, "body": "{}",
                          "headers": {"Retry-After": "60"}}]) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_API_RATE_LIMITED", "1")


class TestSchema(BaseGate):
    """Un schema inattendu ne doit JAMAIS passer pour un succes."""

    def test_json_malforme_sans_retry(self):
        with FauxGitHub([{"status": 200, "body": "{not valid json"}]) as f:
            s = sur_serveur(f)
            n = len(f.requetes)
        self.attend(s, 1, "GITHUB_SIGNATURE_API_MALFORMED_JSON", "1")
        self.assertEqual(n, 1, "un JSON casse ne se repare pas en "
                               "redemandant")

    def test_verification_absente(self):
        with FauxGitHub([{"status": 200, "body": json.dumps(
                {"sha": CIBLE, "commit": {}})}]) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_API_SCHEMA_ERROR", "1")

    def test_verified_at_absent(self):
        with FauxGitHub([{"status": 200, "body": json.dumps(
                {"sha": CIBLE, "commit": {"verification": {
                    "verified": True, "reason": "valid",
                    "signature": "s", "payload": "p"}}})}]) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_API_SCHEMA_ERROR", "1")

    def test_verified_at_non_analysable(self):
        """SIG-R3-TIME-01 : le champ doit etre une date ISO 8601 COMPLETE.

        Une date tronquee est le piege classique : elle « ressemble » a
        un horodatage et se fait recopier dans le rapport, ou elle
        devient un `1970-01-01` silencieux.
        """
        for mauvais in ("foo", "2026", "2026-07-13T10:00:00", "2026-07-13"):
            with self.subTest(verified_at=mauvais):
                with FauxGitHub([{"status": 200, "body": json.dumps(
                        {"sha": CIBLE, "commit": {"verification": {
                            "verified": True, "reason": "valid",
                            "signature": "s", "payload": "p",
                            "verified_at": mauvais}}})}]) as f:
                    s = sur_serveur(f)
                self.attend(s, 1, "GITHUB_SIGNATURE_API_SCHEMA_ERROR", "1")

    def test_verified_de_mauvais_type(self):
        with FauxGitHub([{"status": 200, "body": json.dumps(
                {"sha": CIBLE, "commit": {"verification": {
                    "verified": "true", "reason": "valid",
                    "signature": "s", "payload": "p",
                    "verified_at": TS}}})}]) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_API_SCHEMA_ERROR", "1",
                    "la chaine 'true' n'est pas le booleen true")

    def test_reason_de_mauvais_type(self):
        with FauxGitHub([{"status": 200, "body": json.dumps(
                {"sha": CIBLE, "commit": {"verification": {
                    "verified": True, "reason": 42,
                    "signature": "s", "payload": "p",
                    "verified_at": TS}}})}]) as f:
            s = sur_serveur(f)
        self.attend(s, 1, "GITHUB_SIGNATURE_API_SCHEMA_ERROR", "1")


class TestConfiguration(BaseGate):
    """Les erreurs de configuration sortent en 2, AVANT tout appel reseau.

    La distinction exit 1 / exit 2 n'est pas cosmetique : elle separe
    « ce commit n'est pas publiabe » (attendu, diagnosticable) de « le
    job est mal configure » (a corriger dans les reglages). Les
    confondre enverrait l'operateur chercher un probleme de signature
    qui n'existe pas.
    """

    def _attend_config(self, s: Sortie, msg=""):
        self.attend(s, 2, "GITHUB_SIGNATURE_CONFIG_ERROR", "0", msg)

    def test_target_sha_manquant(self):
        s = lance(GITHUB_API_URL="http://127.0.0.1:1",
                  GITHUB_REPOSITORY="test/repo", GITHUB_TOKEN="t")
        self._attend_config(s)

    def test_target_sha_malforme(self):
        s = lance(TARGET_SHA="abc123", GITHUB_API_URL="http://127.0.0.1:1",
                  GITHUB_REPOSITORY="test/repo", GITHUB_TOKEN="t")
        self._attend_config(s)

    def test_token_manquant(self):
        s = lance(TARGET_SHA=CIBLE, GITHUB_API_URL="http://127.0.0.1:1",
                  GITHUB_REPOSITORY="test/repo")
        self._attend_config(s)

    def test_api_url_manquante(self):
        s = lance(TARGET_SHA=CIBLE, GITHUB_REPOSITORY="test/repo",
                  GITHUB_TOKEN="t")
        self._attend_config(s)

    def test_repository_manquant(self):
        s = lance(TARGET_SHA=CIBLE, GITHUB_API_URL="http://127.0.0.1:1",
                  GITHUB_TOKEN="t")
        self._attend_config(s)

    def test_mode_test_refuse_une_url_non_locale(self):
        """Le mode test ne doit pas pouvoir viser le vrai GitHub.

        Sans ce refus, une variable d'environnement suffirait a faire
        interroger une API choisie par l'attaquant — et a obtenir un
        « verified » fabrique.
        """
        s = lance(TARGET_SHA=CIBLE, GITHUB_API_URL="https://api.github.com",
                  GITHUB_REPOSITORY="test/repo", GITHUB_TOKEN="t")
        self._attend_config(s, "une API non-loopback doit etre refusee")

    def test_github_actions_desactive_le_mode_test(self):
        """SIG-R3-CI-01 : deuxieme verrou, independant du premier.

        En CI, la variable GITHUB_ACTIONS vaut "true" : meme si le mode
        test etait active et l'URL loopback, le script doit refuser. Ce
        test couvre le cas ou la verification d'URL serait contournee.
        """
        s = lance(TARGET_SHA=CIBLE, GITHUB_API_URL="http://127.0.0.1:1",
                  GITHUB_REPOSITORY="test/repo", GITHUB_TOKEN="t",
                  GITHUB_ACTIONS="true")
        self._attend_config(s, "GITHUB_ACTIONS=true doit interdire le "
                               "mode test, meme sur une URL loopback")

    def test_echelle_de_retry_invalide(self):
        """SIG-R3-RETRY-02 : seule 0 est admise, et seulement en test."""
        s = lance(TARGET_SHA=CIBLE, GITHUB_API_URL="http://127.0.0.1:1",
                  GITHUB_REPOSITORY="test/repo", GITHUB_TOKEN="t",
                  SIGNATURE_RETRY_DELAY_SCALE="2")
        self._attend_config(s)

    def test_echelle_zero_refusee_en_production(self):
        """scale=0 hors mode test supprimerait toute attente entre retries.

        C'est une valeur de TEST : l'utiliser en production martelerait
        l'API GitHub et se ferait rate-limiter pour de bon.
        """
        env = _env_propre()
        env.update({
            "TARGET_SHA": CIBLE,
            "GITHUB_API_URL": "https://api.github.com",
            "GITHUB_REPOSITORY": "test/repo",
            "GITHUB_TOKEN": "t",
            "SIGNATURE_RETRY_DELAY_SCALE": "0",
        })
        env.pop("OUTPUT_FILE", None)
        tmp = Path(tempfile.mkdtemp(prefix="sig-prod-"))
        try:
            env["OUTPUT_FILE"] = str(tmp / "o.json")
            r = subprocess.run(["bash", str(SCRIPT)], env=env,
                               capture_output=True, text=True, timeout=60)
            self.assertEqual(r.returncode, 2,
                             f"exit attendu 2 (config)\n{r.stderr[-800:]}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class TestErreurReseau(BaseGate):

    def test_connexion_refusee_est_retentee(self):
        # Un port libre, immediatement ferme : rien n'ecoute.
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        res = lance(TARGET_SHA=CIBLE, GITHUB_API_URL=f"http://127.0.0.1:{port}",
                    GITHUB_REPOSITORY="test/repo", GITHUB_TOKEN="t")
        self.attend(res, 1, "GITHUB_SIGNATURE_API_NETWORK_ERROR", "3")


class TestFormeDeLaRequete(BaseGate):
    """Un « verified » n'a de sens que si on a interroge LE BON endroit.

    Ces controles portent sur la requete reellement emise, pas sur le
    resultat : c'est le seul moyen de detecter un script qui lirait la
    verification d'un autre commit, ou qui presenterait un token de
    travers.
    """

    def test_methode_chemin_et_entetes(self):
        with FauxGitHub([{"status": 200, "body": corps_valide()}]) as f:
            sur_serveur(f)
            self.assertEqual(len(f.requetes), 1)
            q = f.requetes[0]
        self.assertEqual(q["method"], "GET")
        self.assertEqual(q["path"], f"/repos/test/repo/commits/{CIBLE}",
                         "le chemin doit viser le sha DEMANDE")
        self.assertEqual(q["headers"].get("authorization"),
                         "Bearer fake-token")
        self.assertIn("application/vnd.github+json",
                      q["headers"].get("accept", ""))
        self.assertEqual(q["headers"].get("x-github-api-version"),
                         "2026-03-10",
                         "une version d'API figee evite qu'un changement "
                         "cote GitHub modifie le contrat de verification "
                         "sans que personne ne le voie")

    def test_nombre_de_requetes_par_scenario(self):
        """Le compte de tentatives doit etre EXACT, pas « au moins »."""
        for reponses, attendu, nom in (
            ([{"status": 200, "body": corps_valide()}], 1, "succes"),
            ([{"status": 429, "body": "{}"},
              {"status": 200, "body": corps_valide()}], 2, "429 puis succes"),
            ([{"status": 500, "body": "{}"}], 3, "500 permanent"),
            ([{"status": 401, "body": "{}"}], 1, "401 sans retry"),
            ([{"status": 200, "body": "{casse"}], 1, "JSON casse"),
        ):
            with self.subTest(scenario=nom):
                with FauxGitHub(reponses) as f:
                    sur_serveur(f)
                    self.assertEqual(len(f.requetes), attendu, nom)


if __name__ == "__main__":
    unittest.main()
