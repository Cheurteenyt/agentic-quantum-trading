"""Mise en rapport d'une campagne — rendre le mensonge visible, pas le maquiller.

Ce module ne calcule aucune statistique nouvelle. Il prend le resultat brut
d'une campagne (`CampaignReport.as_dict()`) et, si disponible, son audit de
multiplicite (`CampaignAudit`), et produit un texte lisible a 8h du matin par
un humain fatigue.

Regle unique et non negociable : **jamais un chiffre sans son denominateur**.
Le pipeline legacy affichait "+924 828 USD" et "105 357 lanes rentables". Les
deux chiffres etaient vrais. Les deux etaient des mensonges, parce que leur
denominateur (1 117 620 combinaisons testees, dont seules les gagnantes etaient
ecrites) etait absent. Ce module rend ce type d'affichage impossible : toute
quantite passe par `_ratio()`, qui refuse de formatter sans denominateur.

Stdlib pure (json, datetime, textwrap). Pas de jinja2, pas de pandas.
"""
from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

__all__ = [
    "ReportSection",
    "build_report",
    "render_markdown",
    "render_console",
    "render_discord",
    "health_flags",
]

# --------------------------------------------------------------------------
# Seuils. Ils sont ici, nommes, et pas enfouis dans une condition.
# --------------------------------------------------------------------------

SUSPICIOUS_ACCEPTANCE_RATE = 0.05
"""Au-dela de 5 % d'acceptation, le nombre de survivants est du meme ordre que
ce qu'un generateur aleatoire produirait a alpha=5 %. Ce n'est pas une preuve
de fraude, c'est une absence de preuve de signal."""

HIGH_ERROR_RATE = 0.10
"""Au-dela de 10 % d'erreurs, le denominateur reel de la campagne n'est plus
celui qu'on croit : on ne sait pas ce que les combinaisons plantees auraient
donne, donc les taux affiches sont biaises d'une facon inconnue."""

LARGE_CAMPAIGN_TESTED = 50
"""A partir de ~50 essais, la probabilite d'obtenir un faux positif a 5 % est
superieure a 90 %. Sans correction de multiplicite, tout resultat est ininterpretable."""

SEVERITY_ORDER = {"critical": 0, "warning": 1, "info": 2}

_CRITICAL_MARKERS = (
    "TAUX D'ACCEPTATION SUSPECT",
    "CAMPAGNE NON CORRIGEE DE LA MULTIPLICITE",
    "CAMPAGNE NON CORRIGÉE DE LA MULTIPLICITÉ",
    "INCOHERENCE",
)
_WARNING_MARKERS = (
    "TAUX D'ERREUR ELEVE",
    "TAUX D'ERREUR ÉLEVÉ",
    "CAMPAGNE VIDE",
    "AUCUNE LANE MESURABLE",
)


@dataclass
class ReportSection:
    """Un bloc de rapport : un titre, des lignes deja formatees, une gravite.

    `severity` vaut 'info', 'warning' ou 'critical'. 'critical' est reserve a
    ce qui peut faire perdre de l'argent si on le lit de travers.
    """

    title: str
    lines: list[str] = field(default_factory=list)
    severity: str = "info"

    def __post_init__(self) -> None:
        if self.severity not in SEVERITY_ORDER:
            raise ValueError(
                f"severity invalide: {self.severity!r} "
                f"(attendu: {sorted(SEVERITY_ORDER)})"
            )
        self.lines = list(self.lines)


# --------------------------------------------------------------------------
# Formatage — le coeur de la regle du denominateur
# --------------------------------------------------------------------------


def _fr(value: float, decimals: int = 1) -> str:
    """Formatte un nombre a la francaise (virgule decimale)."""
    return f"{value:.{decimals}f}".replace(".", ",")


def _ratio(numerator: float, denominator: float, unit: str = "") -> str:
    """Rend "n / d (x,y%)". Le denominateur n'est PAS optionnel.

    C'est la seule facon d'ecrire une quantite dans ce module. Un appelant qui
    n'a pas de denominateur n'a pas de chiffre publiable : il a une anecdote.
    """
    suffix = f" {unit}" if unit else ""
    if not denominator:
        # Denominateur nul : on le dit, on n'invente pas un pourcentage.
        return f"{numerator:g}{suffix} / 0 (denominateur nul — taux indefini)"
    pct = 100.0 * numerator / denominator
    return f"{numerator:g}{suffix} / {denominator:g} ({_fr(pct, 1)} %)"


def _get_rate(campaign: dict) -> float:
    """Taux d'acceptation, recalcule si absent — jamais devine."""
    tested = int(campaign.get("tested") or 0)
    if "acceptance_rate" in campaign and campaign["acceptance_rate"] is not None:
        return float(campaign["acceptance_rate"])
    accepted = int(campaign.get("accepted") or 0)
    return (accepted / tested) if tested else 0.0


def _flag_severity(flag: str) -> str:
    """Classe un flag. Tout ce qui peut couter de l'argent est 'critical'."""
    for marker in _CRITICAL_MARKERS:
        if marker in flag:
            return "critical"
    for marker in _WARNING_MARKERS:
        if marker in flag:
            return "warning"
    return "info"


# --------------------------------------------------------------------------
# Diagnostic
# --------------------------------------------------------------------------


def health_flags(campaign: dict, audit: dict | None = None) -> list[str]:
    """Alertes de sante d'une campagne, en clair, avec les denominateurs.

    Renvoie une liste de phrases. Une liste vide ne veut pas dire "tout va
    bien" : elle veut dire "aucun des pieges connus n'a ete detecte".
    """
    flags: list[str] = []
    tested = int(campaign.get("tested") or 0)
    accepted = int(campaign.get("accepted") or 0)
    errored = int(campaign.get("errored") or 0)
    rate = _get_rate(campaign)

    if tested <= 0:
        flags.append(
            "CAMPAGNE VIDE : 0 combinaison testee — aucun chiffre de ce rapport "
            "n'a de denominateur, donc aucun n'est interpretable."
        )
        return flags

    if rate > SUSPICIOUS_ACCEPTANCE_RATE:
        flags.append(
            "TAUX D'ACCEPTATION SUSPECT : compatible avec du bruit pur — "
            + _ratio(accepted, tested, "acceptees")
            + f" alors qu'un tirage aleatoire a alpha={_fr(SUSPICIOUS_ACCEPTANCE_RATE * 100, 0)} % "
            f"en produirait deja {_ratio(SUSPICIOUS_ACCEPTANCE_RATE * tested, tested)}."
        )

    if errored / tested > HIGH_ERROR_RATE:
        flags.append(
            "TAUX D'ERREUR ELEVE : "
            + _ratio(errored, tested, "erreurs")
            + " — les combinaisons plantees n'ont pas de resultat, donc les taux "
            "ci-dessus portent sur un denominateur incomplet."
        )

    if audit is None:
        if tested >= LARGE_CAMPAIGN_TESTED:
            flags.append(
                "CAMPAGNE NON CORRIGEE DE LA MULTIPLICITE : "
                + _ratio(tested, tested, "essais")
                + " sans audit — a ce volume, obtenir un « gagnant » par hasard "
                "est l'issue la plus probable. Lancer audit_campaign() avant "
                "toute decision."
            )
        else:
            flags.append(
                "Audit de multiplicite absent (campagne de "
                + _ratio(tested, tested, "essais")
                + "). Sous le seuil de "
                f"{LARGE_CAMPAIGN_TESTED} essais, mais la correction reste "
                "recommandee avant tout passage en live."
            )
    else:
        n_gate = int(audit.get("n_gate_survivors") or 0)
        n_after = int(audit.get("n_after_multiplicity") or 0)
        if n_gate > 0 and n_after == 0:
            # Flag rassurant, volontairement : c'est le systeme qui fonctionne.
            flags.append(
                "AUCUN SURVIVANT APRES CORRECTION DE MULTIPLICITE : "
                + _ratio(n_gate, tested, "lanes passaient les gates")
                + f", 0 / {n_gate} survit a la correction. C'est le comportement "
                "attendu : les gates filtrent une lane, la multiplicite juge la "
                "campagne. Aucune perte d'argent possible ici."
            )
        if audit.get("verdict"):
            flags.append(f"Verdict d'audit : {audit['verdict']}")

    return flags


# --------------------------------------------------------------------------
# Construction du rapport
# --------------------------------------------------------------------------


def _section_header(campaign: dict) -> ReportSection:
    tested = int(campaign.get("tested") or 0)
    started = campaign.get("started_at") or "?"
    finished = campaign.get("finished_at") or "?"
    lines = [
        f"run_id      : {campaign.get('run_id') or '(sans identifiant)'}",
        f"debut       : {started}",
        f"fin         : {finished}",
        f"duree       : {_duration(started, finished)}",
        f"testees     : {_ratio(tested, tested, 'combinaisons')}",
    ]
    return ReportSection(title="Campagne", lines=lines, severity="info")


def _duration(started: str, finished: str) -> str:
    """Duree lisible, ou une mention explicite si non calculable."""
    try:
        t0 = datetime.fromisoformat(started)
        t1 = datetime.fromisoformat(finished)
    except (TypeError, ValueError):
        return "inconnue (horodatage absent ou invalide)"
    secs = (t1 - t0).total_seconds()
    if secs < 0:
        return "incoherente (fin anterieure au debut)"
    if secs < 60:
        return f"{_fr(secs, 0)} s"
    return f"{_fr(secs / 60.0, 1)} min"


def _section_counts(campaign: dict) -> ReportSection:
    tested = int(campaign.get("tested") or 0)
    accepted = int(campaign.get("accepted") or 0)
    rejected = int(campaign.get("rejected") or 0)
    errored = int(campaign.get("errored") or 0)
    lines = [
        f"acceptees   : {_ratio(accepted, tested)}",
        f"rejetees    : {_ratio(rejected, tested)}",
        f"erreurs     : {_ratio(errored, tested)}",
    ]
    accounted = accepted + rejected + errored
    if tested and accounted != tested:
        lines.append(
            "INCOHERENCE : "
            + _ratio(accounted, tested, "combinaisons comptabilisees")
            + " — la somme acceptees+rejetees+erreurs ne retombe pas sur le total."
        )
    severity = "critical" if (tested and accounted != tested) else "info"
    return ReportSection(title="Comptage", lines=lines, severity=severity)


def _section_health(campaign: dict, audit: dict | None) -> ReportSection | None:
    flags = health_flags(campaign, audit)
    if not flags:
        return None
    severity = "info"
    for f in flags:
        s = _flag_severity(f)
        if SEVERITY_ORDER[s] < SEVERITY_ORDER[severity]:
            severity = s
    lines = [f"[{_flag_severity(f).upper()}] {f}" for f in flags]
    return ReportSection(title="Sante de la campagne", lines=lines, severity=severity)


def _section_rejections(campaign: dict) -> ReportSection | None:
    profile = campaign.get("rejection_profile") or {}
    if not profile:
        return None
    tested = int(campaign.get("tested") or 0)
    total_motifs = sum(int(v) for v in profile.values())
    lines = [
        "Un rejet peut cumuler plusieurs motifs : le total ci-dessous peut "
        "depasser le nombre de combinaisons rejetees.",
        "",
    ]
    for motif, n in sorted(profile.items(), key=lambda kv: (-int(kv[1]), kv[0])):
        lines.append(f"{motif:<34} {_ratio(int(n), tested)}")
    lines.append("")
    lines.append(f"total motifs : {_ratio(total_motifs, tested, 'occurrences')}")
    return ReportSection(title="Motifs de rejet", lines=lines, severity="info")


def _section_multiplicity(campaign: dict, audit: dict | None) -> ReportSection:
    tested = int(campaign.get("tested") or 0)
    if audit is None:
        return ReportSection(
            title="Correction de multiplicite",
            lines=[
                "ABSENTE. Aucune correction n'a ete appliquee a cette campagne de "
                + _ratio(tested, tested, "essais")
                + ".",
                "Sans correction, le meilleur resultat d'une campagne est par "
                "construction le tirage le plus chanceux, pas la meilleure strategie.",
            ],
            severity="critical" if tested >= LARGE_CAMPAIGN_TESTED else "warning",
        )

    n_audit = int(audit.get("n_tested") or tested or 0)
    n_gate = int(audit.get("n_gate_survivors") or 0)
    n_after = int(audit.get("n_after_multiplicity") or 0)
    expected = float(audit.get("expected_by_chance") or 0.0)
    lines = [
        f"essais audites          : {_ratio(n_audit, n_audit, 'essais')}",
        f"passent les gates       : {_ratio(n_gate, n_audit)}",
        f"survivent a la corr.    : {_ratio(n_after, n_audit)}",
        f"attendus par hasard     : {_ratio(expected, n_audit)}",
        f"verdict                 : {audit.get('verdict') or '(absent)'}",
    ]
    if n_gate and n_gate <= expected:
        lines.append(
            "Le nombre de lanes passant les gates est INFERIEUR OU EGAL a ce que "
            "le hasard produirait : aucun signal detectable."
        )
    for k, v in (audit.get("detail") or {}).items():
        lines.append(f"{k:<24}: {v}")
    severity = "warning" if n_after == 0 else "info"
    return ReportSection(
        title="Correction de multiplicite", lines=lines, severity=severity
    )


def _fmt_num(value: Any, decimals: int = 2) -> str:
    if value is None:
        return "n/d"
    try:
        return _fr(float(value), decimals)
    except (TypeError, ValueError):
        return str(value)


def _section_survivors(campaign: dict, top_n: int) -> ReportSection:
    tested = int(campaign.get("tested") or 0)
    survivors = list(campaign.get("survivors") or [])
    if not survivors:
        return ReportSection(
            title="Survivants",
            lines=[
                "AUCUN SURVIVANT : " + _ratio(0, tested, "combinaisons"),
                "",
                "Ce n'est pas un echec de la campagne : c'est son resultat.",
                "Une campagne qui ne trouve rien a produit une information exacte "
                "et gratuite. Une campagne qui trouve beaucoup, a ce niveau de "
                "test, produit surtout des faux positifs payants.",
            ],
            severity="info",
        )

    shown = survivors[:top_n]
    lines = [
        "Un survivant est un CANDIDAT, pas une strategie validee : il doit etre "
        "reevalue sur des donnees posterieures a la campagne.",
        "",
        "affiches : " + _ratio(len(shown), len(survivors), "survivants"),
        "survivants : " + _ratio(len(survivors), tested),
        "",
    ]
    for i, s in enumerate(shown, start=1):
        lines.append(
            f"{i:>2}. {s.get('identity', '(identite absente)')}"
            f" | sharpe_oos={_fmt_num(s.get('sharpe_oos'))}"
            f" | oos/is={_fmt_num(s.get('oos_is_ratio'))}"
            f" | trades={s.get('closed_trades', 'n/d')}"
        )
    if len(survivors) > len(shown):
        lines.append(
            f"... {_ratio(len(survivors) - len(shown), len(survivors), 'non affiches')}"
        )
    return ReportSection(title="Survivants", lines=lines, severity="info")


def _section_candidates(candidates: dict, campaign: dict) -> ReportSection | None:
    """Section libre : tout dict fourni est rendu en JSON indente.

    On ne suppose rien de sa forme — mais on rappelle son denominateur, sinon
    l'appelant reintroduit exactement le biais qu'on combat.
    """
    if not candidates:
        return None
    tested = int(campaign.get("tested") or 0)
    body = json.dumps(candidates, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    lines = [
        "Contexte : " + _ratio(len(candidates), tested, "cles de candidats"),
        "",
    ]
    lines.extend(body.splitlines())
    return ReportSection(title="Candidats", lines=lines, severity="info")


def build_report(
    *,
    campaign: dict,
    audit: dict | None = None,
    candidates: dict | None = None,
    top_n: int = 10,
) -> list[ReportSection]:
    """Assemble les sections d'un rapport de campagne, gravite decroissante.

    Les sections `critical` remontent en premier : a 8h du matin, on lit la
    premiere section et on s'arrete. Elle doit donc contenir ce qui peut
    couter de l'argent.
    """
    if top_n < 0:
        raise ValueError("top_n doit etre >= 0")

    sections: list[ReportSection | None] = [
        _section_health(campaign, audit),
        _section_header(campaign),
        _section_counts(campaign),
        _section_multiplicity(campaign, audit),
        _section_survivors(campaign, top_n),
        _section_rejections(campaign),
        _section_candidates(candidates or {}, campaign),
    ]
    kept = [s for s in sections if s is not None]

    # Tri STABLE : a gravite egale, l'ordre de construction est conserve.
    kept.sort(key=lambda s: SEVERITY_ORDER[s.severity])
    return kept


# --------------------------------------------------------------------------
# Rendus
# --------------------------------------------------------------------------

_BADGE = {"critical": "[CRITIQUE]", "warning": "[ALERTE]", "info": "[INFO]"}


def render_markdown(sections: list[ReportSection]) -> str:
    """Markdown : un `##` par section, corps en bloc de code pour l'alignement."""
    if not sections:
        return "# Rapport de campagne\n\n_Aucune section._\n"
    out = ["# Rapport de campagne", ""]
    for s in sections:
        out.append(f"## {_BADGE[s.severity]} {s.title}")
        out.append("")
        out.append("```text")
        out.extend(s.lines or ["(vide)"])
        out.append("```")
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_console(sections: list[ReportSection], width: int = 78) -> str:
    """Rendu terminal, replie a `width` colonnes."""
    if width < 20:
        raise ValueError("width doit etre >= 20")
    out: list[str] = []
    for s in sections:
        out.append("=" * width)
        title = f"{_BADGE[s.severity]} {s.title}"
        out.append(title[:width])
        out.append("=" * width)
        for line in s.lines or ["(vide)"]:
            if not line:
                out.append("")
                continue
            out.extend(
                textwrap.wrap(
                    line,
                    width=width,
                    subsequent_indent="    ",
                    break_long_words=False,
                    break_on_hyphens=False,
                )
                or [""]
            )
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def render_discord(sections: list[ReportSection], max_chars: int = 1900) -> list[str]:
    """Decoupe le markdown en messages Discord (< 2000 caracteres).

    Invariant : un bloc ``` n'est jamais coupe en deux. Si la coupure tombe
    dedans, le bloc est ferme dans le message courant et rouvert dans le
    suivant — sinon Discord affiche du texte brut illisible, et un rapport
    illisible est un rapport non lu.
    """
    if max_chars < 100:
        raise ValueError("max_chars doit etre >= 100")

    raw = render_markdown(sections).split("\n")

    # Aucune ligne ne doit a elle seule depasser le budget d'un message.
    lines: list[str] = []
    hard = max_chars - 20
    for line in raw:
        if len(line) <= hard:
            lines.append(line)
        else:
            lines.extend(textwrap.wrap(line, width=hard) or [""])

    messages: list[str] = []
    cur: list[str] = []
    fence: str | None = None  # ligne d'ouverture du bloc en cours, sinon None

    def cur_len(extra: str | None = None) -> int:
        parts = cur + ([extra] if extra is not None else [])
        return len("\n".join(parts))

    for line in lines:
        # +4 : marge pour la ligne de fermeture "```" eventuelle.
        closing_cost = 4 if fence else 0
        if cur and cur_len(line) + closing_cost > max_chars:
            if fence:
                cur.append("```")
            messages.append("\n".join(cur).strip("\n"))
            cur = [fence] if fence else []
        cur.append(line)
        if line.startswith("```"):
            fence = None if fence else line

    if fence:
        cur.append("```")
    tail = "\n".join(cur).strip("\n")
    if tail:
        messages.append(tail)
    return [m for m in messages if m.strip()]
