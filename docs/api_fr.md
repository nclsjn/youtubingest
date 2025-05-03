# Documentation de l'API Youtubingest

Ce document décrit les endpoints de l'API Youtubingest, leurs paramètres et leurs réponses.

## Endpoints

### 1. Ingest YouTube Content

Extrait et traite le contenu YouTube (vidéos, playlists, chaînes).

**Endpoint**: `/api/v1/ingest`

**Méthode**: `POST`

**Paramètres de requête**:

| Paramètre | Type | Description | Requis | Défaut |
|-----------|------|-------------|--------|--------|
| url | string | URL YouTube à traiter | Oui | - |
| include_transcripts | boolean | Inclure les transcriptions | Non | true |
| transcript_interval | integer | Intervalle de regroupement des transcriptions (secondes) | Non | 10 |

**Exemple de requête**:

```json
{
  "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "include_transcripts": true,
  "transcript_interval": 30
}
```

**Exemple de réponse**:

```json
{
  "source_name": "Never Gonna Give You Up",
  "content_type": "video",
  "videos": [
    {
      "id": "dQw4w9WgXcQ",
      "title": "Rick Astley - Never Gonna Give You Up (Official Music Video)",
      "description": "...",
      "channel_title": "Rick Astley",
      "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
      "duration_seconds": 213,
      "duration_formatted": "3:33",
      "published_at": "2009-10-25T06:57:33Z",
      "view_count": 1234567890,
      "like_count": 12345678,
      "comment_count": 1234567,
      "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
      "transcript": {
        "language": "en",
        "transcript": "[00:00] We're no strangers to love\n[00:10] You know the rules and so do I..."
      }
    }
  ],
  "stats": {
    "processing_time_ms": 1234,
    "api_calls_request": 2,
    "api_quota_used_request": 3,
    "transcript_found_count": 1,
    "memory_mb_process": 123.45
  }
}
```

**Codes de réponse**:

- `200 OK`: Requête traitée avec succès
- `400 Bad Request`: Paramètres invalides
- `404 Not Found`: Ressource YouTube non trouvée
- `429 Too Many Requests`: Limite de requêtes atteinte
- `500 Internal Server Error`: Erreur interne du serveur

### 2. Get Global Stats

Récupère les statistiques globales de l'application.

**Endpoint**: `/api/v1/stats`

**Méthode**: `GET`

**Exemple de réponse**:

```json
{
  "engine_uptime_seconds": 3600,
  "total_requests_processed": 100,
  "total_videos_processed": 500,
  "api_client_stats": {
    "api_calls": 200,
    "quota_used": 300,
    "quota_reached": false,
    "cache_hits": 50
  },
  "transcript_manager_stats": {
    "cache_hits_result": 80,
    "cache_hits_error": 10,
    "cache_misses": 20,
    "fetch_attempts": 30,
    "fetch_errors": 5
  },
  "memory_stats": {
    "process_memory_mb": 256.78,
    "system": {
      "memory_percent": 45.6,
      "memory_total_gb": 16.0,
      "memory_available_gb": 8.7
    }
  }
}
```

**Codes de réponse**:

- `200 OK`: Requête traitée avec succès
- `500 Internal Server Error`: Erreur interne du serveur

### 3. Clear Caches

Vide les caches de l'application.

**Endpoint**: `/api/v1/clear-caches`

**Méthode**: `POST`

**Exemple de réponse**:

```json
{
  "function_caches_cleared": 5,
  "lru_cache_youtube_api": 10,
  "lru_cache_transcript": 15,
  "garbage_collection": {
    "objects_collected": 1000,
    "memory_freed_mb": 50.25
  }
}
```

**Codes de réponse**:

- `200 OK`: Requête traitée avec succès
- `500 Internal Server Error`: Erreur interne du serveur

### 4. Health Check

Vérifie l'état de santé de l'application.

**Endpoint**: `/api/v1/health`

**Méthode**: `GET`

**Exemple de réponse**:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "api_client_available": true,
  "transcript_manager_available": true,
  "memory_pressure": false,
  "uptime_seconds": 3600
}
```

**Codes de réponse**:

- `200 OK`: Application en bon état
- `503 Service Unavailable`: Application en mauvais état

## Gestion des erreurs

Toutes les erreurs sont renvoyées dans un format JSON cohérent :

```json
{
  "error": {
    "code": "QUOTA_EXCEEDED",
    "message": "YouTube API quota exceeded",
    "details": "Daily quota limit reached. Try again tomorrow.",
    "retry_after": 86400
  }
}
```

## Limites de l'API

- **Limite de requêtes** : 30 requêtes par minute par adresse IP
- **Limite de vidéos** : 200 vidéos maximum par requête
- **Taille maximale du corps de la requête** : 15 Mo

## Authentification

L'API ne nécessite pas d'authentification pour le moment, mais elle peut être limitée par adresse IP.

## Versionnement

L'API est versionnée dans l'URL (`/api/v1/...`). Les changements incompatibles seront introduits dans une nouvelle version.
