"""Store des resultats de backtest — les 6 regles data cablees dans le schema.

docs/06-data.md section 6. Chaque regle est appliquee par le SCHEMA ou par
`record()`, pas par la discipline de l'appelant :

  1. Ecrire les perdants      -> record() accepte les rejets ; c'est le chemin normal
  2. Identite obligatoire     -> NOT NULL + CHECK SQL, refus a l'insertion
  3. Blobs isoles             -> table `lane_blobs` separee, liee par identity_hash
  4. Schema versionne         -> schema_version NOT NULL sur chaque ligne
  5. Realise/latent separes   -> 2 colonnes, aucune vue ne les somme
  6. Denominateur conserve    -> table `runs` avec tested/accepted/rejected

Stdlib pure (sqlite3). Zero dependance : ce module ne doit jamais casser a
cause d'un upgrade de lib.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from . import SCHEMA_VERSION
from .gates import BenchmarkVerdict, GateVerdict

# Les 6 champs d'identite — docs/03-methodology.md section 2.5
IDENTITY_FIELDS = (
    "symbol",
    "interval",
    "side",
    "trigger",
    "execution_model",
    "leverage",
)


class IdentityError(ValueError):
    """Levee quand une lane n'a pas d'identite complete. Jamais rattrapee."""


@dataclass(frozen=True)
class LaneIdentity:
    """Identite canonique d'une lane. Immuable, validee a la construction."""

    symbol: str
    interval: str
    side: str
    trigger: str
    execution_model: str
    leverage: float

    def __post_init__(self) -> None:
        for f in IDENTITY_FIELDS[:-1]:
            v = getattr(self, f)
            if not isinstance(v, str) or not v.strip() or v.strip() == "?":
                raise IdentityError(
                    f"champ d'identite '{f}' vide ou invalide: {v!r} — "
                    "resultat non comparable, insertion refusee"
                )
        if self.leverage is None or self.leverage <= 0:
            raise IdentityError(f"leverage invalide: {self.leverage!r}")

    @property
    def key(self) -> str:
        return "|".join(
            [
                self.symbol,
                self.interval,
                self.side,
                self.trigger,
                self.execution_model,
                f"{self.leverage:g}",
            ]
        )

    @property
    def hash(self) -> str:
        return hashlib.sha1(self.key.encode()).hexdigest()[:16]


SCHEMA = """
PRAGMA foreign_keys = ON;

-- Regle 6 : le denominateur fait partie du resultat
CREATE TABLE IF NOT EXISTS runs (
    run_id              TEXT PRIMARY KEY,
    started_at          TEXT NOT NULL,
    finished_at         TEXT,
    schema_version      TEXT NOT NULL,
    gate_config_json    TEXT NOT NULL,
    gate_fingerprint    TEXT NOT NULL,
    data_snapshot_id    TEXT NOT NULL,
    tested              INTEGER NOT NULL DEFAULT 0,
    accepted            INTEGER NOT NULL DEFAULT 0,
    rejected            INTEGER NOT NULL DEFAULT 0,
    notes               TEXT
);

-- Regles 1, 2, 4, 5 : perdants persistes, identite NOT NULL, version, PnL separes
CREATE TABLE IF NOT EXISTS lanes (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id                  TEXT NOT NULL REFERENCES runs(run_id),
    schema_version          TEXT NOT NULL,
    recorded_at             TEXT NOT NULL,

    identity_hash           TEXT NOT NULL,
    identity_key            TEXT NOT NULL,
    symbol                  TEXT NOT NULL CHECK (length(trim(symbol)) > 0 AND symbol <> '?'),
    interval                TEXT NOT NULL CHECK (length(trim(interval)) > 0 AND interval <> '?'),
    side                    TEXT NOT NULL CHECK (side IN ('long','short','both')),
    trigger                 TEXT NOT NULL CHECK (length(trim(trigger)) > 0 AND trigger <> '?'),
    execution_model         TEXT NOT NULL CHECK (length(trim(execution_model)) > 0),
    leverage                REAL NOT NULL CHECK (leverage > 0),

    closed_trades           INTEGER,
    win_rate                REAL,
    sharpe_is               REAL,
    sharpe_oos              REAL,
    max_drawdown_pct        REAL,
    param_sensitivity       REAL,

    -- Regle 5 : jamais sommes, aucune vue ne les additionne
    pnl_realized_usd        REAL,
    pnl_unrealized_usd      REAL,

    -- Les 4 postes de cout, explicites
    fees_usd                REAL,
    funding_usd             REAL,
    slippage_usd            REAL,
    liquidation_checked     INTEGER NOT NULL DEFAULT 0,

    microstructure_validated INTEGER NOT NULL DEFAULT 0,

    -- Regle 1 : le verdict est une donnee de premier plan
    gate_passed             INTEGER NOT NULL,
    gate_primary_failure    TEXT,
    gate_failures           TEXT,
    gate_config_fingerprint TEXT NOT NULL,
    gate_detail_json        TEXT,

    bench_passed            INTEGER,
    bench_failures          TEXT,
    bench_detail_json       TEXT
);

-- Regle 3 : les blobs lourds hors de la table de metriques (96 % du volume legacy)
CREATE TABLE IF NOT EXISTS lane_blobs (
    lane_id     INTEGER PRIMARY KEY REFERENCES lanes(id) ON DELETE CASCADE,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_lanes_run      ON lanes(run_id);
CREATE INDEX IF NOT EXISTS ix_lanes_identity ON lanes(identity_hash);
CREATE INDEX IF NOT EXISTS ix_lanes_passed   ON lanes(gate_passed);
CREATE INDEX IF NOT EXISTS ix_lanes_failure  ON lanes(gate_primary_failure);

-- Vue de lecture : uniquement les survivants, denominateur attache
CREATE VIEW IF NOT EXISTS survivors AS
SELECT l.*, r.tested, r.accepted, r.rejected
FROM lanes l JOIN runs r ON r.run_id = l.run_id
WHERE l.gate_passed = 1 AND COALESCE(l.bench_passed, 0) = 1;

-- Vue d'analyse : la distribution des rejets, c'est ca l'information utile
CREATE VIEW IF NOT EXISTS rejection_profile AS
SELECT run_id,
       COALESCE(gate_primary_failure, 'passed') AS motif,
       COUNT(*)                                 AS n
FROM lanes GROUP BY run_id, motif;
"""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BacktestStore:
    """Store SQLite. Toute ecriture passe par record() ou finish_run()."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self.con.commit()

    # ------------------------------------------------------------------ runs

    def start_run(
        self,
        run_id: str,
        gate_config: dict[str, Any],
        gate_fingerprint: str,
        data_snapshot_id: str,
        notes: str | None = None,
    ) -> str:
        """`data_snapshot_id` identifie les donnees utilisees. Sans lui un run
        n'est pas reproductible — et un backtest non reproductible ne prouve rien."""
        if not data_snapshot_id or not data_snapshot_id.strip():
            raise ValueError(
                "data_snapshot_id obligatoire : un run sans provenance de donnees "
                "n'est pas reproductible"
            )
        self.con.execute(
            "INSERT INTO runs (run_id, started_at, schema_version, gate_config_json,"
            " gate_fingerprint, data_snapshot_id, notes) VALUES (?,?,?,?,?,?,?)",
            (
                run_id,
                _utc(),
                SCHEMA_VERSION,
                json.dumps(gate_config, sort_keys=True),
                gate_fingerprint,
                data_snapshot_id,
                notes,
            ),
        )
        self.con.commit()
        return run_id

    def finish_run(self, run_id: str) -> dict[str, int]:
        """Recalcule les compteurs depuis les lignes reelles — pas depuis un
        compteur tenu a la main qui peut deriver."""
        row = self.con.execute(
            "SELECT COUNT(*) tested,"
            " SUM(gate_passed = 1 AND COALESCE(bench_passed,0) = 1) accepted"
            " FROM lanes WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        tested = row["tested"] or 0
        accepted = row["accepted"] or 0
        self.con.execute(
            "UPDATE runs SET finished_at=?, tested=?, accepted=?, rejected=?"
            " WHERE run_id=?",
            (_utc(), tested, accepted, tested - accepted, run_id),
        )
        self.con.commit()
        return {"tested": tested, "accepted": accepted, "rejected": tested - accepted}

    # ----------------------------------------------------------------- lanes

    def record(
        self,
        run_id: str,
        identity: LaneIdentity,
        metrics: dict[str, Any],
        gate: GateVerdict,
        bench: BenchmarkVerdict | None = None,
        blob: dict[str, Any] | None = None,
    ) -> int:
        """Enregistre UNE lane, gagnante ou perdante.

        Regle 1 : appeler record() pour un rejet est le chemin NORMAL, pas une
        exception. Un moteur qui n'appelle record() que sur les gagnants
        reproduit exactement le biais de survivance du legacy.
        """
        cols = {
            "run_id": run_id,
            "schema_version": SCHEMA_VERSION,
            "recorded_at": _utc(),
            "identity_hash": identity.hash,
            "identity_key": identity.key,
            "symbol": identity.symbol,
            "interval": identity.interval,
            "side": identity.side,
            "trigger": identity.trigger,
            "execution_model": identity.execution_model,
            "leverage": identity.leverage,
            "gate_passed": int(gate.passed),
            "gate_primary_failure": gate.primary_failure.value if gate.primary_failure else None,
            "gate_failures": ",".join(g.value for g in gate.failures) or None,
            "gate_config_fingerprint": gate.config_fingerprint,
            "gate_detail_json": json.dumps(gate.detail, sort_keys=True) if gate.detail else None,
            "bench_passed": None if bench is None else int(bench.passed),
            "bench_failures": None
            if bench is None
            else (",".join(g.value for g in bench.failures) or None),
            "bench_detail_json": None
            if bench is None
            else (json.dumps(bench.detail, sort_keys=True) or None),
        }

        allowed = {
            "closed_trades", "win_rate", "sharpe_is", "sharpe_oos",
            "max_drawdown_pct", "param_sensitivity", "pnl_realized_usd",
            "pnl_unrealized_usd", "fees_usd", "funding_usd", "slippage_usd",
            "liquidation_checked", "microstructure_validated",
        }
        unknown = set(metrics) - allowed
        if unknown:
            raise ValueError(
                f"metriques inconnues: {sorted(unknown)} — "
                "ajoute la colonne au schema plutot que de la fourrer dans un blob"
            )
        for k in ("liquidation_checked", "microstructure_validated"):
            if k in metrics:
                metrics[k] = int(bool(metrics[k]))
        cols.update(metrics)

        names = ", ".join(cols)
        marks = ", ".join("?" * len(cols))
        cur = self.con.execute(
            f"INSERT INTO lanes ({names}) VALUES ({marks})", list(cols.values())
        )
        lane_id = int(cur.lastrowid)

        if blob:
            self.con.execute(
                "INSERT INTO lane_blobs (lane_id, payload_json) VALUES (?,?)",
                (lane_id, json.dumps(blob, sort_keys=True)),
            )
        self.con.commit()
        return lane_id

    # --------------------------------------------------------------- lecture

    def survivors(self, run_id: str | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM survivors"
        args: tuple = ()
        if run_id:
            sql += " WHERE run_id = ?"
            args = (run_id,)
        return self.con.execute(sql, args).fetchall()

    def rejection_profile(self, run_id: str) -> list[sqlite3.Row]:
        return self.con.execute(
            "SELECT motif, n FROM rejection_profile WHERE run_id = ? ORDER BY n DESC",
            (run_id,),
        ).fetchall()

    def run_summary(self, run_id: str) -> dict[str, Any]:
        """Resume publiable : jamais un chiffre sans son denominateur."""
        r = self.con.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        if r is None:
            raise KeyError(run_id)
        out = dict(r)
        out["rejection_profile"] = {
            row["motif"]: row["n"] for row in self.rejection_profile(run_id)
        }
        pnl = self.con.execute(
            "SELECT SUM(pnl_realized_usd) realized, SUM(pnl_unrealized_usd) unrealized"
            " FROM lanes WHERE run_id = ? AND gate_passed = 1",
            (run_id,),
        ).fetchone()
        # Regle 5 : deux cles distinctes, jamais un total
        out["pnl_realized_usd_survivors"] = pnl["realized"]
        out["pnl_unrealized_usd_survivors"] = pnl["unrealized"]
        return out

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> "BacktestStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
