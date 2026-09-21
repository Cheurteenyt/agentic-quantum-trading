# configs/ — config non-secrete

Voir la documentation centrale : [`docs/02-architecture.md`](../docs/02-architecture.md)

Point d'entree : [`docs/README.md`](../docs/README.md)

- `systemd-user/` — copie versionnée des unités user réellement installées
  dans `~/.config/systemd/` (campagne nocturne : `trading-agent-nightly`).
  Après modification ici, re-copier vers `~/.config/systemd/user/` puis
  `systemctl --user daemon-reload`.
- `tailscale/` — ACL et surface réseau.
- `cloudflare-tunnel.example.yml` — gabarit (le vrai tunnel config est ignoré).
