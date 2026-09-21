from __future__ import annotations

from typing import Any


def _readiness_gate(name: str, current: float, target: float, blockers_for_gate: list[str]) -> dict[str, Any]:
    progress = round(min(100.0, (float(current or 0) / float(target or 1)) * 100), 2)
    return {
        "name": name,
        "current": current,
        "target": target,
        "progress_pct": progress,
        "passed": progress >= 100 and not blockers_for_gate,
        "blockers": blockers_for_gate,
    }


def _minimum_readiness_requirement(
    requirement_id: str,
    label_fr: str,
    current: float,
    target: float,
    unit: str,
    action_id: str,
) -> dict[str, Any]:
    current_value = round(float(current or 0), 4)
    target_value = round(float(target or 0), 4)
    missing = max(0.0, target_value - current_value)
    return {
        "id": requirement_id,
        "label_fr": label_fr,
        "direction": "minimum",
        "current": current_value,
        "target": target_value,
        "missing": round(missing, 4),
        "unit": unit,
        "passed": missing <= 0,
        "recommended_action_id": action_id,
    }


def _maximum_readiness_requirement(
    requirement_id: str,
    label_fr: str,
    current: float,
    target: float,
    unit: str,
    action_id: str,
) -> dict[str, Any]:
    current_value = round(float(current or 0), 4)
    target_value = round(float(target or 0), 4)
    excess = max(0.0, current_value - target_value)
    return {
        "id": requirement_id,
        "label_fr": label_fr,
        "direction": "maximum",
        "current": current_value,
        "target": target_value,
        "excess": round(excess, 4),
        "unit": unit,
        "passed": excess <= 0,
        "recommended_action_id": action_id,
    }


def _build_manipulation_research_verdict(metrics: dict[str, Any]) -> dict[str, Any]:
    """Research-only synthesis of manipulation evidence lanes."""
    evidence: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    score = 0
    confidence = 0

    def add_evidence(key: str, points: int, label_fr: str, detail: str, severity: str = "medium") -> None:
        nonlocal score
        score += points
        evidence.append({
            "key": key,
            "points": points,
            "severity": severity,
            "label_fr": label_fr,
            "detail": detail,
        })

    def add_missing(key: str, label_fr: str, why_it_matters_fr: str) -> None:
        missing.append({
            "key": key,
            "label_fr": label_fr,
            "why_it_matters_fr": why_it_matters_fr,
        })

    deposits = int(metrics.get("cex_token_deposit_rows") or 0)
    fresh_like = int(metrics.get("cex_token_fresh_like_depositors") or 0)
    shared_funders = int(metrics.get("cex_token_shared_funders") or 0)
    unknown_funders = int(metrics.get("cex_token_shared_unknown_funders") or 0)
    max_deposits_6h = int(metrics.get("cex_token_max_deposits_6h") or 0)
    max_deposits_24h = int(metrics.get("cex_token_max_deposits_24h") or 0)
    swap_rows = int(metrics.get("cex_token_swap_rows_around_deposits") or 0)
    swap_after = int(metrics.get("cex_token_swap_rows_after_24h") or 0)
    price_tokens = int(metrics.get("cex_token_price_proxy_before_after_tokens") or 0)
    price_change = float(metrics.get("cex_token_price_proxy_max_change_pct") or 0)
    holder_snapshots = int(metrics.get("cex_token_holder_supply_snapshot_tokens") or 0)
    high_cex_share = int(metrics.get("cex_token_holder_flow_high_cex_share_tokens") or 0)
    high_fresh_share = int(metrics.get("cex_token_holder_flow_high_fresh_like_share_tokens") or 0)
    high_top_holder = int(metrics.get("cex_token_holder_flow_high_top_holder_concentration_tokens") or 0)
    high_supply_share = int(metrics.get("cex_token_holder_flow_high_supply_share_tokens") or 0)
    max_supply_share = float(metrics.get("cex_token_holder_flow_max_supply_share_pct") or 0)
    coordination_score = int(metrics.get("cex_token_coordination_score") or 0)
    source_backed_targets = int(metrics.get("cex_token_source_backed_targets") or 0)
    deposit_targets = int(metrics.get("cex_token_deposit_targets") or 0)
    token_transfer_rows = int(metrics.get("token_transfer_rows") or 0)
    token_transfer_days = float(metrics.get("token_transfer_history_days") or 0)

    if deposits:
        add_evidence(
            "cex_token_deposits_observed",
            min(15, deposits * 3),
            "Depots token vers CEX observes",
            f"{deposits} depots token vers des wallets CEX locaux.",
            "high",
        )
    else:
        add_missing(
            "cex_token_deposits_missing",
            "Aucun depot token CEX observe",
            "Sans depot vers CEX, le scenario distribution/manipulation type LAB/RaveDAO n'est pas prouve localement.",
        )
    if max_deposits_6h >= 2 or max_deposits_24h >= 2:
        add_evidence(
            "clustered_cex_deposits",
            14 if max_deposits_6h >= 2 else 8,
            "Depots groupes dans le temps",
            f"Max {max_deposits_6h} depots/6h et {max_deposits_24h} depots/24h.",
            "high",
        )
    if fresh_like:
        add_evidence(
            "fresh_like_depositors",
            min(16, fresh_like * 4),
            "Wallets fresh-like impliques",
            f"{fresh_like} depositors fresh-like observes.",
            "high",
        )
    if shared_funders:
        add_evidence(
            "shared_funders",
            min(18, shared_funders * 9),
            "Funder partage",
            f"{shared_funders} funders financent plusieurs depositors.",
            "critical",
        )
    if unknown_funders:
        add_evidence(
            "shared_unknown_funders",
            min(14, unknown_funders * 7),
            "Funder partage non identifie",
            f"{unknown_funders} funders partages restent inconnus.",
            "critical",
        )
    if swap_rows:
        confidence += 15
        add_evidence(
            "swap_activity_around_deposits",
            min(10, swap_rows),
            "Swaps autour des depots",
            f"{swap_rows} swaps locaux autour des depots CEX.",
        )
    else:
        add_missing(
            "swap_context_missing",
            "Contexte swap manquant",
            "Il faut des swaps avant/apres pour separer distribution coordonnee et simple transfert.",
        )
    if swap_after:
        add_evidence(
            "post_deposit_swap_activity",
            min(8, swap_after * 2),
            "Activite apres depot",
            f"{swap_after} swaps locaux apres les depots.",
        )
    if price_tokens:
        confidence += 15
        add_evidence(
            "price_proxy_available",
            6,
            "Proxy prix avant/apres disponible",
            f"{price_tokens} tokens ont un proxy prix avant/apres depot.",
        )
    else:
        add_missing(
            "price_proxy_missing",
            "Proxy prix avant/apres manquant",
            "Sans proxy prix, le systeme ne sait pas encore si le flux precede ou suit un pump.",
        )
    if price_change >= 100:
        add_evidence(
            "large_positive_price_move",
            12,
            "Hausse forte apres fenetre",
            f"Proxy prix max +{round(price_change, 2)}%.",
            "high",
        )
    if holder_snapshots:
        confidence += 20
        add_evidence(
            "holder_supply_snapshot_available",
            8,
            "Snapshot holders/supply present",
            f"{holder_snapshots} tokens ont un snapshot holder/supply.",
        )
    elif deposits:
        add_missing(
            "holder_supply_snapshot_missing",
            "Snapshot holders/supply manquant",
            "Sans holders/supply, le score ne peut pas estimer correctement concentration et impact supply.",
        )
    if high_cex_share:
        add_evidence(
            "cex_share_of_observed_flow_high",
            min(8, high_cex_share * 4),
            "CEX domine le flow observe",
            f"{high_cex_share} tokens ont une forte part de flow vers CEX.",
            "high",
        )
    if high_fresh_share:
        add_evidence(
            "fresh_wallet_cex_value_share_high",
            min(8, high_fresh_share * 4),
            "Fresh wallets dominent la valeur CEX",
            f"{high_fresh_share} tokens ont une forte part fresh-like.",
            "high",
        )
    if high_top_holder:
        add_evidence(
            "top_holder_concentration_high",
            min(8, high_top_holder * 4),
            "Concentration top holder",
            f"{high_top_holder} tokens ont une concentration top holder elevee.",
            "critical",
        )
    if high_supply_share:
        add_evidence(
            "cex_deposit_supply_share_high",
            min(12, high_supply_share * 6),
            "Part supply envoyee vers CEX",
            f"Max {round(max_supply_share, 4)}% de supply estimee envoyee vers CEX.",
            "critical",
        )
    if source_backed_targets and source_backed_targets >= deposit_targets:
        confidence += 15
        add_evidence(
            "source_backed_cex_targets",
            6,
            "Cibles CEX source-backed",
            "Les wallets CEX cibles sont sources localement.",
        )
    elif deposits:
        add_missing(
            "cex_target_source_backing_incomplete",
            "Labels CEX incomplets",
            "Les wallets de destination doivent etre sources avant un signal client.",
        )
    if token_transfer_rows >= 500:
        confidence += 10
    else:
        add_missing(
            "token_transfer_history_shallow",
            "Historique Transfer logs insuffisant",
            "Les Transfer logs sont indispensables pour confirmer depots CEX et mouvements holders.",
        )
    if token_transfer_days >= 14:
        confidence += 10
    elif token_transfer_rows:
        add_missing(
            "token_transfer_window_short",
            "Fenetre Transfer logs trop courte",
            "Une fenetre courte peut transformer du bruit normal en faux signal.",
        )
    if coordination_score:
        score += min(20, round(coordination_score * 0.25))
    score = max(0, min(100, int(round(score))))
    confidence_score = max(0, min(100, confidence))
    if score >= 75:
        tier = "critical_research_case"
    elif score >= 55:
        tier = "strong_research_case"
    elif score >= 30:
        tier = "watchlist_research_case"
    else:
        tier = "insufficient_local_evidence"
    confidence_tier = "high" if confidence_score >= 70 else "medium" if confidence_score >= 40 else "low"
    direction = (
        "distribution_or_unlock_risk"
        if high_supply_share or high_top_holder or (deposits and max_supply_share >= 1)
        else "coordinated_wallet_activity_risk"
        if fresh_like or shared_funders or unknown_funders
        else "market_flow_watch_only"
        if deposits or swap_rows
        else "no_local_case"
    )
    return {
        "version": "manipulation-research-verdict-v1",
        "score": score,
        "tier": tier,
        "confidence_score": confidence_score,
        "confidence_tier": confidence_tier,
        "direction": direction,
        "evidence": evidence,
        "missing_evidence": missing,
        "client_action": "research_only",
        "client_execution_enabled": False,
        "copy_trade_enabled": False,
        "profit_guarantee_allowed": False,
        "plain_summary_fr": (
            "Cas prioritaire a investiguer: plusieurs preuves locales convergent, mais execution client interdite."
            if tier in {"critical_research_case", "strong_research_case"}
            else "Signal en watchlist recherche: il manque encore des preuves avant d'en faire un signal client."
            if tier == "watchlist_research_case"
            else "Pas assez de preuves locales pour conclure a une manipulation."
        ),
        "source_policy": (
            "read-only synthesis from existing readiness metrics, CEX token deposits, holder-flow, funding graph and swap/price proxies; "
            "no RPC calls, labels, cache writes or client execution are performed"
        ),
    }


def _build_holder_flow_evidence_verdict(metrics: dict[str, Any]) -> dict[str, Any]:
    """Compact holder-flow verdict for UI and admin review queues."""
    snapshot_tokens = int(metrics.get("cex_token_holder_supply_snapshot_tokens") or 0)
    flow_tokens = int(metrics.get("cex_token_holder_flow_tokens") or 0)
    max_cex_share = float(metrics.get("cex_token_holder_flow_max_cex_share_pct") or 0)
    max_fresh_share = float(metrics.get("cex_token_holder_flow_max_fresh_like_share_pct") or 0)
    max_top_holder = float(metrics.get("cex_token_holder_flow_max_top_holder_share_pct") or 0)
    max_top10_holder = float(metrics.get("cex_token_holder_flow_max_top10_holder_share_pct") or 0)
    max_supply_share = float(metrics.get("cex_token_holder_flow_max_supply_share_pct") or 0)
    risk_flags: list[str] = []
    if flow_tokens and not snapshot_tokens:
        risk_flags.append("holder_supply_snapshot_missing")
    if max_cex_share >= 50:
        risk_flags.append("high_cex_share_of_observed_flow")
    if max_fresh_share >= 50:
        risk_flags.append("high_fresh_like_cex_value_share")
    if max_top_holder >= 30:
        risk_flags.append("high_top_holder_concentration")
    if max_top10_holder >= 60:
        risk_flags.append("high_top10_holder_concentration")
    if max_supply_share >= 1:
        risk_flags.append("high_cex_deposit_supply_share")
    if not flow_tokens:
        state = "inconclusive"
        confidence = "low"
    elif not snapshot_tokens:
        state = "inconclusive"
        confidence = "low"
    elif any(flag in risk_flags for flag in [
        "high_top_holder_concentration",
        "high_top10_holder_concentration",
        "high_cex_deposit_supply_share",
    ]):
        state = "review_required"
        confidence = "medium"
    elif risk_flags:
        state = "watch_only"
        confidence = "medium"
    else:
        state = "watch_only"
        confidence = "low"
    return {
        "state": state,
        "confidence": confidence,
        "basis": {
            "source": "token_transfers + holders_cache_proxy",
            "tokens_profiled": flow_tokens,
            "holder_snapshot_tokens": snapshot_tokens,
            "holder_snapshot_available": snapshot_tokens > 0,
        },
        "scores": {
            "max_cex_share_pct": round(max_cex_share, 6),
            "max_fresh_like_pct": round(max_fresh_share, 6),
            "max_top_holder_pct": round(max_top_holder, 6),
            "max_top10_holder_pct": round(max_top10_holder, 6),
            "max_supply_share_pct": round(max_supply_share, 6),
        },
        "risk_flags": risk_flags,
        "recommended_action_id": (
            "refresh_holder_snapshot_if_needed"
            if "holder_supply_snapshot_missing" in risk_flags
            else "manual_holder_flow_review"
            if state == "review_required"
            else "watch_only"
        ),
        "client_execution_enabled": False,
        "copy_trade_enabled": False,
        "profit_guarantee_allowed": False,
        "plain_summary_fr": (
            "Snapshot holder manquant: le verdict reste inconclusif."
            if flow_tokens and not snapshot_tokens
            else "Concentration holder/supply a verifier manuellement."
            if state == "review_required"
            else "A surveiller uniquement; pas de preuve execution-grade."
        ),
        "source_policy": (
            "indicative holder-flow verdict from local token_transfers and cached holders only; "
            "not execution-grade and not proof of intent"
        ),
    }
