# Core Equity Trailer

Trailer Remotion horizontal 1080p pour annoncer les prochaines briques Core Equity.

## Intention

- ton premium / cinematic
- logo orb Core Equity au centre de l'identité visuelle
- annonce "La semaine prochaine"
- focus client: cockpit prive, mouvements suspects, preuves claires, decisions plus rapides, automatisation controlee
- aucune promesse de profit, aucune fausse activation trading

## Preview

```powershell
cd D:\trading-agent\remotion-trailer
npm install
npm run preview
```

## Render

```powershell
cd D:\trading-agent\remotion-trailer
npm run render
```

Sortie prévue:

```text
D:\trading-agent\remotion-trailer\out\core-equity-next-week.mp4
```

## Poster

```powershell
cd D:\trading-agent\remotion-trailer
npm run still
```

## Notes

Le logo utilisé est:

```text
D:\trading-agent\remotion-trailer\public\core-equity-orb.png
```

Le trailer ne touche pas au backend, à la DB, aux labels, aux mappings, aux signaux client ou au trading.
