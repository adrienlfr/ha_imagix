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
- **Planning expert** : toutes les 10 minutes, le programme `progServer` lu sur le coffret est recopié à l’identique dans `prog_user`, même s’il est vide. Le programme de filtration actuellement actif n’est pas changé. Si `progServer` n’est pas fourni par le coffret, aucune commande n’est envoyée.
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

## Développement

### Structure du projet

```
custom_components/imagix/
├── __init__.py          # Point d'entrée de l'intégration
├── api.py              # Client API pour communiquer avec iMagi-x
├── climate.py           # Thermostat de la pompe à chaleur
├── config_flow.py      # Interface de configuration
├── const.py            # Constantes
├── coordinator.py      # Coordinateur de mise à jour des données
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
