"""Registre de candidats — le cycle de vie OOS postérieur à la campagne.

RÔLE (docs/03-methodology.md §2.2, §5) : un survivant de campagne N'EST PAS une
stratégie validée. C'est un *candidat* qui doit survivre à une période OOS
POSTÉRIEURE à la campagne — des données que personne n'avait au moment du test.
Le legacy a promu des lanes sur la même fenêtre qu'il les avait découvertes :
c'est réutiliser les données, donc du sur-ajustement.

Ce module gère ce cycle de vie strict :
    découverte (campagne) -> PENDING -> (délai réel obligatoire) ->
        évaluation sur données fraîches -> CONFIRMED | REJECTED
    PENDING jamais évalué après max_age_days -> EXPIRED (on ne garde pas
        éternellement un candidat qu'on n'a jamais pu tester).

Le schéma SQL DÉFEND (UNIQUE sur (identity_key, run_id), CHECK sur status), il
ne fait pas la discipline à la place de l'appelant : la logique de décision
(CONFIRMED vs REJECTED) vit dans `confirm()`.

Stdlib pure (sqlite3, dataclasses, datetime, enum). Zero dépendance : ce module
ne doit jamais casser à cause d'un upgrade de lib.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from scripts.research_os import load_confirmation_protocol

# L'AUTORITÉ UNIQUE des seuils de confirmation (ratifiée 2026-10-05,
# research/protocols/active.yaml) — plus aucun seuil codé en dur ici.
PROTOCOL = load_confirmation_protocol()


class CandidateStatus(str, Enum):
    """Statut d'un candidat. str pour sérialisation directe en SQL/JSON."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    EXPIRED = "expired"


class DuplicateCandidateError(ValueError):
    """Levée quand (identity_key, run_id) existe déjà.

    Le schéma a aussi un UNIQUE, mais on lève une erreur lisible plutôt que de
    laisser fuiter un IntegrityError brut à l'appelant.
    """


@dataclass
class Candidate:
    """Un survivant de campagne en attente de validation OOS postérieure.

    `discovered_at` et `evaluated_at` sont des chaînes ISO-8601 UTC (timespec
    à la seconde) — jamais de naive datetime, sinon l'âge est faux.
    """

    identity_key: str
    run_id: str
    discovered_at: str
    sharpe_oos_discovery: float
    n_tested_in_campaign: int
    params: dict
    status: str = "pending"
    forward_sharpe: float | None = None
    forward_trades: int | None = None
    evaluated_at: str | None = None
    decision_reason: str | None = None


SCHEMA = """
PRAGMA foreign_keys = ON;

-- Le schéma défend, pas la discipline :
--   UNIQUE (identity_key, run_id) -> un candidat = une ligne, pas de doublon
--   CHECK (status IN (...))        -> impossible d'injecter un statut fantaisie
CREATE TABLE IF NOT EXISTS candidates (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_key          TEXT NOT NULL,
    run_id                TEXT NOT NULL,
    discovered_at         TEXT NOT NULL,
    sharpe_oos_discovery  REAL NOT NULL,
    n_tested_in_campaign  INTEGER NOT NULL,
    params_json           TEXT NOT NULL,
    status                TEXT NOT NULL
                             CHECK (status IN ('pending','confirmed','rejected','expired')),
    forward_sharpe        REAL,
    forward_trades        INTEGER,
    evaluated_at          TEXT,
    decision_reason       TEXT,
    schema_version        TEXT NOT NULL,
    UNIQUE (identity_key, run_id)
);

CREATE INDEX IF NOT EXISTS ix_candidates_status       ON candidates(status);
CREATE INDEX IF NOT EXISTS ix_candidates_discovered   ON candidates(discovered_at);
"""


def _utc() -> str:
    """Horodatage UTC stable (timespec seconde), identique à store.py."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse(ts: str) -> datetime:
    """Parse une chaîne ISO en datetime UTC tolérante ('Z', offset, ou naive)."""
    s = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        # Naive = on suppose UTC : mieux qu'une erreur silencieuse d'âge.
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _age_days(ts: str, now: datetime | None = None) -> float:
    """Âge en jours d'un `discovered_at` relatif à `now` (défaut : maintenant)."""
    now = now or datetime.now(timezone.utc)
    return (now - _parse(ts)).total_seconds() / 86400.0


class CandidateRegistry:
    """Registre SQLite des candidats et de leur décision OOS."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        # Le dossier parent doit exister ; on le crée pour que l'appelant
        # n'ait pas à le faire (cohérent avec BacktestStore).
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        self.con.commit()

    # ------------------------------------------------------------- register

    def register(self, c: Candidate) -> int:
        """Inscrit un candidat. Lève DuplicateCandidateError sur doublon
        (identity_key, run_id). Lève sqlite3.IntegrityError si le statut est
        invalide — c'est le CHECK SQL qui défend, pas ce code.

        Retourne l'id de ligne (int).
        """
        # Double défense : on refuse proprement le doublon AVANT l'insert,
        # le UNIQUE SQL restant le filet de sécurité.
        existing = self.con.execute(
            "SELECT id FROM candidates WHERE identity_key=? AND run_id=?",
            (c.identity_key, c.run_id),
        ).fetchone()
        if existing is not None:
            raise DuplicateCandidateError(
                f"candidat deja enregistre: identity_key={c.identity_key!r} "
                f"run_id={c.run_id!r}"
            )
        cur = self.con.execute(
            "INSERT INTO candidates ("
            " identity_key, run_id, discovered_at, sharpe_oos_discovery,"
            " n_tested_in_campaign, params_json, status, schema_version"
            ") VALUES (?,?,?,?,?,?,?,?)",
            (
                c.identity_key,
                c.run_id,
                c.discovered_at,
                c.sharpe_oos_discovery,
                c.n_tested_in_campaign,
                json.dumps(c.params, sort_keys=True),
                c.status,
                SCHEMA_VERSION,
            ),
        )
        self.con.commit()
        return int(cur.lastrowid)

    # -------------------------------------------------------------- pending

    def pending(self, min_age_days: float = 0.0) -> list[Candidate]:
        """Retourne les candidats PENDING découverts il y a PLUS de
        `min_age_days` jours.

        Le filtre d'âge est le garde-fou anti-réutilisation : on n'évalue pas
        un candidat tant qu'une période OOS postérieure n'a pas eu le temps de
        s'écouler. `min_age_days=0` (défaut) renvoie tous les PENDING.
        """
        now = datetime.now(timezone.utc)
        rows = self.con.execute(
            "SELECT * FROM candidates WHERE status = ? ORDER BY discovered_at ASC",
            (CandidateStatus.PENDING.value,),
        ).fetchall()
        out: list[Candidate] = []
        for r in rows:
            if _age_days(r["discovered_at"], now) > min_age_days:
                out.append(self._row_to_candidate(r))
        return out

    # -------------------------------------------------------------- confirm

    def confirm(
        self,
        identity_key: str,
        run_id: str,
        forward_sharpe: float | None,
        forward_trades: int | None,
    ) -> str:
        """Applique la décision OOS et renvoie le nouveau statut ('confirmed'
        ou 'rejected').

        RÈGLES (le None = non mesuré = jamais un pass) :
          CONFIRMED seulement si TOUTES :
            forward_sharpe     >= PROTOCOL["forward_confirmation"]["min_forward_sharpe"]
            forward_trades     >= PROTOCOL["forward_confirmation"]["min_forward_trades"]
            forward_sharpe     >= PROTOCOL["forward_confirmation"]["min_vs_discovery"] * sharpe_oos_discovery
          Sinon REJECTED, avec `decision_reason` explicite.

        Lève KeyError si (identity_key, run_id) inconnu.
        """
        row = self.con.execute(
            "SELECT * FROM candidates WHERE identity_key=? AND run_id=?",
            (identity_key, run_id),
        ).fetchone()
        if row is None:
            raise KeyError(f"candidat inconnu: identity_key={identity_key!r} run_id={run_id!r}")

        status, reason = self._decide(
            forward_sharpe, forward_trades, row["sharpe_oos_discovery"]
        )
        self.con.execute(
            "UPDATE candidates SET status=?, forward_sharpe=?, forward_trades=?,"
            " evaluated_at=?, decision_reason=? WHERE identity_key=? AND run_id=?",
            (
                status,
                forward_sharpe,
                forward_trades,
                _utc(),
                reason,
                identity_key,
                run_id,
            ),
        )
        self.con.commit()
        return status

    @staticmethod
    def _decide(
        forward_sharpe: float | None,
        forward_trades: int | None,
        sharpe_oos_discovery: float,
    ) -> tuple[str, str]:
        """Pure décision : (statut, raison). Aucun accès DB, testable isolément."""
        # None = non mesuré = jamais un pass. On ne devine pas une mesure.
        if forward_sharpe is None or forward_trades is None:
            return (
                CandidateStatus.REJECTED.value,
                "mesure forward absente (None) : un candidat non mesure "
                "ne peut etre confirme",
            )
        if forward_sharpe < 0.5:
            return (
                CandidateStatus.REJECTED.value,
                f"forward_sharpe={forward_sharpe:.4g} < 0.5 : performance "
                f"forward insuffisante",
            )
        if forward_trades < 100:
            return (
                CandidateStatus.REJECTED.value,
                f"forward_trades={forward_trades} < 100 : echantillon forward "
                f"insuffisant pour conclure",
            )
        # Dégradation OOS/decouverte : un candidat qui s'effondre > 50% vs sa
        # découverte est overfitté, pas bon (docs/03 §3 : gate le plus discriminant).
        threshold = 0.5 * sharpe_oos_discovery
        if forward_sharpe < threshold:
            return (
                CandidateStatus.REJECTED.value,
                f"degradation OOS/decouverte : forward_sharpe={forward_sharpe:.4g} "
                f"< 0.5*sharpe_oos_discovery={threshold:.4g}",
            )
        return (
            CandidateStatus.CONFIRMED.value,
            "confirme : forward_sharpe>=0.5, forward_trades>=100, et "
            "degradation<=50% vs decouverte",
        )

    # ----------------------------------------------------------- expire_stale

    def expire_stale(self, max_age_days: float = 90.0) -> int:
        """Expire les candidats PENDING jamais évalués après `max_age_days`.

        Un candidat qu'on n'a pas pu tester en OOS dans le délai n'est pas une
        stratégie en attente indéfinie : il devient EXPIRED pour ne pas polluer
        le pool de PENDING. Retourne le nombre d'expirés.
        """
        now = datetime.now(timezone.utc)
        rows = self.con.execute(
            "SELECT identity_key, run_id, discovered_at FROM candidates "
            "WHERE status = ?",
            (CandidateStatus.PENDING.value,),
        ).fetchall()
        n = 0
        for r in rows:
            if _age_days(r["discovered_at"], now) > max_age_days:
                self.con.execute(
                    "UPDATE candidates SET status=?, decision_reason=? "
                    "WHERE identity_key=? AND run_id=?",
                    (
                        CandidateStatus.EXPIRED.value,
                        f"expire : aucune evaluation OOS apres {max_age_days:g} jours",
                        r["identity_key"],
                        r["run_id"],
                    ),
                )
                n += 1
        self.con.commit()
        return n

    # ---------------------------------------------------------------- stats

    def stats(self) -> dict[str, Any]:
        """Compte par statut + taux de confirmation.

        `confirmation_rate` = confirmed / (confirmed + rejected) : la fraction
        des candidats *décidés* qui ont été confirmés (EXPIRED et PENDING ne
        sont pas des décisions, ils ne comptent pas dans le dénominateur).
        """
        counts = {s.value: 0 for s in CandidateStatus}
        for row in self.con.execute(
            "SELECT status, COUNT(*) AS n FROM candidates GROUP BY status"
        ):
            counts[row["status"]] = row["n"]
        total = sum(counts.values())
        decided = counts[CandidateStatus.CONFIRMED.value] + counts[CandidateStatus.REJECTED.value]
        rate = (counts[CandidateStatus.CONFIRMED.value] / decided) if decided else 0.0
        return {
            CandidateStatus.PENDING.value: counts[CandidateStatus.PENDING.value],
            CandidateStatus.CONFIRMED.value: counts[CandidateStatus.CONFIRMED.value],
            CandidateStatus.REJECTED.value: counts[CandidateStatus.REJECTED.value],
            CandidateStatus.EXPIRED.value: counts[CandidateStatus.EXPIRED.value],
            "total": total,
            "confirmation_rate": rate,
        }

    # ---------------------------------------------------------------- utils

    def _row_to_candidate(self, row: sqlite3.Row) -> Candidate:
        return Candidate(
            identity_key=row["identity_key"],
            run_id=row["run_id"],
            discovered_at=row["discovered_at"],
            sharpe_oos_discovery=row["sharpe_oos_discovery"],
            n_tested_in_campaign=row["n_tested_in_campaign"],
            params=json.loads(row["params_json"]),
            status=row["status"],
            forward_sharpe=row["forward_sharpe"],
            forward_trades=row["forward_trades"],
            evaluated_at=row["evaluated_at"],
            decision_reason=row["decision_reason"],
        )

    def close(self) -> None:
        self.con.close()

    def __enter__(self) -> "CandidateRegistry":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = [
    "CandidateStatus",
    "Candidate",
    "CandidateRegistry",
    "DuplicateCandidateError",
]
