# Youtubingest

Youtubingest est une application FastAPI qui extrait et traite du contenu YouTube (vidéos, playlists, chaînes, requêtes de recherche) en texte optimisé pour les Grands Modèles de Langage (LLMs).

## Fonctionnalités

* Ingestion de contenu à partir de vidéos YouTube, playlists, chaînes (par ID, handle, URL personnalisée, nom d'utilisateur) ou termes de recherche.
* Extraction des métadonnées clés des vidéos (titre, description, durée, date de publication, informations sur la chaîne, tags).
* Récupération et formatage des transcriptions vidéo avec regroupement temporel configurable.
* Nettoyage du contenu textuel (titres, descriptions) pour une meilleure utilisation par les LLMs.
* Filtrage des vidéos par date de publication.
* Calcul du nombre estimé de tokens pour le digest généré (utilisant TikToken).
* Interface web simple pour l'interaction et les tests.
* API REST pour une utilisation programmatique.
* Limitation de débit, métriques et middleware de sécurité de base.
* Support optionnel de chiffrement de clé API.
* Gestion centralisée du cache pour améliorer les performances et l'utilisation de la mémoire.
* Gestion robuste des erreurs avec des réponses d'erreur standardisées.

## Prérequis

* Python 3.8 ou supérieur
* Une clé API YouTube Data v3

## Installation

1.  **Cloner le dépôt :**
    ```bash
    git clone https://github.com/nclsjn/youtubingest.git
    cd youtubingest
    ```

2.  **Créer et activer un environnement virtuel (recommandé) :**
    ```bash
    # Sur Linux/macOS
    python3 -m venv venv
    source venv/bin/activate

    # Sur Windows
    python -m venv venv
    .\venv\Scripts\activate
    ```

3.  **Installer les dépendances :**
    ```bash
    pip install -r requirements.txt
    ```
    *Note : Pour des builds reproductibles, il est fortement recommandé d'utiliser les versions épinglées générées par `pip freeze > requirements.txt` après avoir vérifié que votre environnement fonctionne.*

4.  **Configurer les variables d'environnement :**
    * Copier le fichier d'environnement exemple :
        ```bash
        cp .env.example .env
        ```
    * Éditer le fichier `.env` et ajouter votre clé API YouTube :
        ```dotenv
        YOUTUBE_API_KEY="VOTRE_CLE_API_YOUTUBE"
        ```
    * Revoir les autres paramètres dans `.env` (comme `ALLOWED_ORIGINS` si vous déployez) et ajuster si nécessaire. Voir la section [Configuration](#configuration) ci-dessous et les commentaires dans `.env.example` pour plus de détails.

## Configuration

L'application est configurée via des variables d'environnement, généralement chargées à partir d'un fichier `.env`. Voir `.env.example` pour une liste complète des options configurables.

Variables clés :

* `YOUTUBE_API_KEY` (Obligatoire) : Votre clé API YouTube Data v3.
* `ALLOWED_ORIGINS` : Liste séparée par des virgules des origines autorisées à accéder à l'API (CORS). Important pour le déploiement. Exemple : `"http://localhost:8000,https://votre-domaine-frontend.com"`
* `HOST` : Hôte du serveur (par défaut : `127.0.0.1`).
* `PORT` : Port du serveur (par défaut : `8000`).
* `DEBUG` : Mettre à `true` pour le mode développement (active le rechargement automatique) (par défaut : `false`).
* `LOG_LEVEL_CONSOLE`/`LOG_LEVEL_FILE` : Définir les niveaux de journalisation (par défaut : `INFO`/`DEBUG`).
* `LOG_STRUCTURED` : Utiliser la journalisation JSON structurée (`true`/`false`) (par défaut : `true`).

Variables optionnelles pour le chiffrement de la clé API (nécessitent le package `cryptography`) :

* `YOUTUBE_API_KEY_PASSWORD` : Mot de passe pour dériver la clé de chiffrement.
* `YOUTUBE_API_KEY_SALT` : Un sel unique et fixe (encodage base64 recommandé) utilisé avec le mot de passe.

Référez-vous à `config.py` et `.env.example` pour des options plus avancées (limites de débit, paramètres de cache, timeouts, etc.).

## Utilisation

1.  **Démarrer le serveur :**
    ```bash
    python server.py
    ```
    Par défaut, le serveur fonctionnera sur `http://127.0.0.1:8000` et tentera d'ouvrir automatiquement votre navigateur web (désactivez avec `AUTO_OPEN_BROWSER=false` dans `.env`).

2.  **Accéder à l'interface Web :**
    Ouvrez votre navigateur à l'adresse `http://127.0.0.1:8000` (ou l'hôte/port configuré). L'interface vous permet d'envoyer facilement des requêtes à l'endpoint `/ingest`.

3.  **Utiliser l'API de manière programmatique :**
    Voir la section [Documentation de l'API](#documentation-de-lapi) ci-dessous.

## Architecture

Youtubingest est construit avec une architecture modulaire qui met l'accent sur la maintenabilité et les performances. Bien que conçue avec l'assistance de l'IA, l'architecture suit plusieurs bonnes pratiques :

### Gestion du Cache

L'application utilise un système de gestion de cache centralisé (`cache_manager.py`) qui :

* Fournit une interface unifiée pour enregistrer et effacer différents types de caches
* Prend en charge à la fois les caches de fonctions (décorés avec `@lru_cache`) et les caches LRU personnalisés
* Efface automatiquement les caches lorsqu'une pression mémoire est détectée
* Fournit des statistiques sur l'utilisation et les performances du cache
* Optimise l'utilisation de la mémoire en effaçant les caches lorsque nécessaire

### Gestion des Erreurs

Le système de gestion des erreurs (`exceptions.py`) fournit :

* Une hiérarchie d'exceptions spécifiques à l'application qui étendent `AppBaseError`
* Des codes d'erreur cohérents, des codes de statut HTTP et des en-têtes retry-after
* Une fonction centralisée `handle_exception` qui convertit n'importe quelle exception en `HTTPException` appropriée
* Des réponses d'erreur standardisées pour tous les endpoints API

### Optimisation des Performances

L'application inclut plusieurs optimisations de performance :

* Traitement par lots des transcriptions pour éviter de créer trop de tâches à la fois
* Préallocation de mémoire pour de meilleures performances
* Compilation des expressions régulières une seule fois pour de meilleures performances
* Mise en cache des fonctions et données fréquemment utilisées
* Traitement asynchrone des requêtes concurrentes
* Surveillance de la mémoire pour détecter et gérer la pression mémoire

### Tests

L'application inclut une suite de tests complète :

* Tests unitaires pour les composants principaux (moteur, cache, moniteur de mémoire)
* Tests d'intégration pour les endpoints API
* Tests de performance pour les chemins critiques
* Tests d'utilisation de la mémoire pour assurer une utilisation efficace des ressources

## Documentation de l'API

L'API fournit plusieurs endpoints sous le préfixe `/` (comme défini dans `api/routes.py`) :

### `POST /ingest`

Traite une URL YouTube ou un terme de recherche et renvoie un digest.

* **Corps de la Requête :** (`application/json`)
    * `url` (chaîne, obligatoire) : URL de vidéo/playlist/chaîne YouTube, handle (@nomutilisateur) ou terme de recherche.
    * `include_transcript` (booléen, optionnel, par défaut : `true`) : Inclure ou non les transcriptions.
    * `include_description` (booléen, optionnel, par défaut : `true`) : Inclure ou non les descriptions de vidéos.
    * `transcript_interval` (entier, optionnel, par défaut : `10`) : Intervalle de regroupement en secondes pour les transcriptions (0 = pas d'horodatage/regroupement, autorisé : 0, 10, 20, 30, 60). Utilise la valeur par défaut de `config.py` si null ou invalide.
    * `start_date` (chaîne, optionnel, par défaut : `null`) : Date ISO 8601 (ex. `AAAA-MM-JJ`). Filtre les vidéos publiées à partir de cette date (UTC).
    * `end_date` (chaîne, optionnel, par défaut : `null`) : Date ISO 8601 (ex. `AAAA-MM-JJ`). Filtre les vidéos publiées jusqu'à cette date (UTC).

* **Réponse Réussie :** (`200 OK`, `application/json`) - Structure basée sur le modèle `IngestResponse` (`models.py`) :
    ```json
    {
      "source_name": "chaîne",
      "digest": "chaîne",
      "video_count": 0,
      "processing_time_ms": 0.0,
      "api_call_count": 0,
      "token_count": 0,
      "api_quota_used": 0,
      "high_quota_cost": false,
      "videos": [ /* Liste d'objets Video (voir models.py) */ ]
    }
    ```

* **Réponses d'Erreur :**
    * `400 Bad Request` : Entrée invalide (ex. URL manquante, format de date invalide).
    * `403 Forbidden` : Problème de clé API ou quota dépassé.
    * `404 Not Found` : Ressource YouTube non trouvée.
    * `413 Request Entity Too Large` : Taille du corps de la requête dépasse la limite.
    * `429 Too Many Requests` : Limite de débit dépassée.
    * `500 Internal Server Error` : Erreur serveur inattendue.
    * `503 Service Unavailable` : Erreur de configuration API, disjoncteur ouvert ou échec d'initialisation.
    (Les réponses d'erreur suivent le modèle `ErrorResponse` de `models.py`)

### `GET /health`

Vérifie l'état opérationnel du service et de ses composants.

* **Réponse Réussie :** (`200 OK`, `application/json`)
    * Renvoie un objet JSON avec le statut, l'horodatage, la version, l'état de préparation des composants et des statistiques détaillées (utilisation de l'API, caches, mémoire, etc.).

### `POST /clear-caches`

Efface manuellement tous les caches internes de l'application (réponses API, transcriptions, etc.). À utiliser avec précaution.

* **Réponse Réussie :** (`200 OK`, `application/json`)
    * Renvoie un objet JSON confirmant le succès et les détails sur les caches effacés.
* **Réponse d'Erreur :** (`500 Internal Server Error`) si l'effacement échoue.

### `POST /check-input-type`

Vérifie si l'entrée fournie (champ `url` dans le corps JSON) est probablement une requête de recherche (coût API élevé) ou un autre type (vidéo, playlist, URL de chaîne).

* **Corps de la Requête :** (`application/json`)
    ```json
    { "url": "chaîne" }
    ```
* **Réponse Réussie :** (`200 OK`, `application/json`)
    ```json
    {
      "is_search": booléen,
      "input_type": "chaîne", // ex. "video", "playlist", "channel", "search", "invalid", "empty", "error"
      "high_cost_warning": booléen,
      "message": "chaîne"
    }
    ```
* **Réponse d'Erreur :** (`503 Service Unavailable`) si le client API n'est pas prêt.

## Documentation

Pour une documentation détaillée, veuillez consulter les ressources suivantes :

- [Documentation de l'API](docs/api.md) - Description des endpoints, paramètres et réponses
- [Architecture du Projet](docs/architecture.md) - Vue d'ensemble de l'architecture et des composants
- [Guide de Développement](docs/development.md) - Instructions pour les développeurs

## Contribution

Les contributions sont les bienvenues ! Veuillez lire le fichier [CONTRIBUTING_FR.md](CONTRIBUTING_FR.md) pour les directives sur la façon de contribuer à ce projet.

## À propos de l'Auteur et du Projet

Je ne suis pas un développeur professionnel. Cette application a été entièrement développée avec l'assistance d'outils d'IA. Bien que j'aie fait tous les efforts pour garantir que l'application fonctionne correctement, elle peut ne pas suivre toutes les meilleures pratiques et pourrait contenir des imperfections.

Le projet sert d'exemple de ce qui peut être réalisé avec l'assistance de l'IA dans le développement logiciel, même sans expérience formelle en programmation. Je suis ouvert aux contributions de développeurs expérimentés pour améliorer le code.

## Licence

Ce projet est sous licence MIT - voir le fichier [LICENSE](LICENSE) pour plus de détails.
