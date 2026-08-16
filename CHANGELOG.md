# Changelog

Toutes les modifications notables de ce projet sont documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
projet utilise [Semantic Versioning](https://semver.org/lang/fr/).

## [0.9.2] - 2026-08-16

### Corrigé

- Un recalcul effectué après le coucher du soleil prépare désormais le
  planning du lendemain au lieu de publier un programme de zéro heure.
- Le calcul nocturne ne crédite pas au lendemain les EFH et minutes Boost déjà
  délivrées pendant la journée terminée.

## [0.9.1] - 2026-08-16

### Corrigé

- Corrige l'erreur HTTP 500 à l'ouverture des options en remplaçant le
  validateur horaire non sérialisable par Home Assistant.
- Conserve une validation stricte du format HC `HH:MM` lors de
  l'enregistrement du formulaire.

## [0.9.0] - 2026-08-16

### Ajouté

- Optimisation du coût électrique entre heures creuses et heures pleines à
  partir des puissances configurées pour les profils Éco, Moyen et Boost.
- Contrainte stricte de filtration entre le lever et le coucher du soleil,
  obtenus depuis l'entité Home Assistant `sun.sun`.
- Minimum quotidien configurable de 60 minutes continues en mode Boost.
- Capteurs de diagnostic pour la durée Boost confirmée, le coût estimé et le
  besoin EFH impossible à placer dans la fenêtre solaire.

### Modifié

- Le planning utilise plusieurs profils hydrauliques et privilégie les plages
  HC uniquement lorsqu'elles chevauchent la journée.
- Le suivi persistant comptabilise séparément les minutes réellement
  confirmées à haut débit.

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
