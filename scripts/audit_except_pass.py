#!/usr/bin/env python3
"""audit_except_pass.py — ratchet sur les `except ...: pass`.

AGENTS.md liste « except: pass » comme **bug prioritaire n°1** : un
excepteur qui n'avale rien cache une panne derrière un résultat vide. Un
collecteur qui échoue doit le dire, sinon il « prouve » une absence de
signal qui n'existe pas.

Le stock mesuré au 2026-10-08 est de **207** `except` dont le corps est un
`pass` seul, répartis sur 84 fichiers. Réduire 207 d'un coup n'est pas
réaliste et n'est pas nécessaire : ce qu'il faut, c'est que la dette
**cesse de croître** et qu'elle soit **visible**.

D'où un ROCHET, sur le même modèle que le ratchet bandit de #197 :

  - le total ne doit pas AUGMENTER ;
  - et **aucun fichier** ne doit voir son propre compte augmenter.

Le second point est ce qui rend le ratchet honnête : sans lui, on pourrait
supprimer 3 `except: pass` d'un fichier et en ajouter 3 ailleurs, le total
resterait plat et la nouvelle dette serait invisible. Le compte par
fichier empêche ce glissement.

Codage par AST et non par grep, parce que grep ne sait pas distinguer :
  - `except X:` suivi de `pass` (corps = pass SEUL, avalé) ;
  - `except X:` suivi de `pass` PUIS d'un `return` (ce n'est plus un
    avalement, le excepteur fait quelque chose) ;
  - une chaîne ou un commentaire contenant « except … pass ».

    python3 scripts/audit_except_pass.py              # compte, exit 1 si > base
    python3 scripts/audit_except_pass.py --list       # les 15 pires fichiers
    python3 scripts/audit_except_pass.py --check      # gate CI : rochet
    python3 scripts/audit_except_pass.py --reset      # réécrit la base (PR de réduction)

Stdlib pure, lecture seule (sauf `--reset`). Code de sortie = 0 si la dette
n'a pas augmenté.
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / ".github" / "except-pass-baseline.json"
RACINES = ("scripts", "backend", "discord_bot", "agent", "tests")
# `agent/` et `tests/` sont inclus : un swallow dans un test masque une
# régression, exactement comme en production.


def _corps_avaler(handler: ast.ExceptHandler) -> bool:
    """Le handler n'avale-t-il RIEN ?

    On ignore les `docstring` (Expr/Constant) — un `except:` documenté puis
    suivi d'un `pass` reste un avalement. Une fois le docstring retiré, un
    corps réduit au seul `Pass` avale l'exception.
    """
    corps = [
        s for s in handler.body
        if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))
    ]
    return len(corps) == 1 and isinstance(corps[0], ast.Pass)


def mesurer() -> dict[str, int]:
    """{fichier relatif -> nombre de `except: pass`}. Les fichiers à zéro
    sont absents du dict : une référence de 84 entrées reste lisible."""
    out: dict[str, int] = {}
    for racine in RACINES:
        for path in sorted((ROOT / racine).rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8",
                                               errors="replace"))
            except (SyntaxError, ValueError):
                continue
            n = sum(1 for h in ast.walk(tree)
                    if isinstance(h, ast.ExceptHandler) and _corps_avaler(h))
            if n:
                out[str(path.relative_to(ROOT))] = n
    return out


def _top(courant: dict[str, int], n: int = 15) -> list[tuple[str, int]]:
    return sorted(courant.items(), key=lambda kv: (-kv[1], kv[0]))[:n]


def _charger_base() -> dict[str, int]:
    if not BASELINE.exists():
        return {}
    try:
        return {k: int(v) for k, v in
                json.loads(BASELINE.read_text(encoding="utf-8")).items()}
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return {}


def cmd_compte(a) -> int:
    courant = mesurer()
    total = sum(courant.values())
    print(f"except: pass — {total} au total sur {len(courant)} fichier(s)")
    for f, n in _top(courant, a.top):
        print(f"  {n:>4}  {f}")
    base = _charger_base()
    if base:
        bt = sum(base.values())
        marque = "" if total <= bt else "   <- AUGMENTE"
        print(f"\nréférence : {bt} sur {len(base)} fichier(s){marque}")
    return 0


def cmd_list(a) -> int:
    courant = mesurer()
    for f, n in sorted(courant.items()):
        for i in range(n):
            print(f"{f}:{n - i}")
    return 0


def cmd_check(a) -> int:
    courant = mesurer()
    base = _charger_base()
    if not base:
        print("::error::référence absente — "
              "`python3 scripts/audit_except_pass.py --reset` "
              "(et commite `.github/except-pass-baseline.json`)")
        return 1
    total_c, total_b = sum(courant.values()), sum(base.values())
    # une régression, c'est un fichier dont le compte AUGMENTE. Un fichier
    # réparé (absent de `courant`) n'en est pas une : c'est une réduction,
    # traitée plus bas.
    regressions = [(f, base.get(f, 0), n) for f, n in sorted(courant.items())
                   if n > base.get(f, 0)]
    if regressions:
        for f, avant, apres in regressions:
            print(f"::error::{f} : except: pass {avant} -> {apres} "
                  f"(le rochet interdit l'augmentation)")
        if total_c > total_b:
            print(f"::error::total {total_b} -> {total_c}")
        return 1
    if total_c < total_b:
        gain = total_b - total_c
        print(f"::notice::dette réduite de {gain} "
              f"({total_b} -> {total_c}) — pense à `--reset` dans la PR")
    else:
        print(f"::notice::except: pass stable a {total_c} "
              f"(référence {total_b}, plafond {len(base)} fichiers)")
    return 0


def cmd_reset(a) -> int:
    courant = mesurer()
    BASELINE.write_text(
        json.dumps(courant, indent=1, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8")
    print(f"référence réécrite : {sum(courant.values())} sur "
          f"{len(courant)} fichier(s) -> {BASELINE.relative_to(ROOT)}")
    print("Ne l utiliser QUE dans une PR qui RÉDUIT la dette : relever la "
          "référence sans rien corriger, c'est effacer l'alarme.")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--top", type=int, default=15)
    p.add_argument("--list", action="store_true",
                   help="liste chaque occurrence (fichier:ligne)")
    p.add_argument("--check", action="store_true", help="gate CI (rochet)")
    p.add_argument("--reset", action="store_true",
                   help="réécrit la référence (PR de réduction)")
    a = p.parse_args(argv)
    if a.list:
        return cmd_list(a)
    if a.check:
        return cmd_check(a)
    if a.reset:
        return cmd_reset(a)
    return cmd_compte(a)


if __name__ == "__main__":
    sys.exit(main())