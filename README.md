# iMagi-x Home Assistant Integration

Intégration personnalisée pour connecter votre contrôleur de piscine iMagi-x à Home Assistant.

## Fonctionnalités

Cette intégration vous permet de surveiller votre piscine directement depuis Home Assistant :

### Capteurs disponibles

- **Température de l'eau** - Température actuelle de l'eau de la piscine
- **Température de l'air** - Température ambiante
- **pH** - Niveau de pH de l'eau
- **ORP (Redox)** - Potentiel d'oxydo-réduction en mV
- **État de la filtration** - Arrêt, marche, eco, boost
- **Mode de filtration** - Manuel, auto, nage, pause, hivernal
- **Volume du bassin** - Volume configuré du bassin
- **Colmatage du filtre** - Pourcentage de colmatage du filtre
- **Vitesse de la pompe** - Vitesse actuelle de la pompe en RPM
- **Temps de fonctionnement** - Durée depuis le dernier redémarrage
- **Chlore libre, salinité et dureté de l'eau** - Mesures publiées par le coffret, lorsque disponibles
- **Dernières mesures en circulation** - Température d'eau, pH et ORP mémorisés lorsque la filtration faisait circuler l'eau, avec leur horodatage

### Commandes locales disponibles

Les commandes ci-dessous utilisent l’API locale du coffret et sont affichées seulement si l’équipement correspondant est déclaré présent :

- **Éclairage** : entité `light` pour allumer ou éteindre les spots.
- **Filtration** : choix du mode et du programme, interrupteurs *Filtration baignade* et *Pause filtration*, ainsi que réglage de la durée de pause par défaut.
- **Planning expert adaptatif** : l’intégration calcule le besoin quotidien en heures équivalentes de filtration (EFH), génère un planning à partir de trois profils hydrauliques et le publie dans `prog_user`. Une nouvelle écriture n’est envoyée que lorsque le planning change. Le programme de filtration actuellement actif n’est pas changé automatiquement.
- **Chauffage** : une entité thermostat regroupe la température actuelle, la consigne, les modes Arrêt/Chauffage/Auto, les préréglages Éco/Confort/Boost/Planning et la priorité chauffage. Les anciennes entités de réglage restent disponibles pour compatibilité.
- **Traitement** : choix du mode pH, chlore ou électrolyseur ; les consignes pH, Redox/chlore et électrolyseur sont présentes mais désactivées par défaut dans le registre d’entités, car elles modifient le traitement de l’eau.

Les équipements absents du coffret (volet, balnéo, remplissage, accessoires, etc.) ne créent pas d’entité. Les commandes dont le protocole n’a pas été confirmé par l’application iMAGI-X ne sont volontairement pas envoyées.

## Installation

### HACS (Recommandé)

1. Assurez-vous que [HACS](https://hacs.xyz/) est installé
2. Ajoutez ce dépôt comme dépôt personnalisé dans HACS
3. Recherchez "iMagi-x" et installez
4. Redémarrez Home Assistant

### Installation Manuelle

1. Copiez le dossier `custom_components/imagix` dans le répertoire `custom_components` de votre configuration Home Assistant
2. Redémarrez Home Assistant

## Configuration

1. Allez dans **Paramètres** → **Appareils et services**
2. Cliquez sur **+ Ajouter une intégration**
3. Recherchez "iMagi-x"
4. Entrez l'adresse IP de votre contrôleur iMagi-x (ex: `192.168.1.40`)

### Trouver l'adresse IP de votre contrôleur

Vous pouvez trouver l'adresse IP de votre contrôleur iMagi-x :
- Dans l'application mobile iMagi-x
- Sur l'interface du contrôleur
- Dans les appareils connectés de votre routeur

## API

L'intégration utilise l'API locale du contrôleur iMagi-x sur le port 11000 :
- Lecture : `http://{ip}:11000/api/v1/pool/info`
- Commandes locales : `http://{ip}:11000/api/v1/pool/local/{commande}`
- Intervalle de mise à jour : 5 secondes

`local` est le contexte utilisé par l’application officielle lorsqu’elle est en connexion directe au coffret, depuis le réseau local ou le Wi-Fi iMAGI-X.

### Plages de priorité chauffage

Lorsque le sélecteur **Fonctionnement de la filtration pour le chauffage** est sur *Priorité au chauffage*, le service `imagix.set_heating_priority_schedule` permet de définir une ou plusieurs plages quotidiennes. Pendant ces créneaux, le coffret peut demander le démarrage de la filtration afin de chauffer l’eau ; en dehors, il ne le fait pas.

Dans **Outils de développement → Actions**, exécutez par exemple :

```yaml
action: imagix.set_heating_priority_schedule
data:
  schedule:
    - start: "08:00"
      end: "12:00"
    - start: "14:00"
      end: "20:00"
```

Le service active la priorité chauffage. Les créneaux peuvent traverser minuit, par exemple `22:00`–`06:00`. Si plusieurs coffrets iMAGI-X sont installés, renseignez également `config_entry_id`.

### Tester un planning expert depuis Home Assistant

Le fichier `rest_commands_imagix.yaml` contient une commande de test qui remplace `prog_user` par un planning de 08:00 à 20:00 à vitesse moyenne, sans activer le programme expert. Copiez-le dans le dossier de configuration de Home Assistant, puis ajoutez :

```yaml
rest_command: !include rest_commands_imagix.yaml
```

Après un redémarrage de Home Assistant, exécutez l’action `rest_command.imagix_test_expert_program` depuis **Outils de développement → Actions**. Adaptez l’adresse IP au début du fichier si nécessaire.

### Filtration adaptative

La filtration adaptative est activée par défaut. Elle utilise les profils
physiques suivants :

| Profil | Mode contrôleur | Régime initial | Débit initial |
|---|---:|---:|---:|
| Éco | `4` | 1 800 tr/min | 14 m³/h |
| Moyen | `3` | 2 200 tr/min | 21 m³/h |
| Boost | `1` | 2 850 tr/min | 30 m³/h |

Le libellé « débit optimisé » reste un segment au profil Moyen et envoie donc
le mode `3`. Le mode natif `7` du coffret n’est pas utilisé par le moteur.

Les réglages sont disponibles depuis **Paramètres → Appareils et services →
iMagi-x → Configurer**. Ils permettent notamment de désactiver le moteur, de
choisir la stratégie Éco/Équilibrée/Qualité et d’ajuster les débits, RPM,
bornes EFH et durées minimales.

Le planificateur place tous les segments strictement entre le lever et le
coucher du soleil fournis par l'entité Home Assistant `sun.sun`. Une marge
configurable peut être ajoutée après le lever et avant le coucher. Il garantit
par défaut un segment continu de 60 minutes en Boost chaque jour, puis combine
Éco, Moyen et Boost pour couvrir le besoin EFH au coût estimé le plus faible.

Les heures creuses, les tarifs HC/HP et les puissances électriques des trois
profils sont réglables. Une plage HC nocturne ne sera donc pas utilisée si elle
se trouve hors de la fenêtre solaire. Si le besoin ne tient pas dans la durée
du jour restante, le moteur ne programme rien la nuit : l'état
`daylight_limited` et le capteur de filtration non planifiable exposent le
déficit restant.

Si `sun.sun` ou ses horaires ne sont pas disponibles, le planning reste à
l'arrêt avec l'état `sun_unavailable`. Il est recalculé automatiquement dès
que Home Assistant publie des données solaires valides.

Le moteur publie le planning dans `prog_user`, mais ne sélectionne pas
automatiquement le programme expert. Cette activation reste manuelle tant que
la valeur `actualProg` correspondante n’a pas été confirmée sur le coffret.

## Développement

### Structure du projet

```
custom_components/imagix/
├── __init__.py          # Point d'entrée de l'intégration
├── adaptive_filtration/ # Moteur EFH, planification et entités dédiées
├── api.py              # Client API pour communiquer avec iMagi-x
├── button.py           # Recalcul manuel du planning adaptatif
├── climate.py           # Thermostat de la pompe à chaleur
├── config_flow.py      # Interface de configuration
├── const.py            # Constantes
├── coordinator.py      # Lecture périodique du coffret uniquement
├── entity.py           # Base commune des entités
├── light.py            # Éclairage de la piscine
├── manifest.json       # Métadonnées de l'intégration
├── number.py           # Durées et consignes configurables
├── select.py           # Modes de filtration, chauffage et traitement
├── services.py          # Actions de configuration des plannings
├── services.yaml        # Description des actions Home Assistant
├── sensor.py           # Plateforme capteur
├── switch.py           # Modes temporisés de filtration
└── strings.json        # Traductions
```

## Support

Pour les problèmes et suggestions, veuillez créer une issue sur GitHub.

## Licence

Ce projet est sous licence MIT.
