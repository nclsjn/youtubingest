# YouTubingest CLI (Async)

Script Python en ligne de commande pour extraire les métadonnées (titre, description, chaîne, date, durée, tags) et les transcriptions de vidéos YouTube. Il est conçu pour traiter des URLs individuelles (vidéo, playlist, chaîne, recherche) ou un fichier contenant plusieurs URLs, et génère des fichiers de sortie structurés (TXT, Markdown, YAML) optimisés pour une utilisation ultérieure, notamment avec des modèles de langage (LLM).

## Fonctionnalités Principales

*   **Extraction Complète :** Récupère le titre, la description, l'ID/nom/URL de la chaîne, la date de publication, la durée, les tags et les URLs présentes dans la description.
*   **Gestion des Transcriptions :**
    *   Récupère automatiquement les transcriptions disponibles.
    *   Sélectionne la meilleure langue selon un ordre de préférence configurable (`fr`, `en`, `es`...).
    *   Distingue les transcriptions manuelles des transcriptions générées automatiquement.
    *   Formate les transcriptions en blocs horodatés (`[HH:MM:SS] Texte...`) pour une meilleure lisibilité.
*   **Entrées Flexibles :** Accepte différents types d'URLs YouTube :
    *   Vidéo (`/watch?v=`, `youtu.be/`, `/shorts/`)
    *   Playlist (`/playlist?list=`)
    *   Chaîne (via ID `/channel/UC...`, Handle `/@handle`, URL custom `/c/nom`, URL utilisateur `/user/nom`)
    *   Recherche (`/results?search_query=`)
    *   Peut lire une liste d'URLs depuis un fichier texte.
*   **Formats de Sortie Multiples :** Génère les résultats dans des fichiers :
    *   `.txt` : Format texte brut structuré.
    *   `.md` : Format Markdown avec titres et formatage.
    *   `.yaml` : Format YAML structuré et lisible par les machines.
*   **Traitement Asynchrone :** Utilise `asyncio` pour traiter plusieurs requêtes API (détails vidéo, transcriptions) en parallèle, améliorant significativement la vitesse d'exécution pour de grands volumes d'URLs.
*   **Optimisation & Robustesse :**
    *   **Filtrage :** Ignore les vidéos trop courtes (configurable) ou publiées avant une date limite (configurable).
    *   **Nettoyage :** Nettoie les titres et descriptions en supprimant les éléments superflus (emojis, hashtags, indicateurs publicitaires...).
    *   **Gestion Quota API :** Détecte les erreurs de quota de l'API YouTube Data v3 et arrête proprement le traitement si nécessaire.
    *   **Délais Aléatoires :** Intègre des délais légers et aléatoires entre les appels API pour éviter de surcharger l'API.
    *   **Mise en Cache :** Utilise `lru_cache` et des caches manuels pour réduire les appels API redondants (analyse d'URL, résolution d'ID, listage de transcriptions, pages de playlist).
    *   **Découpage Fichiers :** Découpe automatiquement les fichiers de sortie en plusieurs parties si la taille estimée en tokens dépasse une limite configurable, pour faciliter le traitement par les LLMs.
*   **Interface Utilisateur :** Fournit une interface en ligne de commande interactive (basée sur `rich`) avec une barre de progression en temps réel.
*   **Journalisation :** Enregistre les détails du processus, les avertissements et les erreurs dans un fichier `youtube_scraper_async.log`.

## Prérequis

*   Python 3.7+
*   Dépendances Python (à installer via `pip`) :
    *   `google-api-python-client`
    *   `youtube-transcript-api`
    *   `rich`
    *   `isodate`
    *   `emoji`
    *   `pathvalidate`
    *   `tiktoken` (pour l'estimation des tokens et le découpage des fichiers)
    *   `PyYAML` (pour la sortie au format YAML)

## Installation

1.  **Obtenir le script :**
    *   Téléchargez le fichier `youtube_scraper_cli.py` et placez-le dans le dossier de votre choix.

2.  **Installer les dépendances :**
    Ouvrez un terminal ou une invite de commandes dans le dossier où vous avez placé le script et exécutez :
    ```bash
    pip install google-api-python-client youtube-transcript-api rich isodate emoji pathvalidate tiktoken PyYAML
    ```
    *(Si vous avez un fichier `requirements.txt` correspondant, vous pouvez aussi utiliser `pip install -r requirements.txt`)*

## Configuration : Clé API YouTube

Ce script nécessite une **Clé API YouTube Data v3** pour fonctionner.

1.  **Obtenir une Clé API :**
    *   Allez sur la [Google Cloud Console](https://console.cloud.google.com/).
    *   Créez un nouveau projet (ou sélectionnez un projet existant).
    *   Activez l'API "YouTube Data API v3" pour votre projet.
    *   Créez des identifiants de type "Clé API".
    *   **Important :** Sécurisez votre clé API en limitant son utilisation (par exemple, par adresse IP ou en la restreignant aux API nécessaires) pour éviter toute utilisation abusive.

2.  **Fournir la Clé API au Script :**
    La méthode recommandée est d'utiliser une **variable d'environnement**. Définissez la variable `YOUTUBE_API_KEY` avec votre clé :

    *   **Linux/macOS:**
        ```bash
        export YOUTUBE_API_KEY="VOTRE_CLE_API_ICI"
        python youtube_scraper_cli.py
        ```
        (Pour une définition permanente, ajoutez `export YOUTUBE_API_KEY="VOTRE_CLE_API_ICI"` à votre fichier `~/.bashrc`, `~/.zshrc` ou équivalent).

    *   **Windows (Invite de commandes):**
        ```cmd
        set YOUTUBE_API_KEY=VOTRE_CLE_API_ICI
        python youtube_scraper_cli.py
        ```

    *   **Windows (PowerShell):**
        ```powershell
        $env:YOUTUBE_API_KEY="VOTRE_CLE_API_ICI"
        python youtube_scraper_cli.py
        ```

    *   **(Optionnel) Fichier `.env`:** Vous pouvez aussi utiliser un fichier `.env` dans le même dossier que le script avec le contenu `YOUTUBE_API_KEY="VOTRE_CLE_API_ICI"` et installer `python-dotenv` (`pip install python-dotenv`). Il faudra alors ajouter `from dotenv import load_dotenv; load_dotenv()` au début du script `youtube_scraper_cli.py`.

## Utilisation

Exécutez le script depuis votre terminal (assurez-vous d'être dans le dossier contenant le fichier `.py`) :

```bash
python youtube_scraper_cli.py
```

Le script vous posera ensuite plusieurs questions de manière interactive :

1.  **Mode :**
    *   `1` : Entrer une seule URL YouTube.
    *   `2` : Spécifier le chemin vers un fichier texte contenant une liste d'URLs.
2.  **URL YouTube / Chemin Fichier :** Entrez l'URL ou le chemin du fichier selon le mode choisi.
3.  **Format de sortie :** Choisissez `txt`, `md` ou `yaml`.
4.  **Inclure transcriptions ? :** `y` (oui) ou `n` (non).
5.  **Inclure descriptions ? :** `y` (oui) ou `n` (non).

Le script affichera ensuite une barre de progression en temps réel pendant le traitement des URLs.

### Exemples d'URLs Acceptées

*   **Vidéo :** `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
*   **Playlist :** `https://www.youtube.com/playlist?list=PLXXXXXXXXXXXXXX`
*   **Chaîne (ID) :** `https://www.youtube.com/channel/UCXXXXXXXXXXXXXX`
*   **Chaîne (Handle) :** `https://www.youtube.com/@youtube`
*   **Chaîne (Custom) :** `https://www.youtube.com/c/NomCustom`
*   **Chaîne (User) :** `https://www.youtube.com/user/NomUtilisateur`
*   **Recherche :** `https://www.youtube.com/results?search_query=python+asyncio`
*   **Recherche (avec filtres) :** `"python asyncio" after:2023-01-01 duration:medium order:viewCount` (entré directement comme "URL" en mode 1)

### Format du Fichier d'URLs (Mode 2)

Le fichier doit être un simple fichier texte (`.txt`) avec une URL par ligne. Les lignes vides et les lignes commençant par `#` sont ignorées.

```
# Ceci est un commentaire
https://www.youtube.com/watch?v=VIDEO_ID_1
https://www.youtube.com/playlist?list=PLAYLIST_ID_1

# Autre URL
https://www.youtube.com/@handle_chaine
```

## Sortie

*   Les fichiers de sortie sont générés dans le sous-dossier `Vidéos/` (créé automatiquement dans le répertoire du script).
*   Le nom de base du fichier est dérivé du nom de la source (titre de la playlist, nom de la chaîne, requête de recherche, ou titre de la vidéo si URL unique). Les caractères invalides sont nettoyés.
*   Si la sortie est trop volumineuse (basé sur `MAX_TOKENS_PER_FILE`), elle sera divisée en plusieurs fichiers avec un suffixe `_partie-XX` (ex: `MaPlaylist_partie-01.txt`, `MaPlaylist_partie-02.txt`).
*   L'extension du fichier correspondra au format choisi (`.txt`, `.md`, `.yaml`).

## Configuration Avancée

La plupart des paramètres (délais, date limite, langues préférées, limites de cache, etc.) peuvent être modifiés directement dans la classe `Config` au début du script `youtube_scraper_cli.py`.

## Journalisation (Logging)

Les informations détaillées sur le processus, les avertissements (ex: transcription non trouvée) et les erreurs sont enregistrés dans le fichier `youtube_scraper_async.log` dans le même dossier que le script. Pour un débogage très détaillé, vous pouvez décommenter la ligne `logging.getLogger().setLevel(SPAM_LEVEL_NUM)` dans le script.

## Limitations et Problèmes Connus

*   **Quota API YouTube :** L'utilisation de l'API YouTube Data v3 est soumise à des quotas journaliers. Des recherches ou le traitement de très grandes playlists/chaînes peuvent épuiser rapidement le quota gratuit. Le script détecte les erreurs de quota et s'arrête.
*   **Précision des Transcriptions :** Les transcriptions générées automatiquement par YouTube peuvent contenir des erreurs.
*   **Nettoyage de Texte :** L'heuristique de nettoyage des titres/descriptions peut parfois supprimer des informations légitimes ou ne pas en supprimer assez. Le nettoyage des caractères non imprimables peut affecter certaines langues.
*   **Résolution d'Identifiants :** La résolution des handles (`@nom`) et des URLs custom (`/c/nom`) dépend de l'API Search, qui n'est pas toujours parfaitement fiable pour trouver l'ID de chaîne exact.
*   **Dépendances Externes :** Le script dépend du bon fonctionnement des API YouTube (Data v3 et Transcript API) et des bibliothèques tierces. Des changements dans ces services peuvent affecter le script.

