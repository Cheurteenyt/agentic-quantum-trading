#!/usr/bin/env python3
"""Les unités systemd du dépôt sont-elles vraiment la COPIE des installées ?

`configs/README.md` l'affirme : « `systemd-user/` — copie versionnée des
unités user réellement installées dans `~/.config/systemd/` ». Rien ne le
vérifiait — et le 13/10, cinq unités avaient divergé :

  `trading-agent-nightly.service` installé le **05/10** portait encore les
  étapes BLOQUANTES que le FIX R3 (**08/10**) avait rendues tolérantes (`-`).
  Autrement dit : **les correctifs étaient dans git, jamais déployés**, et un
  hic réseau sur un symbole avortait toujours les étapes suivantes.

C'est le motif « un état qu'on croit vérifié mais qui ne l'est pas » (#288, le
gel). Ce contrôle rend la copie vérifiable.

Portée volontairement ÉTROITE : on ne juge que les unités que le dépôt
VERSIONNE. Une unité installée qui n'est pas ici appartient à un autre projet
de la machine — la flaguer serait du bruit, pas un contrôle.

Sans unité installée (CI, clone propre), le contrôle s'ABSTIENT : on ne juge
pas une copie dont l'original est absent. Un garde qui rougit sur un clone
propre apprend à être ignoré.

Usage :
    .venv/bin/python scripts/audit_systemd_units.py            # rapport
    .venv/bin/python scripts/audit_systemd_units.py --check    # exit 1 si dérive
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_UNITS = ROOT / "configs" / "systemd-user"
INSTALLED_UNITS = Path.home() / ".config" / "systemd" / "user"


def _normaliser(txt: str) -> list[str]:
    """Les lignes qui comptent : on ignore commentaires et lignes vides.

    Un commentaire peut différer d'une copie à l'autre sans que le
    COMPORTEMENT change — juger le commentaire serait juger le style.
    """
    return [ln.rstrip() for ln in txt.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def comparer(repo_dir: Path, installe_dir: Path) -> dict:
    """Les unités versionnées : divergentes / non installées / fidèles."""
    divergentes, non_installees, fideles = [], [], []
    if not repo_dir.is_dir():
        return {"repo_absent": True, "divergentes": [], "non_installees": [],
                "fideles": []}
    for src in sorted(repo_dir.iterdir()):
        if not src.is_file() or src.suffix not in (".service", ".timer"):
            continue
        dst = installe_dir / src.name
        if not dst.exists():
            non_installees.append(src.name)
            continue
        if _normaliser(src.read_text(encoding="utf-8")) == \
                _normaliser(dst.read_text(encoding="utf-8")):
            fideles.append(src.name)
        else:
            divergentes.append(src.name)
    return {"repo_absent": False, "divergentes": divergentes,
            "non_installees": non_installees, "fideles": fideles}


def main() -> int:
    ap = argparse.ArgumentParser(description="Copie des unités systemd fidèle ?")
    ap.add_argument("--repo-dir", default=str(REPO_UNITS))
    ap.add_argument("--installed-dir", default=str(INSTALLED_UNITS))
    ap.add_argument("--check", action="store_true",
                    help="exit 1 si une unité installée diverge de sa copie")
    a = ap.parse_args()
    repo, installe = Path(a.repo_dir), Path(a.installed_dir)
    if not installe.is_dir():
        print(f"[info] aucune unité installée ({installe}) — copie non jugeable "
              f"(CI / clone propre). Rien à vérifier.")
        return 0
    r = comparer(repo, installe)
    if r["repo_absent"]:
        print(f"[ERREUR] {repo} est absent — le dépôt doit versionner ses unités.")
        return 1 if a.check else 0
    total = len(r["divergentes"]) + len(r["non_installees"]) + len(r["fideles"])
    print(f"SYSTEMD UNITS — {total} unité(s) versionnée(s) ; "
          f"{len(r['fideles'])} fidèle(s) à {installe}")
    for nom in r["divergentes"]:
        print(f"  [PROBLÈME] {nom} : la copie du dépôt ≠ l'installée "
              f"(un correctif n'a pas été déployé ?)")
    for nom in r["non_installees"]:
        print(f"  [info]     {nom} : versionnée, pas installée "
              f"(variante ou service à activer)")
    if not r["divergentes"]:
        print("  [OK] aucune divergence : la copie est fidèle.")
        return 0
    print(f"\n→ {len(r['divergentes'])} divergence(s). Déployer : "
          "`cp configs/systemd-user/* ~/.config/systemd/user/` puis "
          "`systemctl --user daemon-reload`.")
    return 1 if a.check else 0


if __name__ == "__main__":
    sys.exit(main())
