# Versionnement et publication

## Principe

Le projet utilise Semantic Versioning : `MAJEUR.MINEUR.CORRECTIF`.

- `CORRECTIF` : correction compatible, par exemple `0.4.0` vers `0.4.1`.
- `MINEUR` : nouvelle fonctionnalité compatible, par exemple `0.4.1` vers
  `0.5.0`.
- `MAJEUR` : changement incompatible de configuration, d'entité ou de service.
- Une version de test peut utiliser un suffixe tel que `0.5.0-beta.1`.

La version de `custom_components/imagix/manifest.json` doit être strictement
identique au tag Git, sans le préfixe `v` :

```text
manifest.json : 0.8.1
tag Git       : v0.8.1
```

## Préparer une release

1. Partir d'une branche `main` propre et à jour.
2. Déplacer les changements de la section `Non publié` de `CHANGELOG.md` vers
   une section portant la nouvelle version et la date.
3. Modifier `version` dans `custom_components/imagix/manifest.json`.
4. Contrôler la cohérence :

   ```bash
   python3 scripts/check_version.py v0.8.1
   ```

5. Valider les changements dans Git :

   ```bash
   git add CHANGELOG.md custom_components/imagix/manifest.json
   git commit -m "Release 0.8.1"
   ```

6. Créer et pousser le tag :

   ```bash
   git tag -a v0.8.1 -m "iMagi-x 0.8.1"
   git push origin main
   git push origin v0.8.1
   ```

Le workflow `release.yml` vérifie la correspondance des versions puis crée la
GitHub Release. HACS utilise cette release pour proposer la mise à jour.

## Mise à jour dans Home Assistant

1. Créer une sauvegarde Home Assistant avant l'installation.
2. Lire les notes de version dans HACS.
3. Installer la version proposée.
4. Redémarrer Home Assistant.
5. Vérifier le journal et les principales entités iMagi-x.

## Rollback avec HACS

1. Ouvrir HACS puis l'intégration iMagi-x.
2. Utiliser le menu à trois points puis `Retélécharger`.
3. Sélectionner une release antérieure.
4. Télécharger cette version et redémarrer Home Assistant.
5. Si Home Assistant ne redémarre plus, restaurer la sauvegarde créée avant la
   mise à jour.

Ne jamais déplacer ou remplacer un tag déjà publié. Une correction d'une
release doit toujours recevoir un nouveau numéro de version.
