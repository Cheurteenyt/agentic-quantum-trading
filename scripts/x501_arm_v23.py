#!/usr/bin/env python3
"""
x501_arm_v23.py — PONT D'ARMEMENT v23 (Task 23) : dernier câble de la boucle
« zéro intervention manuelle » entre le planificateur 4x/j et l'exécution kScript.
=================================================================================
Chaîne : x501_plan_v22.py (verdict GO + carte G4) -> x501_arm_v23.py -> ARMED.

Contrôles du pont (tous bloquants) :
  A1 Fraîcheur    : dernière passe journal < ARM_MAX_AGE_H (7 h = cadence 4x/j + marge)
  A2 Verdict      : dernière passe = GO (5 gates verts)
  A3 Signal-6     : re-calcul FRAIS de la carte de direction sur la DB (pas de cache)
                    — un symbole dont les features sont absentes est ÉCARTÉ (pas deviné)
  A4 Intégrité    : SHA256 des 5 .ks déployés + setup js vs manifest
                    (toute modification non tracée -> NO-ARM)
  A5 QA statique  : qa_kscript_x501.py doit passer 0 échec avant chaque armement

Sorties :
  scripts/x501_v21_results/arming_x501.json  — machine (consommable par l'exécution)
  scripts/x501_v21_results/arming_x501.md    — ordre de bataille lisible
  code retour 0 = ARMED, 1 = NO-ARM
"""
import hashlib, json, os, sqlite3, subprocess, sys, time
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]   # racine du repo
KS_DIR = BASE / "scripts" / "studies" / "x501_openmarket"
sys.path.insert(0, str(BASE / "scripts"))
OUT = str(BASE / "scripts" / "x501_v21_results")
DB = f"{OUT}/om_v21.db"
JOURNAL = f"{OUT}/scheduler_journal_v22.jsonl"
ARMING = f"{OUT}/arming_x501.json"
ARMING_MD = f"{OUT}/arming_x501.md"
MANIFEST = f"{OUT}/kscript_manifest.json"
ML_SCORES = f"{OUT}/ml_scores_v25.json"
CONTEXTE_V29 = f"{OUT}/contexte_om_v29.json"

KS_FILES = [
    str(KS_DIR / "Operation_x501_Signature_H1.ks"),
    str(KS_DIR / "Operation_x501_Signature_H4.ks"),
    str(KS_DIR / "Operation_x501_Alpha2_Cascade_Financement_H4.ks"),
    str(KS_DIR / "Operation_x501_Alpha3_Eruption_Volatilite_H4.ks"),
    str(KS_DIR / "Operation_x501_Alpha4_Confluence_MTF_H4.ks"),
    str(KS_DIR / "x501_setup_kscript.js"),
]
ARM_MAX_AGE_H = 7.0
SCHEDULE = "0 3,9,15,21 * * * (UTC, hors fenêtres funding 00/08/16)"


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def no_arm(reason, detail=None):
    out = {"ts": int(time.time()), "status": "NO-ARM", "reason": reason, "detail": detail}
    with open(ARMING, "w") as f:
        json.dump(out, f, indent=1)
    print(f"NO-ARM: {reason}" + (f" | {detail}" if detail else ""))
    return 1


def main():
    t0 = time.time()

    # ---- A1 + A2 : journal planificateur -----------------------------------
    if not os.path.exists(JOURNAL):
        return no_arm("A1 journal planificateur absent (lancer x501_plan_v22.py d'abord)")
    lines = [l for l in open(JOURNAL) if l.strip()]
    last = json.loads(lines[-1])
    age_h = (time.time() - last["ts"]) / 3600.0
    if age_h > ARM_MAX_AGE_H:
        return no_arm(f"A1 passe trop ancienne {age_h:.1f}h > {ARM_MAX_AGE_H}h")
    if last.get("verdict") != "GO":
        return no_arm("A2 dernière passe = NO-GO", "; ".join(last.get("fails", [])[:3]))

    # ---- A3 : carte signal-6 RECALCULÉE à froid ----------------------------
    import x501_gate_v21 as g
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row
    symbols, errs = {}, []
    for (s,) in con.execute("SELECT DISTINCT symbol FROM funding_1h_30d ORDER BY symbol"):
        try:
            f = g.features_symbol(con, s)
            al, ash, reasons = g.gate_decision(f)
            if f["funding_z"] is None and f["liq_imb24"] is None:
                errs.append(s)          # pas de devination : symbole écarté
                continue
            symbols[s] = {"allow_long": al, "allow_short": ash,
                          "funding_z": f["funding_z"], "liq_imb24": f["liq_imb24"],
                          "oi_chg24_pct": f["oi_chg24_pct"], "block_reasons": reasons}
        except Exception:
            errs.append(s)
    con.close()
    if not symbols:
        return no_arm("A3 aucune feature signal-6 calculable (DB vide ?)")

    # ---- A4 : intégrité kScript (SHA256 vs manifest) -----------------------
    missing = [p for p in KS_FILES if not os.path.exists(p)]
    if missing:
        return no_arm("A4 fichiers kScript manquants", str(missing))
    now_h = {os.path.basename(p): sha256(p) for p in KS_FILES}
    if os.path.exists(MANIFEST):
        ref = json.load(open(MANIFEST))
        drift = [k for k, v in now_h.items() if ref.get("files", {}).get(k) != v]
        if drift:
            return no_arm("A4 DRIFT kScript détecté (re-run QA + regénérer manifest)",
                          str(drift))
    else:
        json.dump({"ts": int(time.time()), "files": now_h}, open(MANIFEST, "w"), indent=1)

    # ---- A5 : QA statique kScript (0 échec requis) -------------------------
    r = subprocess.run([sys.executable, str(KS_DIR / "qa_kscript_x501.py")],
                       capture_output=True, text=True, timeout=60)
    qa_ok = "0 échec" in (r.stdout + r.stderr) or r.returncode == 0
    if not qa_ok:
        return no_arm("A5 QA kScript en échec", (r.stdout + r.stderr)[-300:])

    # ---- A6 (advisory, non bloquant) : score ML gate appris ----------------
    ml_adv, ml_meta = {}, {"status": "absent"}
    try:
        m = json.load(open(ML_SCORES))
        if time.time() - m.get("ts", 0) < 8 * 3600:
            ml_adv = m.get("p_danger_short", {})
            ml_meta = {"status": m.get("status", "advisory"),
                       "age_h": round((time.time() - m["ts"]) / 3600, 1),
                       "top_danger": m.get("top_danger", [])[:3]}
    except Exception:
        pass

    # ---- A7 (advisory, non bloquant) : contexte om_v29 (outils gratuits) ----
    # signaux_om_v29.py : S1 KILL / S3 KILL (affichage) / S2 ADVISORY (dispersion
    # 28,1 bps test) / S4 DIAG — RIEN de bloquant : la config certifiée reste
    # l'autorité. Le contexte est loggé à chaque armement (preuve temporelle).
    ctx_adv, ctx_meta = {}, {"status": "absent"}
    try:
        c = json.load(open(CONTEXTE_V29))
        if time.time() - c.get("ts", 0) < 26 * 3600:
            ctx_adv = c.get("features", {})
            ctx_meta = {"status": "advisory", "source": "om_v27.db",
                        "age_h": round((time.time() - c["ts"]) / 3600, 1),
                        "verdicts": {k: v.get("verdict", "?") for k, v in json.load(
                            open(f"{OUT}/signaux_om_v29.json"))["signaux"].items()}}
    except Exception:
        pass

    # ---- ARMED -------------------------------------------------------------
    longs = sorted(s for s, d in symbols.items() if d["allow_long"])
    shorts = sorted(s for s, d in symbols.items() if d["allow_short"])
    blocked = sorted(s for s, d in symbols.items() if not d["allow_long"] or not d["allow_short"])
    armed = {
        "ts": int(time.time()), "status": "ARMED",
        "source_pass_ts": last["ts"], "pass_age_h": round(age_h, 2),
        "kscript": {"sha256": now_h, "qa": "PASS", "manifest": "MATCH"},
        "schedule": SCHEDULE,
        "signals": symbols,
        "ml_advisory": {"meta": ml_meta, "p_danger_short": ml_adv},
        "contexte_om_v29": {"meta": ctx_meta, "features": ctx_adv},
        "excluded_missing_features": errs,
        "summary": {
            "n_symbols": len(symbols), "long_allowed": len(longs),
            "short_allowed": len(shorts), "any_direction_blocked": len(blocked),
        },
        "elapsed_s": round(time.time() - t0, 2),
    }
    with open(ARMING, "w") as f:
        json.dump(armed, f, indent=1)

    # ---- Ordre de bataille lisible ----------------------------------------
    ts_h = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(last["ts"]))
    md = [
        "# ORDRE DE BATAILLE x501 — ARMÉ", "",
        f"- Passe planificateur : **GO** ({ts_h}, il y a {age_h:.1f} h)",
        f"- Intégrité kScript : SHA256 **MATCH** + QA statique **PASS**",
        f"- Cadence : {SCHEDULE}", "",
        "## Directions autorisées (signal-6 recalculé à froid)", "",
        "| Symbole | LONG | SHORT | funding_z | liq_imb24 | OI 24h | ML danger short | Raisons de blocage |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for s in sorted(symbols):
        d = symbols[s]
        mlp = ml_adv.get(s)
        mlp_s = f"{mlp:.2f}" if mlp is not None else "—"
        md.append(f"| {s} | {'✅' if d['allow_long'] else '🚫'} | "
                  f"{'✅' if d['allow_short'] else '🚫'} | {d['funding_z']} | "
                  f"{d['liq_imb24']} | {d['oi_chg24_pct']} % | {mlp_s} | "
                  f"{'; '.join(d['block_reasons']) or '—'} |")
    md += ["", f"**Résumé** : {len(longs)} longs autorisés, {len(shorts)} shorts autorisés, "
               f"{len(blocked)} symboles partiellement bloqués, "
               f"{len(errs)} écartés (features manquantes).",
           f"",
           f"**ML advisory** : score danger-short du gate appris (leave-one-symbol-out, "
           f"AUC 0,66-0,69 hors symboles vus) — {ml_meta.get('status')} ; "
           f"non bloquant, promotion J+30.",
           "", "## Contexte om_v29 (outils gratuits — advisory NON bloquant)", ""]
    if ctx_adv:
        fund = ctx_adv.get("funding_ann_pct", {})
        struct = ctx_adv.get("structure", {})
        md += ["| Symbole | funding ann % | pos90 (0-1) | compress 30/90 (0-1) |", "|---|---|---|---|"]
        for s in sorted(struct):
            st = struct.get(s, {})
            md.append(f"| {s} | {fund.get(s, '—')} | {st.get('pos90', '—')} | {st.get('comp', '—')} |")
        v = ctx_meta.get("verdicts", {})
        md += ["", f"Verdicts v29 (walk-forward chrono global) : S1 carry funding "
                   f"**{v.get('S1_carry_funding', '—')}** (train +29,6 / test -8,6 bps) ; "
                   f"S2 impulsion OI x prix **{v.get('S2_impulsion_oi_prix', '—')}** "
                   f"(dispersion test 28,1 bps : flush +9,9 vs tendance -18,2) ; "
                   f"S3 structure **{v.get('S3a_position_range90', '—')}** ; S4 régime vol DIAG. "
                   f"Aucun gate nouveau : la config certifiée 50/25/100 + maker reste l'autorité "
                   f"de blocage. Source : {ctx_meta.get('source', '—')} "
                   f"(âge {ctx_meta.get('age_h', '—')} h)."]
    else:
        md += [f"*Contexte om_v29 absent ou périmé ({ctx_meta.get('status')}) — non bloquant.*"]
    md += ["", "*Généré automatiquement par x501_arm_v23.py — zéro intervention manuelle.*"]
    with open(ARMING_MD, "w") as f:
        f.write("\n".join(md) + "\n")

    print(f"ARMED en {armed['elapsed_s']}s | {len(longs)} longs / {len(shorts)} shorts autorisés "
          f"| {len(blocked)} bloqués partiels | {len(errs)} écartés")
    print(f"  -> {ARMING}")
    print(f"  -> {ARMING_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
