# Contribuer à Youtubingest

Tout d'abord, merci d'envisager de contribuer à Youtubingest ! Nous accueillons toute aide, qu'il s'agisse de signaler un bug, de proposer une nouvelle fonctionnalité, d'améliorer la documentation ou d'écrire du code.

Ce document fournit des directives pour vous aider à contribuer efficacement.

## Note Importante sur ce Projet

Ce projet a été développé par une personne sans expérience formelle en programmation, avec une assistance significative d'outils d'IA. Bien que l'application soit fonctionnelle, le code peut ne pas adhérer à toutes les meilleures pratiques de l'industrie et pourrait bénéficier d'améliorations par des développeurs expérimentés.

Si vous êtes un développeur expérimenté, votre expertise en refactoring, optimisation et amélioration de la qualité du code serait particulièrement précieuse. Si vous êtes débutant, ce projet pourrait être une bonne opportunité d'apprentissage, car il démontre ce qui peut être réalisé avec l'assistance de l'IA.

## Code de Conduite

Bien que nous n'ayons pas encore de document formel de Code de Conduite, nous attendons de tous les contributeurs qu'ils soient respectueux et attentionnés envers les autres. Veuillez participer aux discussions de manière constructive et aider à créer un environnement positif.

## Comment Puis-je Contribuer ?

Il y a plusieurs façons de contribuer :

### Signaler des Bugs

* Si vous trouvez un bug, veuillez d'abord vérifier les [Issues GitHub](https://github.com/nclsjn/youtubingest/issues) pour voir s'il a déjà été signalé.
* Si ce n'est pas le cas, ouvrez une nouvelle issue. Assurez-vous d'inclure :
    * Un titre clair et descriptif.
    * Les étapes pour reproduire le bug.
    * Ce que vous vous attendiez à voir se produire.
    * Ce qui s'est réellement produit (y compris les messages d'erreur ou les logs si possible).
    * Les détails de votre environnement (OS, version Python, etc.).

### Suggérer des Améliorations

* Si vous avez une idée pour une nouvelle fonctionnalité ou une amélioration d'une fonctionnalité existante, vérifiez les [Issues GitHub](https://github.com/nclsjn/youtubingest/issues) pour voir si elle a déjà été suggérée.
* Si ce n'est pas le cas, ouvrez une nouvelle issue décrivant votre amélioration :
    * Utilisez un titre clair et descriptif.
    * Fournissez une description étape par étape de l'amélioration suggérée avec autant de détails que possible.
    * Expliquez pourquoi cette amélioration serait utile.

### Pull Requests (Contributions de Code)

Nous accueillons les pull requests ! Voici le workflow général :

1.  **Forkez le dépôt** sur votre propre compte GitHub.
2.  **Clonez votre fork** localement : `git clone https://github.com/VOTRE_NOM_UTILISATEUR/youtubingest.git`
3.  **Créez une nouvelle branche** pour vos modifications : `git checkout -b feature/nom-de-votre-fonctionnalité` ou `fix/numéro-issue`. Veuillez utiliser des noms de branches descriptifs.
4.  **Configurez votre environnement de développement :** Suivez les instructions dans le fichier [README_FR.md](README_FR.md#installation) (créez un environnement virtuel, installez les dépendances, configurez `.env`).
5.  **Faites vos modifications de code.** Assurez-vous de respecter les directives de [Style de Code](#style-de-code).
6.  **Ajoutez des tests** pour vos modifications si applicable (voir [Tests](#tests)).
7.  **Exécutez les tests** localement pour vous assurer qu'ils passent. (Les instructions sur la façon d'exécuter les tests devraient être ajoutées ici une fois qu'un exécuteur de test est configuré, par exemple, `pytest`).
8.  **Committez vos modifications** avec des messages de commit clairs et concis. Référencez tout numéro d'issue connexe (par exemple, `git commit -m 'feat: Ajouter le support pour XYZ (closes #123)'`).
9.  **Poussez votre branche** vers votre fork : `git push origin feature/nom-de-votre-fonctionnalité`
10. **Ouvrez une Pull Request (PR)** contre la branche `main` du dépôt `nclsjn/youtubingest`.
    * Fournissez un titre et une description clairs pour votre PR. Expliquez le "quoi" et le "pourquoi" de vos modifications.
    * Liez toute issue pertinente.
    * Assurez-vous que toute documentation applicable (`README_FR.md`, docstrings) est mise à jour.

## Checklist de Pull Request

Avant de soumettre votre PR, veuillez vous assurer que :

* [ ] Votre code respecte les directives de [Style de Code](#style-de-code).
* [ ] Vous avez ajouté des tests pour les nouvelles fonctionnalités ou corrections de bugs.
* [ ] Tous les tests existants et nouveaux passent localement.
* [ ] Vous avez mis à jour la documentation (`README_FR.md`, docstrings) si nécessaire.
* [ ] Vos messages de commit sont clairs et descriptifs.
* [ ] La description de la PR explique clairement les modifications et fait référence aux issues connexes.

## Style de Code

* Veuillez suivre les directives **PEP 8** pour le code Python. Nous recommandons d'utiliser des linters/formateurs comme `flake8` et `black`.
* Utilisez des noms de variables et de fonctions clairs et descriptifs.
* Ajoutez des **docstrings** aux nouvelles fonctions, classes et méthodes, expliquant leur objectif, arguments et valeurs de retour.
* Gardez le code modulaire et concentré sur des responsabilités spécifiques.

## Tests

* Les contributions devraient idéalement inclure des tests.
* Si vous corrigez un bug, ajoutez un test qui démontre le bug et vérifie la correction.
* Si vous ajoutez une fonctionnalité, ajoutez des tests qui couvrent la nouvelle fonctionnalité.
* Assurez-vous que tous les tests passent avant de soumettre une PR. (Ajoutez la commande pour exécuter les tests ici lorsqu'elle sera disponible).

## Licence

En contribuant à Youtubingest, vous acceptez que vos contributions soient sous licence selon la [Licence MIT](LICENSE) du projet.

Merci de contribuer !
