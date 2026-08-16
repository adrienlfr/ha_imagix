# Changelog

Toutes les modifications notables de ce projet sont documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
projet utilise [Semantic Versioning](https://semver.org/lang/fr/).

## [0.8.1] - 2026-08-16

### Corrigé

- Corrige l'import de la plateforme `sensor` en définissant le calcul du
  prochain segment avant la déclaration des capteurs adaptatifs.

## [0.8.0] - 2026-08-16

### Ajouté

- Moteur de filtration adaptative basé sur les heures équivalentes de
  filtration (EFH).
- Trois profils hydrauliques physiques : Éco, Moyen et Boost.
- Calcul du besoin selon la température, le volume et la qualité d'eau.
- Planification autour du zénith solaire et publication dans `prog_user`.
- Suivi des EFH délivrées, de la dette et de la confiance des données.
- Options Home Assistant, capteurs de diagnostic, sélecteur de stratégie et
  bouton de recalcul.

### Modifié

- Le cron copiant `progServer` toutes les dix minutes est remplacé par un
  manager événementiel qui n'écrit que lorsque le planning change.

## [0.7.0]

### Ajouté

- Infrastructure initiale de versionnement et de publication HACS.

## [0.4.0]

- Version déclarée actuellement dans le manifeste Home Assistant.
