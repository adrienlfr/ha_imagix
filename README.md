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
- Endpoint : `http://{ip}:11000/api/v1/pool/info`
- Intervalle de mise à jour : 30 secondes

## Développement

### Structure du projet

```
custom_components/imagix/
├── __init__.py          # Point d'entrée de l'intégration
├── api.py              # Client API pour communiquer avec iMagi-x
├── config_flow.py      # Interface de configuration
├── const.py            # Constantes
├── coordinator.py      # Coordinateur de mise à jour des données
├── manifest.json       # Métadonnées de l'intégration
├── sensor.py           # Plateforme capteur
└── strings.json        # Traductions
```

### À venir

- [ ] Support des switches (marche/arrêt pompe, projecteur, etc.)
- [ ] Support des lights (contrôle des projecteurs RGB)
- [ ] Support des climate (chauffage de la piscine)
- [ ] Notifications pour alertes pH/ORP
- [ ] Statistiques de consommation énergétique

## Support

Pour les problèmes et suggestions, veuillez créer une issue sur GitHub.

## Licence

Ce projet est sous licence MIT.
