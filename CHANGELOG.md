# Changelog

Toutes les modifications notables de ce projet sont documentées ici.

Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/) et le
projet utilise [Semantic Versioning](https://semver.org/lang/fr/).

## [0.10.1] - 2026-08-17

### Modifié

- Le profil intermédiaire du planning adaptatif commande désormais le mode
  optimisé `7` du coffret au lieu du mode moyen `3`.

## [0.10.0] - 2026-08-17

### Ajouté

- Lecture horaire des prévisions Home Assistant depuis une entité `weather`,
  choisie automatiquement ou configurée dans les options.
- Correction météo bornée du besoin EFH selon la chaleur prévue, l'indice UV,
  le vent, la pluie et les orages.
- Capteurs de diagnostic pour le débit moyen réellement délivré et l'heure du
  pic météo ciblé.

### Modifié

- Le Boost quotidien d'une heure est réparti par défaut en quatre créneaux de
  15 minutes, placés aux moments les plus pertinents selon la météo, le soleil
  et le tarif électrique.
- La pompe reste en marche sur une plage continue : seuls les profils Éco,
  Moyen et Boost changent entre les créneaux.
- La stratégie Équilibrée réserve la majorité des EFH flexibles au débit moyen
  au lieu de laisser le calcul de coût sélectionner presque exclusivement Éco.
- Le planning est recalculé toutes les heures et conserve un minimum quotidien
  configurable de débit moyen.

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
