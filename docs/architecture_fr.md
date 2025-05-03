# Architecture de Youtubingest

Ce document décrit l'architecture globale de l'application Youtubingest, ses composants principaux et leurs interactions.

## Vue d'ensemble

Youtubingest est une application FastAPI qui permet d'extraire et de traiter des données de YouTube (vidéos, playlists, chaînes) pour les rendre utilisables par des modèles de langage (LLM). L'application est conçue avec une architecture modulaire qui met l'accent sur la maintenabilité, la performance et la robustesse.

## Composants principaux

### 1. API FastAPI

Le point d'entrée de l'application est un serveur FastAPI qui expose des endpoints pour interagir avec l'application. Les principaux fichiers sont :

- `main.py` : Configuration de l'application FastAPI, middleware, et gestion du cycle de vie
- `server.py` : Point d'entrée pour le serveur Uvicorn, chargement de la configuration
- `api/routes.py` : Définition des endpoints API
- `api/dependencies.py` : Dépendances injectables pour les routes API

### 2. Moteur de traitement

Le cœur de l'application est le moteur de traitement qui gère l'extraction et le traitement des données YouTube :

- `services/engine.py` : `YoutubeScraperEngine` - Coordonne l'extraction et le traitement des données
- `services/youtube_api.py` : `YouTubeAPIClient` - Interface avec l'API YouTube
- `services/transcript.py` : `TranscriptManager` - Gère l'extraction et le formatage des transcriptions

### 3. Gestion du cache

L'application utilise un système de cache centralisé pour améliorer les performances :

- `cache_manager.py` : Gestionnaire de cache centralisé
- `utils.py` : Implémentation de `LRUCache` (Least Recently Used Cache)

### 4. Gestion des erreurs

Un système de gestion des erreurs unifié pour toute l'application :

- `exceptions.py` : Hiérarchie d'exceptions et fonction `handle_exception`

### 5. Modèles de données

Les modèles de données utilisés dans l'application :

- `models.py` : Définition des classes de modèles (Video, Playlist, etc.)

### 6. Utilitaires

Diverses fonctions et classes utilitaires :

- `utils.py` : Fonctions utilitaires diverses
- `text_processing.py` : Fonctions de traitement de texte
- `logging_config.py` : Configuration du logging

## Flux de données

1. **Requête entrante** : Une requête arrive sur un endpoint API
2. **Validation et traitement** : La requête est validée et traitée par le contrôleur approprié
3. **Extraction des données** : Le moteur de traitement extrait les données de YouTube via l'API
4. **Traitement des transcriptions** : Les transcriptions sont extraites et formatées
5. **Mise en cache** : Les résultats sont mis en cache pour les requêtes futures
6. **Réponse** : Les données traitées sont renvoyées au client

## Gestion de la concurrence

L'application utilise asyncio pour gérer la concurrence :

- Utilisation de `asyncio.Semaphore` pour limiter les requêtes concurrentes
- Traitement par lots des vidéos pour éviter de surcharger l'API YouTube
- Gestion des requêtes dupliquées pour éviter le travail redondant

## Gestion de la mémoire

L'application surveille et gère l'utilisation de la mémoire :

- `MemoryMonitor` surveille l'utilisation de la mémoire
- Nettoyage automatique des caches en cas de pression mémoire
- Limitation du nombre de vidéos traitées par requête

## Optimisations de performance

Plusieurs optimisations sont mises en œuvre pour améliorer les performances :

- Traitement par lots des transcriptions
- Compilation des expressions régulières une seule fois
- Pré-allocation de mémoire pour les structures de données
- Utilisation de références locales pour les méthodes fréquemment appelées
- Mise en cache des résultats intermédiaires

## Tests

L'application inclut une suite de tests complète :

- Tests unitaires pour les composants principaux
- Tests d'intégration pour les endpoints API
- Tests de performance pour les chemins critiques

## Diagramme d'architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Client HTTP    │────▶│  FastAPI        │────▶│  Routes API     │
│                 │     │                 │     │                 │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│                 │     │                 │     │                 │
│  Cache Manager  │◀───▶│  Scraper Engine │◀───▶│  YouTube API    │
│                 │     │                 │     │                 │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │                 │
                        │  Transcript     │
                        │  Manager        │
                        │                 │
                        └─────────────────┘
```

## Bonnes pratiques

L'application suit plusieurs bonnes pratiques de développement :

- **Séparation des préoccupations** : Chaque composant a une responsabilité unique
- **Gestion centralisée des erreurs** : Toutes les erreurs sont gérées de manière cohérente
- **Configuration externalisée** : Les paramètres de configuration sont définis dans un module dédié
- **Logging structuré** : Utilisation de logs structurés pour faciliter le débogage
- **Documentation complète** : Docstrings pour toutes les classes et méthodes
- **Tests automatisés** : Tests unitaires et d'intégration pour garantir la qualité du code
