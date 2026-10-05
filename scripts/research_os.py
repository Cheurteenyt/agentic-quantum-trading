"""RESEARCH OS — la couche de séparation Discovery / Confirmation / Paper.

FIX audit GPT v3 (PR 1 de la séquence §203) : les fondations partagées par
le runner, lab_ledger et le preflight. Stdlib pure — aucune dépendance.

Les règles gravées (brief V3 §214) :
  TRAIN can be mined. VALIDATION cannot be mined adaptatively.
  HOLDOUT cannot be mined. PAPER cannot be retuned retroactively.

Le DataScope est l'objet qui REND CES RÈGLES EXÉCUTABLES : la vue discovery
ne porte même pas les bornes de la validation — le code de discovery ne
peut pas « faire attention », il ne peut pas voir.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Mode(str, Enum):
    """Les trois univers de recherche (brief V3 §128-130)."""

    DISCOVERY = "discovery"      # TRAIN only, budget scientifique illimité, jamais promote
    CONFIRMATION = "confirmation"  # pré-enregistré, protocole gelé, budget strict
    PAPER = "paper"              # flux d'observation, jamais de re-tuning rétroactif


class ExecState(str, Enum):
    """La machine d'états d'exécution d'une expérience (brief V3 §46)."""

    PLANNED = "planned"
    PREFLIGHT = "preflight"
    READY = "ready"
    RESERVED = "reserved"
    RUNNING = "running"
    SEALED = "sealed"
    VERIFIED = "verified"
    VERDICT = "verdict"
    # les sorties d'erreur — la politique de consommation diffère (§47)
    PREFLIGHT_FAILED = "preflight_failed"
    EXECUTION_FAILED_PRE_READ = "execution_failed_pre_read"
    EXECUTION_FAILED_POST_READ = "execution_failed_post_read"
    ABORTED = "aborted"


#: le slot de confirmation est-il consommé par cet état de sortie ?
#: (brief V3 §47 : PREFLIGHT_FAILED → 0 · POST_READ → 1 (INCONCLUSIVE) ·
#:  SEALED/VERIFIED/VERDICT → 1)
SLOT_CONSUMPTION: dict[str, int] = {
    ExecState.PREFLIGHT_FAILED.value: 0,
    ExecState.EXECUTION_FAILED_PRE_READ.value: 0,
    ExecState.EXECUTION_FAILED_POST_READ.value: 1,
    ExecState.SEALED.value: 1,
    ExecState.VERIFIED.value: 1,
    ExecState.VERDICT.value: 1,
}


def consumes_slot(state: "str | ExecState") -> bool:
    """La politique de consommation : un crash AVANT la lecture de la
    validation ne coûte rien ; après, le slot est consommé (INCONCLUSIVE)."""
    s = state.value if isinstance(state, ExecState) else str(state)
    return bool(SLOT_CONSUMPTION.get(s, 0))


class ScopeViolation(Exception):
    """Une requête a tenté d'accéder hors de la vue de données autorisée."""


@dataclass(frozen=True)
class DataView:
    """La tranche de données qu'UN mode a le droit de voir.

    Une vue discovery ne porte AUCUN champ de validation : le code qui la
    reçoit ne peut pas résoudre validation_start/end — la contrainte est
    structurelle, pas une consigne de prompt (brief V3 §8).
    """

    snapshot_id: str
    mode: str
    start_ms: int
    end_ms: int

    def assert_within(self, ts_ms: int) -> None:
        if not (self.start_ms <= ts_ms <= self.end_ms):
            raise ScopeViolation(
                f"{self.mode}: ts {ts_ms} hors de la vue "
                f"[{self.start_ms}, {self.end_ms}]")

    def assert_range(self, a_ms: int, b_ms: int) -> None:
        self.assert_within(a_ms)
        self.assert_within(b_ms)


@dataclass(frozen=True)
class DataScope:
    """Les fenêtres gelées d'un snapshot : train / validation / holdout.

    Les vues par mode sont la SEULE façon d'accéder aux données : le runner
    ne passe jamais un DataScope brut à la couche discovery.
    """

    snapshot_id: str
    train_start_ms: int
    train_end_ms: int
    validation_start_ms: int
    validation_end_ms: int
    holdout_start_ms: int | None = None
    holdout_end_ms: int | None = None

    def __post_init__(self):
        seq = [self.train_start_ms, self.train_end_ms,
               self.validation_start_ms, self.validation_end_ms]
        if self.holdout_start_ms is not None:
            seq += [self.holdout_start_ms, self.holdout_end_ms or 0]
        if any(b < a for a, b in zip(seq, seq[1:])):
            raise ValueError(f"DataScope incohérent (fenêtres non croissantes): {seq}")

    def discovery_view(self) -> DataView:
        """TRAIN ONLY — la validation y est structurellement invisible."""
        return DataView(self.snapshot_id, Mode.DISCOVERY.value,
                        self.train_start_ms, self.train_end_ms)

    def confirmation_view(self) -> tuple[DataView, DataView]:
        """Le couple (train, validation) du test confirmatoire gelé."""
        return (DataView(self.snapshot_id, Mode.CONFIRMATION.value,
                         self.train_start_ms, self.train_end_ms),
                DataView(self.snapshot_id, Mode.CONFIRMATION.value,
                         self.validation_start_ms, self.validation_end_ms))

    def paper_view(self) -> DataView:
        """Le flux d'observation : tout ce qui précède, jamais re-tuné."""
        end = self.holdout_end_ms if self.holdout_end_ms is not None \
            else self.validation_end_ms
        return DataView(self.snapshot_id, Mode.PAPER.value,
                        self.train_start_ms, end)


# ------------------------------------------------------------------ dedup
#: les verdicts de déduplication (brief V3 §4-6) — lab_ledger les applique
DUPLICATE, REPLICATION, NEW = "DUPLICATE", "REPLICATION", "NEW"


def dedup_verdict(mode: str, hyp_hash: str, param_hash: str, snapshot_id: str,
                  prior: list[dict]) -> str:
    """La sémantique de déduplication v3 (content-based, mode-aware).

    - même (hypothèse, params, snapshot, mode)            → DUPLICATE
    - même (hypothèse, params), snapshot différent        → REPLICATION (autorisé)
    - même (hypothèse, params, snapshot), mode différent  → NEW (la transition
      discovery → confirmation est TOUJOURS autorisée — c'est le but du système)

    `prior` : les essais déjà loggés, chacun avec mode/hh/ph/snapshot.
    """
    for p in prior:
        if (p.get("hh") == hyp_hash and p.get("ph") == param_hash
                and p.get("snapshot", "default") == snapshot_id
                and p.get("mode", Mode.CONFIRMATION.value) == mode):
            return DUPLICATE
    for p in prior:
        if (p.get("hh") == hyp_hash and p.get("ph") == param_hash
                and p.get("snapshot", "default") != snapshot_id):
            return REPLICATION
    return NEW
