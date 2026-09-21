from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DOCS_DIR = BASE_DIR.parents[3] / "docs"
JSON_OUT = BASE_DIR / "aster_strategy_registry_latest.json"
HTML_OUT = DOCS_DIR / "core-equity-aster-strategy-registry.html"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(html.escape(str(item)) for item in value)
    return html.escape(str(value))


def _code(value: str) -> str:
    return f"<code>{html.escape(value)}</code>"


def _strategy_families() -> list[dict[str, Any]]:
    return [
        {
            "family_id": "crypto_liquid_momentum",
            "status": "active",
            "purpose": "Recherche long sur crypto liquides avec confirmation mark/index, funding, exchangeInfo et forward paper.",
            "main_scripts": ["backtest_strategy_discovery.py", "aster_promotion_ready_lanes_report.py"],
            "typical_presets": ["core", "aster_v2"],
            "typical_timeframes": ["30m", "1h", "2h", "3h", "5h"],
            "known_symbols": ["LABUSDT", "INJUSDT", "TIAUSDT", "ASTERUSDT", "HYPEUSDT"],
            "decision_rule": "Peut passer en forward seulement si promotion truth exact-lane confirme la lane.",
        },
        {
            "family_id": "macro_commodity_slow_confirmation",
            "status": "exploration",
            "purpose": "Tester commodities/synth macro sur timeframes lents, sans les mélanger aux champions crypto.",
            "main_scripts": ["backtest_strategy_discovery.py"],
            "typical_presets": ["macro", "macro_equity"],
            "typical_timeframes": ["2h", "3h", "4h", "5h", "6h"],
            "known_symbols": ["XAUUSDT", "XAGUSDT", "CLUSDT", "BZUSDT", "CRCLUSDT", "ORCLUSDT"],
            "decision_rule": "Reste exploration tant qu'il n'y a pas microstructure + forward paper séparés.",
        },
        {
            "family_id": "equity_synth_slow_confirmation",
            "status": "exploration",
            "purpose": "Tester actions synthétiques Aster avec contraintes de liquidité plus strictes.",
            "main_scripts": ["backtest_strategy_discovery.py"],
            "typical_presets": ["equities", "macro_equity"],
            "typical_timeframes": ["1h", "2h", "3h", "4h", "5h", "6h"],
            "known_symbols": ["AAPLUSDT", "TSLAUSDT", "NVDAUSDT", "MSFTUSDT", "INTCUSDT", "AMDUSDT"],
            "decision_rule": "Ne pas promouvoir si le meilleur résultat vient d'un sample faible ou d'une microstructure mince.",
        },
        {
            "family_id": "priority_watchlist_exploration",
            "status": "exploration",
            "purpose": "Chercher de nouveaux actifs via l'univers public/WS au lieu de rester figé sur les mêmes paires.",
            "main_scripts": ["backtest_priority_watchlist.py", "research/priority_watchlist_backtest_runner.py"],
            "typical_presets": ["priority_watchlist"],
            "typical_timeframes": ["15m", "30m", "1h", "2h", "3h"],
            "known_symbols": ["dynamic_from_priority_watchlist"],
            "decision_rule": "Un candidat intéressant doit être réinjecté dans promotion truth avant forward persistant.",
        },
        {
            "family_id": "short_fade_archive",
            "status": "archive",
            "purpose": "Ancienne hypothèse short/fade sur anomalies order-flow. Utile comme preuve, pas comme runner actif principal.",
            "main_scripts": ["monitor_shorts.py", "aster_paper_trading_sandbox.py"],
            "typical_presets": ["manual_symbols"],
            "typical_timeframes": ["trade_stream"],
            "known_symbols": ["1000SATSUSDT", "ORDIUSDT", "WIFUSDT", "PEPEUSDT"],
            "decision_rule": "Ne pas relancer comme source de décision actuelle sans nouveau protocole de vérité.",
        },
        {
            "family_id": "reporting_truth_layer",
            "status": "control",
            "purpose": "Couche de vérité: lit les artefacts, ne backteste pas, et décide promote/watch/reject.",
            "main_scripts": [
                "aster_strategy_truth_report.py",
                "aster_promotion_truth_report.py",
                "aster_lane_promotion_scoring.py",
            ],
            "typical_presets": ["local_artifacts"],
            "typical_timeframes": ["not_applicable"],
            "known_symbols": ["all_from_artifacts"],
            "decision_rule": "Toujours lire cette couche avant de conclure qu'une stratégie est bonne.",
        },
    ]


def _script_registry() -> list[dict[str, Any]]:
    return [
        {
            "script": "backtest_strategy_discovery.py",
            "kind": "backtest_discovery",
            "status": "active_core",
            "strategy_exactness": "parametric: output_tag + symbol_preset + search_mode + trigger_reference + execution_model + timeframe",
            "family_ids": [
                "crypto_liquid_momentum",
                "macro_commodity_slow_confirmation",
                "equity_synth_slow_confirmation",
            ],
            "writes": "CSV/JSON locaux uniquement",
            "safe_to_run_afk": True,
            "canonical_command": "python -m services.onchain.aster.backtest_strategy_discovery --symbol-preset core --output-tag core_exchangeinfo --groups both",
            "artifacts": [
                "paper_trading_strategy_discovery_<tag>_v2.csv",
                "paper_trading_strategy_discovery_<tag>_latest.json",
                "paper_trading_strategy_discovery_<tag>_progress_v2.csv",
            ],
            "notes": "Runner principal. Les CSV v2_1 portent strategy_profile_id/profile_family/profile_key pour identifier chaque stratégie exacte.",
        },
        {
            "script": "backtest_aster_v2.py",
            "kind": "research_runner_wrapper",
            "status": "active_exploration",
            "strategy_exactness": "wrapper around research/aster_v2_runner.py",
            "family_ids": ["crypto_liquid_momentum", "priority_watchlist_exploration"],
            "writes": "CSV/JSON locaux uniquement",
            "safe_to_run_afk": True,
            "canonical_command": "python -m services.onchain.aster.backtest_aster_v2 --groups both --output-tag aster_v2_exchangeinfo",
            "artifacts": ["aster_v2_runner_plan_latest.json", "paper_trading_strategy_discovery_aster_v2*_v2.csv"],
            "notes": "Utilise champions + watchlist priorisée + univers public. Plus propre que relancer uniquement core figé.",
        },
        {
            "script": "backtest_priority_watchlist.py",
            "kind": "research_runner_wrapper",
            "status": "active_exploration",
            "strategy_exactness": "wrapper around research/priority_watchlist_backtest_runner.py",
            "family_ids": ["priority_watchlist_exploration"],
            "writes": "CSV/JSON locaux uniquement",
            "safe_to_run_afk": True,
            "canonical_command": "python -m services.onchain.aster.backtest_priority_watchlist --output-tag priority_watchlist",
            "artifacts": ["aster_priority_watchlist_backtest_plan_latest.json", "paper_trading_strategy_discovery_priority_watchlist*_v2.csv"],
            "notes": "Sert à sortir du piège des mêmes symboles. Les gagnants doivent être revalidés ailleurs.",
        },
        {
            "script": "monitor_multi_strategy.py",
            "kind": "forward_paper_monitor",
            "status": "legacy_watch",
            "strategy_exactness": "strategy_id maps to fixed symbols, event_type, UTC regime and max holding profile",
            "family_ids": ["crypto_liquid_momentum"],
            "writes": "ledger paper-trading si --persist",
            "safe_to_run_afk": True,
            "canonical_command": "python -m services.onchain.aster.monitor_multi_strategy --strategies inj_tia_regime_filtered --run-forever --sleep-seconds 300 --forward-window-trades 1000 --persist",
            "artifacts": ["paper_trading_multi_strategy_stateful_monitor.csv", "paper_trading_multi_strategy_stateful_heartbeat.json"],
            "notes": "A garder pour historique, mais ne doit pas surclasser promotion truth.",
        },
        {
            "script": "monitor_optimized_longs.py",
            "kind": "forward_paper_monitor",
            "status": "legacy_watch",
            "strategy_exactness": "fixed optimized long breakout profiles from sandbox",
            "family_ids": ["crypto_liquid_momentum"],
            "writes": "ledger paper-trading si --persist",
            "safe_to_run_afk": True,
            "canonical_command": "python -m services.onchain.aster.monitor_optimized_longs --symbols INJUSDT,NEARUSDT,TIAUSDT --run-forever --sleep-seconds 300 --forward-window-trades 1000 --persist",
            "artifacts": ["paper_trading_optimized_longs_monitor.csv"],
            "notes": "Runner historique. Utile pour continuité mais pas source finale de promotion.",
        },
        {
            "script": "aster_promotion_ready_lanes_report.py",
            "kind": "promotion_and_forward_runner",
            "status": "active_control",
            "strategy_exactness": "exact lane = symbol + interval + side + strict/non-strict event_type",
            "family_ids": ["crypto_liquid_momentum", "reporting_truth_layer"],
            "writes": "HTML/JSON report; ledger paper-trading seulement avec --persist forward-cycle",
            "safe_to_run_afk": True,
            "canonical_command": "python -m services.onchain.aster.aster_promotion_ready_lanes_report --strict-forward-cycle --run-forever --sleep-seconds 300 --forward-window-trades 1000 --persist",
            "artifacts": [
                "aster_promotion_ready_lanes_latest.json",
                "paper_trading_strict_promotion_ready_forward_monitor.csv",
                "docs/core-equity-aster-promotion-ready-lanes.html",
            ],
            "notes": "Pont entre backtest et forward. La variante stricte est préférée.",
        },
        {
            "script": "aster_strategy_truth_report.py",
            "kind": "truth_report",
            "status": "active_control",
            "strategy_exactness": "event_type-level truth from ledger",
            "family_ids": ["reporting_truth_layer"],
            "writes": "JSON/HTML report uniquement",
            "safe_to_run_afk": False,
            "canonical_command": "python -m services.onchain.aster.aster_strategy_truth_report",
            "artifacts": ["aster_strategy_truth_report_latest.json", "docs/core-equity-aster-strategy-truth-report.html"],
            "notes": "À générer avant toute décision. Lit net + latent, pas juste le PnL réalisé.",
        },
        {
            "script": "aster_promotion_truth_report.py",
            "kind": "strict_truth_report",
            "status": "active_control",
            "strategy_exactness": "exact lane truth: symbol + interval + side",
            "family_ids": ["reporting_truth_layer"],
            "writes": "JSON/HTML report uniquement",
            "safe_to_run_afk": False,
            "canonical_command": "python -m services.onchain.aster.aster_promotion_truth_report",
            "artifacts": ["aster_promotion_truth_report_latest.json", "docs/core-equity-aster-promotion-truth-report.html"],
            "notes": "Source finale actuelle pour ne pas confondre LAB 3h, LAB 5h, LAB 30m, etc.",
        },
        {
            "script": "aster_lane_promotion_scoring.py",
            "kind": "ranking_overlay",
            "status": "active_control",
            "strategy_exactness": "lane score with blockers and lifecycle",
            "family_ids": ["reporting_truth_layer"],
            "writes": "CSV/JSON/HTML report uniquement",
            "safe_to_run_afk": False,
            "canonical_command": "python -m services.onchain.aster.aster_lane_promotion_scoring",
            "artifacts": ["aster_lane_promotion_scoring_latest.csv", "docs/core-equity-aster-lane-promotion-scoring.html"],
            "notes": "Donne une file d'attente propre: promote, watch, discovered, rejected.",
        },
        {
            "script": "aster_microstructure_replay_validator.py",
            "kind": "execution_quality_validator",
            "status": "active_control",
            "strategy_exactness": "validates fill plausibility for explicit symbol+interval+side lanes",
            "family_ids": ["reporting_truth_layer"],
            "writes": "JSON local uniquement",
            "safe_to_run_afk": False,
            "canonical_command": "python -m services.onchain.aster.aster_microstructure_replay_validator",
            "artifacts": ["aster_entry_microstructure_diagnostic_latest.json"],
            "notes": "Contrôle spread, gaps, volume réel et nombre de trades. Ne cherche pas de stratégie.",
        },
        {
            "script": "monitor_shorts.py",
            "kind": "legacy_experiment",
            "status": "archive",
            "strategy_exactness": "multiple internal long/short experiments, not current promotion lane format",
            "family_ids": ["short_fade_archive"],
            "writes": "CSV locaux",
            "safe_to_run_afk": False,
            "canonical_command": "not_recommended_currently",
            "artifacts": ["paper_trading_multi_strategy_monitor.csv", "paper_trading_strategy_monitor.csv"],
            "notes": "Conserver comme historique. Ne pas mélanger avec les décisions actuelles.",
        },
    ]


def get_aster_strategy_registry_preview(dry_run: bool = True) -> dict[str, Any]:
    families = _strategy_families()
    scripts = _script_registry()
    by_status: dict[str, int] = {}
    for row in scripts:
        status = str(row.get("status") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
    return {
        "ok": True,
        "dry_run": bool(dry_run),
        "generated_at": _now(),
        "purpose": "canonical_registry_for_aster_backtest_and_forward_scripts",
        "summary": {
            "strategy_families": len(families),
            "registered_scripts": len(scripts),
            "script_status_counts": by_status,
            "current_decision_source": "aster_promotion_truth_report + aster_lane_promotion_scoring",
        },
        "naming_rules": [
            "Une stratégie backtestée doit être identifiée par output_tag + symbol + interval + side + trigger_reference + execution_model + leverage.",
            "Une stratégie forward doit être identifiée par event_type ou strategy_id, jamais seulement par symbol.",
            "Une lane promue doit être validée en exact-lane: symbol + interval + side.",
            "Les scripts archive/legacy peuvent rester présents mais ne doivent pas être lancés comme preuve actuelle.",
        ],
        "strategy_families": families,
        "scripts": scripts,
        "would_write": False,
        "writes_performed": 0,
    }


def _render_html(payload: dict[str, Any]) -> str:
    scripts = payload.get("scripts") or []
    families = payload.get("strategy_families") or []
    script_rows = "\n".join(
        f"""
        <tr>
          <td>{_code(row.get("script", ""))}<br><span>{_cell(row.get("kind"))}</span></td>
          <td><b class="status">{_cell(row.get("status"))}</b></td>
          <td>{_cell(row.get("strategy_exactness"))}</td>
          <td>{_cell(row.get("family_ids"))}</td>
          <td>{_cell(row.get("notes"))}</td>
        </tr>
        """
        for row in scripts
    )
    family_cards = "\n".join(
        f"""
        <article class="card">
          <h3>{_cell(row.get("family_id"))}</h3>
          <p><b>Statut:</b> {_cell(row.get("status"))}</p>
          <p>{_cell(row.get("purpose"))}</p>
          <p><b>Scripts:</b> {_cell(row.get("main_scripts"))}</p>
          <p><b>Timeframes:</b> {_cell(row.get("typical_timeframes"))}</p>
          <p><b>Règle:</b> {_cell(row.get("decision_rule"))}</p>
        </article>
        """
        for row in families
    )
    command_rows = "\n".join(
        f"""
        <tr>
          <td>{_code(row.get("script", ""))}</td>
          <td>{_cell(row.get("status"))}</td>
          <td><pre>{_cell(row.get("canonical_command"))}</pre></td>
        </tr>
        """
        for row in scripts
        if row.get("canonical_command") and row.get("canonical_command") != "not_recommended_currently"
    )
    summary = payload.get("summary") or {}
    return f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Core Equity - Registry Stratégies Aster</title>
  <style>
    :root {{
      --bg:#0d1117; --panel:#151c26; --soft:#101720; --text:#f1f6fb; --muted:#9fb0c0;
      --line:#263445; --green:#5ee08d; --amber:#f2c265; --blue:#7fb7ff;
    }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:radial-gradient(circle at 12% 0%, rgba(127,183,255,.18), transparent 34%), var(--bg); color:var(--text); font-family:"Segoe UI", Aptos, sans-serif; line-height:1.55; }}
    header {{ padding:42px 52px 30px; border-bottom:1px solid var(--line); }}
    main {{ max-width:1480px; margin:0 auto; padding:30px 52px 68px; }}
    h1 {{ margin:0 0 10px; font-size:clamp(34px,4vw,56px); letter-spacing:-.055em; line-height:1; }}
    h2 {{ margin:0 0 14px; font-size:23px; }}
    h3 {{ margin:0 0 10px; }}
    p {{ color:var(--muted); margin:0 0 10px; }}
    code {{ background:#091018; border:1px solid #1c2a39; border-radius:7px; padding:2px 6px; color:#dcecff; }}
    pre {{ white-space:pre-wrap; margin:0; background:#091018; border:1px solid #1c2a39; border-radius:12px; padding:10px; color:#dcecff; }}
    a {{ color:#9fd0ff; text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .grid {{ display:grid; gap:16px; }}
    .g3 {{ grid-template-columns:repeat(3,minmax(0,1fr)); }}
    .card {{ background:rgba(21,28,38,.95); border:1px solid var(--line); border-radius:20px; padding:19px; box-shadow:0 20px 50px rgba(0,0,0,.22); }}
    .hero {{ display:grid; grid-template-columns:1.35fr .65fr; gap:18px; }}
    .kpi {{ background:var(--soft); border:1px solid var(--line); border-radius:16px; padding:15px; }}
    .kpi strong {{ display:block; font-size:30px; color:var(--green); }}
    .badge {{ display:inline-flex; padding:4px 9px; border-radius:999px; border:1px solid var(--line); background:#0d141d; color:var(--amber); font-weight:800; font-size:12px; text-transform:uppercase; }}
    table {{ width:100%; border-collapse:collapse; border-radius:16px; overflow:hidden; }}
    th,td {{ padding:11px 12px; border-bottom:1px solid var(--line); text-align:left; vertical-align:top; font-size:13px; }}
    th {{ background:#101720; color:#d9e6f5; text-transform:uppercase; font-size:11px; letter-spacing:.06em; }}
    tr:last-child td {{ border-bottom:0; }}
    td span {{ color:var(--muted); font-size:12px; }}
    .status {{ color:var(--blue); }}
    .section {{ margin-top:22px; }}
    .rules li {{ margin:8px 0; color:var(--muted); }}
    @media (max-width:1000px) {{ header,main {{ padding-left:22px; padding-right:22px; }} .hero,.g3 {{ grid-template-columns:1fr; }} }}
  </style>
</head>
<body>
  <header>
    <h1>Registry Stratégies Aster</h1>
    <p>Carte canonique pour savoir quel fichier Python correspond à quelle famille de stratégie, quel statut il a, et quels artefacts il produit.</p>
    <p>Généré le {_cell(payload.get("generated_at"))}. Aucun backtest lancé par ce rapport.</p>
  </header>
  <main>
    <section class="hero">
      <div class="card">
        <h2>Pourquoi c'est important</h2>
        <p>On a maintenant beaucoup de runners. Sans registre, un ROI peut être attribué au mauvais script, au mauvais timeframe ou au mauvais event_type. Cette page évite ce piège.</p>
        <ul class="rules">
          {''.join(f'<li>{_cell(rule)}</li>' for rule in payload.get("naming_rules") or [])}
        </ul>
      </div>
      <div class="grid">
        <div class="kpi"><strong>{_cell(summary.get("registered_scripts"))}</strong><span>scripts enregistrés</span></div>
        <div class="kpi"><strong>{_cell(summary.get("strategy_families"))}</strong><span>familles de stratégie</span></div>
      </div>
    </section>

    <section class="grid g3 section">
      {family_cards}
    </section>

    <section class="card section">
      <h2>Scripts et responsabilité exacte</h2>
      <table>
        <thead><tr><th>Script</th><th>Statut</th><th>Identité stratégie</th><th>Familles</th><th>Note</th></tr></thead>
        <tbody>{script_rows}</tbody>
      </table>
    </section>

    <section class="card section">
      <h2>Commandes canoniques</h2>
      <p>Ces commandes ne sont pas toutes à lancer en même temps. Elles servent à identifier proprement le rôle de chaque script.</p>
      <table>
        <thead><tr><th>Script</th><th>Statut</th><th>Commande</th></tr></thead>
        <tbody>{command_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


def write_aster_strategy_registry() -> dict[str, Any]:
    payload = get_aster_strategy_registry_preview(dry_run=True)
    JSON_OUT.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    HTML_OUT.write_text(_render_html(payload), encoding="utf-8")
    payload["would_write"] = True
    payload["writes_performed"] = 2
    payload["outputs"] = {"json": str(JSON_OUT), "html": str(HTML_OUT)}
    return payload


def main() -> None:
    payload = write_aster_strategy_registry()
    summary = payload.get("summary") or {}
    print(
        "strategy_registry "
        f"scripts={summary.get('registered_scripts')} "
        f"families={summary.get('strategy_families')} "
        f"html={HTML_OUT}"
    )


if __name__ == "__main__":
    main()
