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

    def test_admin_route_autorisee_depuis_la_boucle_locale(self) -> None:
        """Le dev local doit continuer de fonctionner sans token."""
        req = _peer_request("127.0.0.1", b"127.0.0.1:8000",
                            path="/api/desktop/launch/app", method="POST")
        self.assertEqual(_gate(req), 200)

    def test_admin_route_autorisee_avec_admin_token_meme_depuis_le_distant(self) -> None:
        main._ADMIN_TOKEN = "admin-secret"
        req = _peer_request("203.0.113.9", b"example:8000",
                            path="/api/desktop/launch/app", method="POST")
        req.scope["headers"] = [
            (b"host", b"example:8000"),
            (b"x-core-admin-token", b"admin-secret"),
        ]
        self.assertEqual(_gate(req), 200)

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
