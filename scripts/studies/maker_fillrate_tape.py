# maker_fillrate_tape.py — LE FILL-RATE MAKER à l'open, mesuré sur la tape réelle (BTC/ETH).
# Le R1 (Sonnet) avait noté : « le fill rate des ordres maker n'est pas testé (hypothèse 70 %) ».
# Le protocole Bonsai (04/10) définissait le fill-rate de façon non mesurable — version honnête ici :
#   fill_rate(T) = part des bougies 1h où le prix REVIENNT toucher l'open dans les T minutes
#   (une limite d'achat posée à l'open ne se remplit que si le prix trade à ≤ open).
# LA SÉLECTION ADVERSE (la moitié que Bonsai a ratée) : être rempli = le marché est revenu à
# ton prix. On mesure donc aussi E[rendement open→clôture | rempli] vs inconditionnel —
# le maker économise le spread (12-24 bps) mais se fait remplir quand ça va contre lui.
# Descriptif → pré-enregistrable si les chiffres le méritent. Aucun verdict de flux.

import sqlite3
import numpy as np
import pandas as pd

DB = "data/warehouse/klines.db"
WINDOWS_MIN = [1, 5, 15, 30, 60]
SYMS = ["BTCUSDT", "ETHUSDT"]


def main():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=60)
    for sym in SYMS:
        kl = pd.read_sql_query(
            "SELECT open_time, open, close FROM klines WHERE symbol=? AND interval='1h' "
            "ORDER BY open_time", con, params=(sym,))
        kl = kl[kl.open_time >= 1751500000000]  # fenêtre couverte par la tape (03/07 →)
        if kl.empty:
            continue
        tape = pd.read_sql_query(
            "SELECT ts_ms, price FROM aster_tape WHERE symbol=?", con, params=(sym,))
        tape = tape.sort_values("ts_ms").reset_index(drop=True)
        ts = tape["ts_ms"].to_numpy()
        px = tape["price"].to_numpy()
        print(f"\n== {sym} : {len(kl):,} bougies 1h × {len(tape):,} prints ==")

        opens = kl["open"].to_numpy()
        closes = kl["close"].to_numpy()
        t0 = kl["open_time"].to_numpy()
        rows = []
        for i in range(len(kl)):
            lo, hi = np.searchsorted(ts, t0[i]), np.searchsorted(ts, t0[i] + 3_600_000)
            if hi <= lo:
                continue
            seg_t = ts[lo:hi] - t0[i]
            seg_p = px[lo:hi]
            o = opens[i]
            row = {"ret_open_close": (closes[i] / o - 1) * 1e4}
            for w in WINDOWS_MIN:
                m = seg_t <= w * 60_000
                if m.any():
                    row[f"buy_touch_{w}"] = bool((seg_p[m] <= o).any())
                    row[f"sell_touch_{w}"] = bool((seg_p[m] >= o).any())
                else:
                    row[f"buy_touch_{w}"] = False
                    row[f"sell_touch_{w}"] = False
            rows.append(row)
        r = pd.DataFrame(rows)
        n = len(r)
        print(f"bougies couvertes par la tape : {n:,}")
        print(f"{'fenêtre':>8s} {'fill_buy':>9s} {'fill_sell':>10s} {'E[ret|rempli_buy]':>18s} "
              f"{'E[ret|pas rempli]':>18s} {'Δ sélection adverse':>20s}")
        for w in WINDOWS_MIN:
            fb = r[f"buy_touch_{w}"]
            e_f = r.loc[fb, "ret_open_close"].mean() if fb.any() else np.nan
            e_nf = r.loc[~fb, "ret_open_close"].mean() if (~fb).any() else np.nan
            print(f"{w:>7d}m {fb.mean()*100:>8.1f}% {(r[f'sell_touch_{w}']).mean()*100:>9.1f}% "
                  f"{e_f if e_f==e_f else float('nan'):>17.1f}bp {e_nf if e_nf==e_nf else float('nan'):>17.1f}bp "
                  f"{(e_f - e_nf) if e_f==e_f and e_nf==e_nf else float('nan'):>19.1f}bp")
        fb5 = r["buy_touch_5"]
        if fb5.any():
            print(f"\nlecture 5 min : un maker acheteur à l'open est rempli {fb5.mean()*100:.0f} % "
                  f"du temps ; quand il est rempli, la bougie finit en moyenne "
                  f"{r.loc[fb5,'ret_open_close'].mean():+.1f} bps SOUS son entrée (la sélection adverse) — "
                  f"vs le spread économisé (~16-24 bps meme, ~0-2 majors)")
    con.close()


if __name__ == "__main__":
    main()
