from __future__ import annotations

import os
import sys
import asyncio
import unittest
from pathlib import Path

from starlette.requests import Request
from starlette.responses import Response


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import main  # noqa: E402


def _request(
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
    method: str = "GET",
) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/api/test",
            "query_string": query_string,
            "headers": headers or [(b"host", b"100.114.51.121:8000")],
            "client": ("100.114.51.121", 4242),
            "server": ("100.114.51.121", 8000),
            "scheme": "http",
        }
    )


def _local_request(headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/test",
            "query_string": b"",
            "headers": headers or [(b"host", b"127.0.0.1:8000")],
            "client": ("127.0.0.1", 4242),
            "server": ("127.0.0.1", 8000),
            "scheme": "http",
        }
    )


class PrivateAccessSecurityTests(unittest.TestCase):
    def test_access_token_query_param_is_not_accepted(self) -> None:
        request = _request(query_string=b"access_token=super-secret")

        self.assertEqual(main._request_token(request), "")

    def test_access_token_cookie_is_still_accepted(self) -> None:
        request = _request(headers=[(b"host", b"100.114.51.121:8000"), (b"cookie", b"core_access=super-secret")])

        self.assertEqual(main._request_token(request), "super-secret")

    def test_env_status_never_returns_secret_prefixes(self) -> None:
        old_key = os.environ.get("FIRECRAWL_API_KEY")
        os.environ["FIRECRAWL_API_KEY"] = "fc-sensitive-token"
        try:
            status = main.env_status()
        finally:
            if old_key is None:
                os.environ.pop("FIRECRAWL_API_KEY", None)
            else:
                os.environ["FIRECRAWL_API_KEY"] = old_key

        self.assertEqual(status["FIRECRAWL_API_KEY"], "SET")
        self.assertNotIn("fc-", str(status))
        self.assertNotIn("sensitive", str(status))

    def test_public_security_status_does_not_disclose_network_map(self) -> None:
        status = main.security_status(_request())

        self.assertIn("allowed_origins_configured", status)
        self.assertIn("allowed_hosts_configured", status)
        self.assertNotIn("allowed_origins", status)
        self.assertNotIn("allowed_hosts", status)

    def test_sensitive_local_control_routes_require_admin_access(self) -> None:
        protected_paths = [
            "/api/desktop/screenshot",
            "/api/vision/agent",
            "/api/agents/run",
            "/api/chat/message",
            "/api/intel/investigate",
            "/api/arkham/scrapling/probe",
            "/api/arkham/db/stats",
            "/api/market/mt5/account",
            "/api/market/ninjatrader",
        ]

        for path in protected_paths:
            with self.subTest(path=path):
                self.assertTrue(main._requires_admin_access("POST", path))

        self.assertFalse(main._requires_admin_access("GET", "/api/market/prices"))
        self.assertTrue(main._requires_admin_access("GET", "/api/news/gold"))
        self.assertTrue(main._requires_admin_access("GET", "/api/news/gold/bias"))
        self.assertTrue(main._requires_admin_access("GET", "/api/news/search"))
        self.assertFalse(main._requires_admin_access("GET", "/api/news/gold/latest"))
        self.assertTrue(main._requires_admin_access("POST", "/api/arkham/scrape/full"))

    def test_api_mutation_routes_are_reviewed_for_admin_or_client_use(self) -> None:
        client_allowed = {
            ("POST", "/api/security/login"),
            ("POST", "/api/security/logout"),
            ("POST", "/api/alpha/simulate/prediction-copy"),
            ("POST", "/api/alpha/simulate/manipulation"),
            ("POST", "/api/alpha/events/dedupe"),
            ("POST", "/api/alpha/risk/token"),
            ("POST", "/api/alpha/usage/event"),
            ("POST", "/api/alpha/wallet/verify"),
        }
        violations: list[str] = []

        for route in main.app.routes:
            path = getattr(route, "path", "")
            methods = set(getattr(route, "methods", set()) or set())
            if not path.startswith("/api/"):
                continue
            for method in sorted(methods & {"POST", "PUT", "PATCH", "DELETE"}):
                if (method, path) in client_allowed:
                    continue
                if main._requires_admin_access(method, path):
                    continue
                dependant = getattr(route, "dependant", None)
                dependencies = getattr(dependant, "dependencies", []) if dependant else []
                dependency_names = {
                    getattr(getattr(dependency, "call", None), "__name__", "")
                    for dependency in dependencies
                }
                if "_require_data_admin" in dependency_names or "_require_alpha_admin" in dependency_names:
                    continue
                violations.append(f"{method} {path}")

        self.assertEqual(violations, [], "Mutation routes must be admin-gated or explicitly client-allowlisted.")

    def test_admin_request_requires_dedicated_admin_token(self) -> None:
        old_admin = main._ADMIN_TOKEN
        main._ADMIN_TOKEN = "admin-secret"
        try:
            user_request = _request(headers=[(b"host", b"100.114.51.121:8000"), (b"x-core-token", b"client-secret")])
            admin_request = _request(headers=[(b"host", b"100.114.51.121:8000"), (b"x-core-admin-token", b"admin-secret")])

            self.assertFalse(main._is_admin_request(user_request))
            self.assertTrue(main._is_admin_request(admin_request))
        finally:
            main._ADMIN_TOKEN = old_admin

    def test_local_auth_bypass_only_allows_direct_localhost(self) -> None:
        self.assertTrue(main._is_local_client(_local_request()))

        tailscale_host = _local_request(headers=[(b"host", b"100.114.51.121:8000")])
        forwarded = _local_request(
            headers=[
                (b"host", b"127.0.0.1:8000"),
                (b"x-forwarded-for", b"100.64.0.10"),
            ]
        )

        self.assertFalse(main._is_local_client(tailscale_host))
        self.assertFalse(main._is_local_client(forwarded))

    def test_local_auth_bypass_allows_windows_wsl_proxy_only_for_localhost_host(self) -> None:
        wsl_proxy = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/test",
                "query_string": b"",
                "headers": [(b"host", b"127.0.0.1:8000")],
                "client": ("172.18.216.1", 4242),
                "server": ("127.0.0.1", 8000),
                "scheme": "http",
            }
        )
        spoofed_tailscale = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/test",
                "query_string": b"",
                "headers": [(b"host", b"127.0.0.1:8000")],
                "client": ("100.114.51.121", 4242),
                "server": ("100.114.51.121", 8000),
                "scheme": "http",
            }
        )
        forwarded_proxy = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/api/test",
                "query_string": b"",
                "headers": [
                    (b"host", b"127.0.0.1:8000"),
                    (b"x-forwarded-for", b"100.64.0.10"),
                ],
                "client": ("172.18.216.1", 4242),
                "server": ("127.0.0.1", 8000),
                "scheme": "http",
            }
        )

        self.assertTrue(main._is_local_client(wsl_proxy))
        self.assertFalse(main._is_local_client(spoofed_tailscale))
        self.assertFalse(main._is_local_client(forwarded_proxy))

    def test_security_headers_reduce_wallet_drainer_blast_radius(self) -> None:
        response = main._with_security_headers(Response())

        csp = response.headers.get("content-security-policy", "")
        self.assertIn("default-src 'self'", csp)
        self.assertIn("object-src 'none'", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("frame-src 'none'", csp)
        self.assertNotIn("connect-src 'self' ws:", csp)
        self.assertIn("ws://127.0.0.1:*", csp)
        self.assertEqual(response.headers.get("x-content-type-options"), "nosniff")
        self.assertEqual(response.headers.get("referrer-policy"), "no-referrer")
        self.assertIn("payment=()", response.headers.get("permissions-policy", ""))

    def test_static_file_helper_blocks_path_traversal(self) -> None:
        if not hasattr(main, "_safe_static_file"):
            self.skipTest("frontend static helper is only defined when backend/static exists")

        self.assertIsNone(main._safe_static_file("../backend/.env"))
        self.assertIsNone(main._safe_static_file("..\\backend\\.env"))

    def test_oversized_mutation_body_is_rejected_before_route(self) -> None:
        request = _request(
            headers=[
                (b"host", b"100.114.51.121:8000"),
                (b"content-length", str(main._MAX_REQUEST_BODY_BYTES + 1).encode("ascii")),
            ],
            method="POST",
        )

        async def call_next(_: Request) -> Response:
            return Response("unexpected")

        response = asyncio.run(main.private_access_gate(request, call_next))
        self.assertEqual(response.status_code, 413)


def _gate(request: Request) -> int:
    """Passe la requête dans le middleware et rend le code HTTP."""

    async def call_next(_: Request) -> Response:
        return Response("passe", status_code=200)

    return asyncio.run(main.private_access_gate(request, call_next)).status_code


def _peer_request(client: str, host: bytes, path: str = "/api/test", method: str = "GET") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": [(b"host", host)],
            "client": (client, 4242),
            "server": (client, 8000),
            "scheme": "http",
        }
    )


class AdminGateWithoutAccessTokenTests(unittest.TestCase):
    """F-047 — l'absence de `CORE_ACCESS_TOKEN` ne doit PAS ouvrir les
    routes admin à un pair distant.

    Le mode « local-open » (pas de token d'accès) reste le défaut pour
    `/api/*` : c'est le confort de dev local. Mais le middleware
    court-circuait AVANT d'appeler `_requires_admin_access`, donc sans
    token les préfixes admin devenaient publics — `/api/desktop/launch/app`
    (exécute un process), `/api/desktop/mouse/click` (pilote la souris),
    `/api/chat` (donne le terminal à un LLM) — sur un serveur qui écoute
    sur 0.0.0.0:8000.
    """

    ADMIN_ROUTES = [
        ("POST", "/api/desktop/launch/app"),
        ("POST", "/api/desktop/mouse/click"),
        ("POST", "/api/chat"),
        ("POST", "/api/agents/run"),
        ("POST", "/api/vision/analyze"),
        ("POST", "/api/intel/investigate"),
        ("GET", "/api/market/mt5/account"),
    ]

    def setUp(self) -> None:
        self._token = main._ACCESS_TOKEN
        self._admin = main._ADMIN_TOKEN
        main._ACCESS_TOKEN = ""      # mode local-open
        main._ADMIN_TOKEN = ""

    def tearDown(self) -> None:
        main._ACCESS_TOKEN = self._token
        main._ADMIN_TOKEN = self._admin

    def test_admin_route_refusee_sans_token_depuis_un_pair_distant(self) -> None:
        for method, path in self.ADMIN_ROUTES:
            with self.subTest(route=f"{method} {path}"):
                req = _peer_request("172.18.216.1", b"localhost:8000",
                                    path=path, method=method)
                self.assertEqual(
                    _gate(req), 403,
                    f"{method} {path} passe en mode local-open depuis "
                    f"172.18.216.1 : le gate admin est court-circuité")

    def test_admin_route_refusee_meme_avec_un_entete_host_local(self) -> None:
        """L'en-tête Host est choisi par le client : il ne prouve rien."""
        req = _peer_request("172.18.216.1", b"127.0.0.1:8000",
                            path="/api/desktop/launch/app", method="POST")
        self.assertEqual(_gate(req), 403)

    def test_admin_route_refusee_depuis_une_ip_publique(self) -> None:
        req = _peer_request("203.0.113.9", b"127.0.0.1:8000",
                            path="/api/desktop/launch/app", method="POST")
        self.assertEqual(_gate(req), 403)

    def test_admin_route_autorisee_avec_admin_token_meme_depuis_le_distant(self) -> None:
        """S1 — le token admin ouvre, y compris derrière un proxy.

        C'est le SEUL moyen d'ouvrir une route d'exécution : ni le pair de
        socket, ni la boucle locale, ni l'absence de token d'accès ne
        suffisent.
        """
        main._ADMIN_TOKEN = "admin-secret"
        req = _peer_request("127.0.0.1", b"127.0.0.1:8000",
                            path="/api/desktop/launch/app", method="POST")
        req.scope["headers"] = [
            (b"host", b"127.0.0.1:8000"),
            (b"x-core-admin-token", b"admin-secret"),
        ]
        self.assertEqual(_gate(req), 200)

    def test_les_routes_admin_non_execution_restent_ouvertes_en_local(self) -> None:
        """Le confort de dev n'est retiré QUE de la classe exécution.

        `/api/arkham/db` et `/api/news/gold` lisent des données ; ils
        gardent la porte loopback ouverte en local-open.
        """
        for path in ("/api/arkham/db/stats", "/api/news/gold"):
            with self.subTest(path=path):
                self.assertEqual(
                    _gate(_peer_request("127.0.0.1", b"127.0.0.1:8000", path=path)), 200)

    # ——— S1 : F-047 était contournable derrière un proxy local ———

    EXECUTION_ROUTES = [
        ("POST", "/api/desktop/launch/app"),
        ("POST", "/api/desktop/mouse/click"),
        ("POST", "/api/chat"),
        ("POST", "/api/agents/run"),
        ("POST", "/api/vision/analyze"),
        ("POST", "/api/intel/investigate"),
        ("GET", "/api/market/mt5/account"),
    ]

    def test_route_d_execution_refusee_meme_en_boucle_locale(self) -> None:
        """S1 — le test d'acceptation de l'audit.

        F-047 ouvrait les routes d'exécution à quiconque avait
        `client.host == 127.0.0.1`. Or le déploiement prévu du projet est
        un tunnel (`configs/cloudflare-tunnel.example.yml` :
        `service: http://127.0.0.1:8000`) : derrière cloudflared, TOUTE
        requête distante arrive depuis la boucle locale.

        Concrètement : sans token, `/api/desktop/launch/app` exécutait un
        process pour n'importe qui sur Internet. Il doit maintenant être
        refusé même depuis 127.0.0.1.
        """
        for method, path in self.EXECUTION_ROUTES:
            with self.subTest(route=f"{method} {path}"):
                self.assertEqual(
                    _gate(_peer_request("127.0.0.1", b"127.0.0.1:8000",
                                        path=path, method=method)),
                    403,
                    f"{method} {path} s'ouvre en boucle locale sans token : "
                    f"le tunnel rend le pair de socket inexploitable")

    def test_entete_de_proxy_invalide_la_qualite_de_locale(self) -> None:
        """`127.0.0.1` + `X-Forwarded-For` = un relais, pas un client local."""
        for header in (b"x-forwarded-for", b"cf-connecting-ip", b"x-real-ip",
                       b"forwarded", b"true-client-ip", b"x-original-forwarded-for"):
            with self.subTest(header=header):
                req = Request({
                    "type": "http", "method": "GET", "path": "/api/test",
                    "query_string": b"", "client": ("127.0.0.1", 4242),
                    "server": ("127.0.0.1", 8000), "scheme": "http",
                    "headers": [(b"host", b"127.0.0.1:8000"),
                                (header, b"203.0.113.9")],
                })
                self.assertFalse(main._is_strictly_local_peer(req),
                                 f"{header!r} est ignoré")

    def test_route_non_execution_refusee_si_proxy_derriere(self) -> None:
        """Le refus « local-only » tient aussi quand un proxy est présent."""
        req = Request({
            "type": "http", "method": "GET", "path": "/api/arkham/db/stats",
            "query_string": b"", "client": ("127.0.0.1", 4242),
            "server": ("127.0.0.1", 8000), "scheme": "http",
            "headers": [(b"host", b"127.0.0.1:8000"),
                        (b"x-forwarded-for", b"203.0.113.9")],
        })
        self.assertEqual(_gate(req), 403)

    def test_sans_proxy_la_boucle_locale_reste_locale(self) -> None:
        """Contrôle négatif : le refus ne doit pas tout casser."""
        self.assertTrue(main._is_strictly_local_peer(
            _peer_request("127.0.0.1", b"127.0.0.1:8000")))
        self.assertTrue(main._is_strictly_local_peer(
            _peer_request("::1", b"[::1]:8000")))

    def test_les_prefixes_d_execution_sont_bien_couverts(self) -> None:
        """Un oubli dans la liste rendrait une route d'exécution publique."""
        for method, path in self.EXECUTION_ROUTES:
            self.assertTrue(main._requires_execution_token(method, path), path)
        for path in ("/api/arkham/db/stats", "/api/news/gold",
                     "/api/market/prices", "/api/agents-list"):
            self.assertFalse(main._requires_execution_token("GET", path), path)



    def test_avec_access_token_le_comportement_admin_est_inchange(self) -> None:
        """Régression : avec token, la branche admin d'origine doit tenir."""
        main._ACCESS_TOKEN = "client-secret"
        for method, path in self.ADMIN_ROUTES:
            with self.subTest(route=f"{method} {path}"):
                req = _peer_request("203.0.113.9", b"example:8000",
                                    path=path, method=method)
                req.scope["headers"] = [
                    (b"host", b"example:8000"),
                    (b"x-core-token", b"client-secret"),
                ]
                self.assertEqual(_gate(req), 403, "admin sans token admin")

    def test_is_strictly_local_peer_ignore_l_entete_host(self) -> None:
        self.assertTrue(main._is_strictly_local_peer(
            _peer_request("127.0.0.1", b"nimporte-quoi:8000")))
        self.assertTrue(main._is_strictly_local_peer(
            _peer_request("127.0.0.5", b"nimporte-quoi:8000")))
        self.assertFalse(main._is_strictly_local_peer(
            _peer_request("172.18.216.1", b"127.0.0.1:8000")))
        self.assertFalse(main._is_strictly_local_peer(
            _peer_request("203.0.113.9", b"127.0.0.1:8000")))


if __name__ == "__main__":
    unittest.main()


class BindSafetyTests(unittest.TestCase):
    """S2 — refuser de démarrer sur une interface large sans token.

    Le mode « local-open » se définit par l'absence de `CORE_ACCESS_TOKEN`.
    Tant que le serveur n'écoute que sur la boucle locale, cette
    configuration veut dire ce qu'elle dit. Dès qu'il écoute sur 0.0.0.0,
    elle expose toutes les routes `/api/*` au réseau — et c'était l'état
    par défaut (`--host 0.0.0.0 --reload` dans start_all.sh et dans le
    `__main__` de main.py).
    """

    MATRICE = [
        # (host, token configuré, doit démarrer ?)
        ("127.0.0.1", False, True),
        ("localhost", False, True),
        ("::1", False, True),
        ("0.0.0.0", False, False),
        ("0.0.0.0", True, True),
        ("192.168.1.5", False, False),
    ]

    def setUp(self) -> None:
        self._token = main._ACCESS_TOKEN

    def tearDown(self) -> None:
        main._ACCESS_TOKEN = self._token

    def test_matrice_bind_vers_token(self) -> None:
        for host, has_token, must_start in self.MATRICE:
            with self.subTest(host=host, token=has_token):
                main._ACCESS_TOKEN = "secret" if has_token else ""
                if must_start:
                    main._assert_safe_bind(host, False)
                else:
                    with self.assertRaises(SystemExit):
                        main._assert_safe_bind(host, False)

    def test_le_refus_explique_les_deux_options(self) -> None:
        main._ACCESS_TOKEN = ""
        with self.assertRaises(SystemExit) as ctx:
            main._assert_safe_bind("0.0.0.0", False)
        msg = str(ctx.exception)
        self.assertIn("CORE_ACCESS_TOKEN", msg)
        self.assertIn("CORE_HOST", msg, "le message doit dire comment sortir de là")

    def test_loopback_bind_reconnait_les_boucles(self) -> None:
        for host in ("127.0.0.1", "127.0.0.5", "::1", "localhost"):
            self.assertTrue(main._loopback_bind(host), host)
        for host in ("0.0.0.0", "192.168.1.5", "::", ""):
            self.assertFalse(main._loopback_bind(host), host)

    def test_le_controle_de_boucle_est_unique(self) -> None:
        """Verrou d'anti-régression : une seule implémentation.

        `addr in _LOOPBACK_NETWORKS` sur un tuple teste l'ÉGALITÉ, pas
        l'appartenance. L'erreur a été commise deux fois (F-047, puis S2)
        — la seconde fois juste sous le commentaire d'avertissement.
        Elle doit maintenant n'exister qu'à un seul endroit.
        """
        import ast
        import inspect
        import textwrap
        tree = ast.parse(textwrap.dedent(inspect.getsource(main)))
        # On compte les LECTURES de la constante (contexte Load), pas sa
        # définition : une affectation la crée, chaque usage la consomme.
        sites = [(n.lineno, n.id) for n in ast.walk(tree)
                 if isinstance(n, ast.Name) and n.id == "_LOOPBACK_NETWORKS"
                 and isinstance(n.ctx, ast.Load)]
        self.assertEqual(len(sites), 1,
                         f"l'appartenance à la boucle doit être testée en UN "
                         f"seul endroit : {sites}")

    def test_le_reste_de_api_reste_ouvert_en_local_open(self) -> None:
        """Le confort de dev est PRÉSERVÉ : rien d'autre n'est durci."""
        for path in ("/api/market/prices", "/api/news/gold/latest", "/api/arkham/top-entities"):
            with self.subTest(path=path):
                self.assertEqual(_gate(_peer_request("172.18.216.1", b"127.0.0.1:8000", path=path)), 200)

    def test_health_reste_public(self) -> None:
        self.assertEqual(_gate(_peer_request("203.0.113.9", b"x:8000", path="/health")), 200)

    def test_la_shell_react_reste_atteignable(self) -> None:
        """Le shell doit rester atteignable pour afficher l'écran de login."""
        self.assertEqual(_gate(_peer_request("203.0.113.9", b"x:8000", path="/")), 200)
