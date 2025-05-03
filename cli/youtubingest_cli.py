#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
youtubingest_cli.py
Script pour l'extraction de métadonnées et transcriptions de vidéos YouTube.
Prend en charge les sorties aux formats TXT, Markdown et YAML.
Optimisé pour un usage avec les intelligences artificielles conversationnelles (ou LLM).
"""

from __future__ import annotations # Pour des annotations de type plus propres dans les classes

# Imports de la bibliothèque standard
import asyncio
import functools
import logging
import os
import random
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import (Any, AsyncIterator, Callable, Dict, List, Optional, Set,
                    Tuple, Union, Coroutine) # Ajout de Coroutine
from urllib.parse import parse_qs, unquote_plus, urlparse

# Imports de bibliothèques tierces
import emoji
import isodate
import yaml # Ajouté pour la sortie YAML
import tiktoken
from googleapiclient.discovery import Resource, build
from googleapiclient.errors import HttpError
from pathvalidate import sanitize_filename
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text
from youtube_transcript_api import (CouldNotRetrieveTranscript, NoTranscriptFound,
                                    Transcript, TranscriptsDisabled,
                                    YouTubeTranscriptApi)
from youtube_transcript_api import \
    _errors as YouTubeTranscriptApiErrors # Pour l'accès aux erreurs de fetch

# ==============================================================================
# SECTION 1 : Configuration et Journalisation (Logging)
# ==============================================================================

@dataclass
class Config:
    """Contient les paramètres de configuration pour le scraper."""
    API_KEY: str = os.environ.get("YOUTUBE_API_KEY", "") # Clé API YouTube (via variable d'environnement)
    WORK_FOLDER: Path = Path(__file__).parent.resolve() # Dossier de travail du script
    VIDEOS_FOLDER: Path = WORK_FOLDER / "Vidéos" # Sous-dossier pour les fichiers de sortie
    YOUTUBE_BASE_URL: str = "https://www.youtube.com" # URL de base de YouTube
    BATCH_SIZE: int = 50 # Nombre max d'éléments par requête API (videos/playlistItems)
    MAX_TOKENS_PER_FILE: int = 100000 # Limite approx. de tokens par fichier de sortie (0 = pas de limite)
    TRANSCRIPT_LANGUAGES: Tuple[str, ...] = ("fr", "en", "es", "pt", "it", "de") # Langues de transcription préférées (ordre de priorité)
    MIN_DURATION: timedelta = timedelta(seconds=20) # Durée minimale des vidéos à traiter
    MIN_DELAY: int = 150   # Délai minimal (ms) entre les appels API
    MAX_DELAY: int = 600   # Délai maximal (ms) entre les appels API
    LIMIT_DATE: datetime = datetime(2020, 1, 1, tzinfo=timezone.utc) # Ignorer les vidéos publiées avant cette date
    MAX_SEARCH_RESULTS: int = 200 # Nombre max de vidéos à récupérer pour une recherche
    TRANSCRIPT_BLOCK_DURATION_SECONDS: int = 10 # Regrouper les lignes de transcription par blocs de cette durée
    RESOLVE_CACHE_SIZE: int = 128 # Taille du cache LRU pour la résolution d'ID de chaîne
    TRANSCRIPT_CACHE_SIZE: int = 512 # Taille du cache LRU pour le listage/récupération de transcriptions
    URL_PARSE_CACHE_SIZE: int = 256 # Taille du cache LRU pour l'analyse d'URL
    PLAYLIST_ITEM_CACHE_SIZE: int = 64 # Taille du cache manuel (FIFO) pour les pages d'items de playlist
    TRANSCRIPT_SEMAPHORE_LIMIT: int = 10 # Limite de requêtes concurrentes à l'API de transcription

config = Config()

# S'assurer que les dossiers de travail existent
config.WORK_FOLDER.mkdir(parents=True, exist_ok=True)
config.VIDEOS_FOLDER.mkdir(parents=True, exist_ok=True)

# Configuration de la journalisation (logging)
logging.basicConfig(
    level=logging.INFO, # Niveau de log par défaut
    format="%(asctime)s [%(levelname)s] %(threadName)s %(message)s | %(funcName)s:%(lineno)d", # Format des messages
    handlers=[logging.FileHandler(config.WORK_FOLDER / "youtubingest_cli.log", mode="w", encoding="utf-8")], # Écriture dans un fichier
    datefmt='%Y-%m-%d %H:%M:%S' # Format de la date
)
logger = logging.getLogger(__name__)

# Ajout d'un niveau de log personnalisé "SPAM" pour les détails très fins
SPAM_LEVEL_NUM = 5
logging.addLevelName(SPAM_LEVEL_NUM, "SPAM")
def spam(self, message, *args, **kws):
    """Méthode pour logger au niveau SPAM."""
    # Vérifie si le logger est activé pour ce niveau avant de logger
    if self.isEnabledFor(SPAM_LEVEL_NUM):
        self._log(SPAM_LEVEL_NUM, message, args, **kws)
logging.Logger.spam = spam
# Décommenter la ligne suivante pour activer les logs de niveau SPAM
# logging.getLogger().setLevel(SPAM_LEVEL_NUM)

class QuotaExceededError(Exception):
    """Exception personnalisée levée lorsque le quota de l'API YouTube est dépassé."""
    pass

# ==============================================================================
# SECTION 2 : Modèles de Données (Data Models)
# ==============================================================================

@dataclass
class Video:
    """Représente une vidéo YouTube avec ses métadonnées et sa transcription."""
    id: str # ID unique de la vidéo YouTube
    snippet: Dict[str, Any] = field(default_factory=dict) # Données du 'snippet' de l'API
    contentDetails: Dict[str, Any] = field(default_factory=dict) # Données 'contentDetails' de l'API
    transcript: Optional[Dict[str, str]] = field(default=None, repr=False) # Transcription traitée: {"language": "xx", "transcript": "..."}
    tags: List[str] = field(default_factory=list) # Liste des tags associés à la vidéo
    description_urls: List[str] = field(default_factory=list) # URLs extraites de la description
    video_transcript_language: Optional[str] = None # Code langue réel de la transcription récupérée

    @classmethod
    def from_api_response(cls, item: Dict[str, Any]) -> Video:
        """
        Crée une instance de Video à partir d'un élément de réponse de l'API YouTube (videos.list).

        Args:
            item: Le dictionnaire représentant la ressource vidéo de l'API.

        Returns:
            Une instance de la classe Video.
        """
        snippet = item.get('snippet', {})
        description = snippet.get('description', "")
        return cls(
            id=item.get('id', 'unknown_id'), # Fournir une valeur par défaut si l'ID manque
            snippet=snippet,
            contentDetails=item.get('contentDetails', {}),
            tags=snippet.get('tags', []),
            description_urls=extract_urls(description)
        )

    # --- Propriétés pour un accès facile aux données ---
    @property
    def title(self) -> str:
        """Retourne le titre de la vidéo."""
        return self.snippet.get("title", "")
    @property
    def description(self) -> str:
        """Retourne la description brute de la vidéo."""
        return self.snippet.get("description", "")
    @property
    def channel_id(self) -> str:
        """Retourne l'ID de la chaîne YouTube."""
        return self.snippet.get("channelId", "")
    @property
    def channel_title(self) -> str:
        """Retourne le nom de la chaîne YouTube."""
        return self.snippet.get("channelTitle", "")
    @property
    def url(self) -> str:
        """Retourne l'URL complète de la vidéo."""
        return f"{config.YOUTUBE_BASE_URL}/watch?v={self.id}"
    @property
    def channel_url(self) -> str:
        """Retourne l'URL de la chaîne, si l'ID est disponible."""
        return f"{config.YOUTUBE_BASE_URL}/channel/{self.channel_id}" if self.channel_id else ""
    @property
    def duration_iso(self) -> str:
        """Retourne la durée au format ISO 8601 (ex: 'PT1M30S')."""
        return self.contentDetails.get("duration", "")
    @property
    def published_at_iso(self) -> str:
        """Retourne la date de publication au format ISO 8601 (chaîne)."""
        return self.snippet.get("publishedAt", "")
    @property
    def default_language(self) -> Optional[str]:
        """Retourne la langue par défaut des métadonnées (ex: 'en-US')."""
        return self.snippet.get("defaultLanguage")
    @property
    def default_audio_language(self) -> Optional[str]:
        """Retourne la langue audio par défaut (ex: 'en')."""
        return self.snippet.get("defaultAudioLanguage")

    # --- Méthodes utilitaires ---
    def get_published_at_datetime(self) -> Optional[datetime]:
        """
        Analyse la chaîne publishedAt ISO 8601 en un objet datetime conscient du fuseau horaire (UTC).

        Returns:
            Un objet datetime ou None si l'analyse échoue.
        """
        if not self.published_at_iso: return None
        try:
            ts = self.published_at_iso
            # S'assurer que le format est bien UTC (RFC3339)
            if not ts.endswith('Z'): ts += 'Z'
            # Utiliser strptime comme dans la version originale pour compatibilité
            return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            logger.warning(f"Format de date de publication invalide pour la vidéo {self.id}: {self.published_at_iso}")
            return None

    def get_duration_seconds(self) -> Optional[int]:
        """
        Analyse la chaîne de durée ISO 8601 en nombre total de secondes.

        Returns:
            Le nombre total de secondes (entier) ou None si l'analyse échoue.
        """
        if not self.duration_iso: return None
        try:
            td: timedelta = isodate.parse_duration(self.duration_iso)
            seconds = int(td.total_seconds())
            return seconds if seconds >= 0 else None # Retourner None pour durées négatives
        except (isodate.ISO8601Error, ValueError, TypeError):
            logger.warning(f"Format de durée invalide pour la vidéo {self.id}: {self.duration_iso}")
            return None

    # --- Méthodes de formatage de sortie ---
    def to_texte(self, include_description: bool = True) -> str:
        """
        Formate les données de la vidéo en un bloc de texte brut.

        Args:
            include_description: Inclure la description nettoyée dans la sortie.

        Returns:
            Une chaîne de caractères formatée en texte brut.
        """
        published_at_dt_utc = self.get_published_at_datetime()
        published_at_str = published_at_dt_utc.strftime("%Y-%m-%d %H:%M:%S (UTC)") if published_at_dt_utc else "Date inconnue"
        formatted_duration = format_duration(self.duration_iso)
        tags_str = ", ".join(f"'{tag}'" for tag in self.tags) if self.tags else "Aucun"
        cleaned_title = clean_title(self.title)
        cleaned_description = clean_description(self.description.strip()) if include_description and self.description else ""
        transcription_section = self._get_transcription_section_text() # Utilise l'helper interne

        metadata_lines = [
            f"- Date de publication : {published_at_str}",
            f"- Durée : {formatted_duration}",
            f"- Tags : {tags_str}",
            f"- URL vidéo : <{self.url}>",
            f"- Nom chaîne : {self.channel_title}",
        ]
        if self.channel_url:
            metadata_lines.append(f"- URL chaîne : <{self.channel_url}>")

        texte = f"Titre vidéo : {cleaned_title}\n\nMétadonnées :\n" + "\n".join(metadata_lines) + "\n\n"
        if include_description and cleaned_description:
            texte += f"Description :\n{cleaned_description}\n\n"
        texte += transcription_section
        return texte.strip()

    def to_markdown(self, include_description: bool = True) -> str:
        """
        Formate les données de la vidéo en une section Markdown.

        Args:
            include_description: Inclure la description nettoyée dans la sortie.

        Returns:
            Une chaîne de caractères formatée en Markdown.
        """
        published_at_dt_utc = self.get_published_at_datetime()
        published_at_str = published_at_dt_utc.strftime("%Y-%m-%d %H:%M:%S (UTC)") if published_at_dt_utc else "Date inconnue"
        formatted_duration = format_duration(self.duration_iso)
        # Formater les tags comme du code inline en Markdown
        tags_str = ", ".join(f"`{tag}`" for tag in self.tags) if self.tags else "Aucun"
        cleaned_title = clean_title(self.title)
        cleaned_description = clean_description(self.description.strip()) if include_description and self.description else ""
        transcript_lang, transcript_text = self._get_transcript_lang_and_text() # Utilise l'helper interne

        md_lines = [f"## {cleaned_title}"] # Titre de niveau 2
        md_lines.append("\n### Métadonnées") # Sous-section pour les métadonnées
        md_lines.append(f"*   **Date de publication**: {published_at_str}")
        md_lines.append(f"*   **Durée**: {formatted_duration}")
        md_lines.append(f"*   **Tags**: {tags_str}")
        md_lines.append(f"*   **URL vidéo**: <{self.url}>")
        md_lines.append(f"*   **Nom chaîne**: {self.channel_title}")
        if self.channel_url:
            md_lines.append(f"*   **URL chaîne**: <{self.channel_url}>")

        if include_description and cleaned_description:
            md_lines.append("\n### Description") # Sous-section pour la description
            # Ajouter des sauts de ligne avant/après pour un meilleur rendu
            md_lines.append(f"\n{cleaned_description}\n")

        if transcript_text:
            md_lines.append(f"\n### Transcription (Langue: `{transcript_lang}`)") # Sous-section transcription
            # Utiliser un bloc de code 'text' pour la transcription
            md_lines.append(f"\n```text\n{transcript_text}\n```\n")
        else:
            md_lines.append("\n### Transcription")
            md_lines.append("\n*Aucune transcription disponible/traitée.*")

        return "\n".join(md_lines).strip()

    def to_dict(self, include_description: bool = True) -> Dict[str, Any]:
        """
        Retourne une représentation dictionnaire des données de la vidéo,
        adaptée pour la sérialisation (ex: YAML, JSON).

        Args:
            include_description: Inclure la description nettoyée dans le dictionnaire.

        Returns:
            Un dictionnaire contenant les données clés de la vidéo.
        """
        published_at_dt = self.get_published_at_datetime()
        transcript_lang, transcript_text = self._get_transcript_lang_and_text() # Utilise l'helper interne

        data: Dict[str, Any] = {
            "id": self.id,
            "title": clean_title(self.title),
            "url": self.url,
            "published_at_iso": self.published_at_iso if self.published_at_iso else None,
            "published_at_utc": published_at_dt.isoformat() if published_at_dt else None, # Format ISO standard pour datetime
            "duration_iso": self.duration_iso if self.duration_iso else None,
            "duration_seconds": self.get_duration_seconds(), # Inclure la durée en secondes
            "channel_name": self.channel_title,
            "channel_id": self.channel_id,
            "channel_url": self.channel_url if self.channel_url else None,
            "tags": self.tags if self.tags else [], # Assurer une liste vide si pas de tags
            "description_urls": self.description_urls if self.description_urls else [], # Assurer une liste vide
        }
        if include_description:
            # Ajouter la description seulement si demandée et si elle existe
            cleaned_desc = clean_description(self.description.strip()) if self.description else None
            data["description"] = cleaned_desc

        # Ajouter les informations de transcription
        data["transcript_language"] = transcript_lang # Sera None si pas de transcript
        data["transcript_text"] = transcript_text # Sera None si pas de transcript

        # Optionnel : Nettoyer les clés ayant une valeur None pour un YAML/JSON plus concis
        return {k: v for k, v in data.items() if v is not None}

    # --- Helpers internes pour le formatage ---
    def _get_transcription_section_text(self) -> str:
        """Helper interne pour obtenir la section transcription formatée pour la sortie TXT."""
        lang, text = self._get_transcript_lang_and_text()
        if text:
            return f"Transcription (langue {lang}) :\n{text}\n"
        return "Transcription : Aucune transcription disponible/traitée.\n"

    def _get_transcript_lang_and_text(self) -> Tuple[Optional[str], Optional[str]]:
        """Helper interne pour récupérer de manière sûre la langue et le texte de la transcription."""
        if self.transcript and isinstance(self.transcript, dict):
            # Utilise la langue stockée lors du fetch, sinon celle du dict transcript
            lang = self.video_transcript_language or self.transcript.get('language')
            text = self.transcript.get('transcript')
            return lang, text
        return None, None # Retourne None pour les deux si pas de transcript

# ==============================================================================
# SECTION 3 : Utilitaires de Traitement de Texte
# ==============================================================================

@functools.lru_cache(maxsize=1024)
def extract_urls(text: str) -> List[str]:
    """
    Extrait toutes les URLs d'une chaîne de caractères donnée.

    Args:
        text: La chaîne de caractères à analyser.

    Returns:
        Une liste des URLs trouvées.
    """
    if not text: return []
    try:
        # Regex robuste pour capturer les URLs, gérant les parenthèses et caractères de fin courants
        urls = re.findall(r'https?://[^\s<>"\')]+(?:\([^\s<>"]*\)|[^\s<>"\')`])', text)
        # Nettoyer la ponctuation finale des URLs capturées
        return [url.rstrip('.,;)!?]\'"') for url in urls]
    except Exception as e:
        logger.error(f"Erreur lors de l'extraction des URLs: {e}")
        return []

@functools.lru_cache(maxsize=512)
def clean_title(title: str) -> str:
    """
    Nettoie un titre de vidéo en supprimant les éléments superflus courants
    et en le rendant sûr pour une utilisation comme nom de fichier.

    Args:
        title: Le titre original de la vidéo.

    Returns:
        Le titre nettoyé.
    """
    if not title: return "Titre_Inconnu"
    try:
        cleaned = emoji.replace_emoji(title, replace='') # Supprimer les emojis

        # Regex améliorée pour supprimer les motifs courants :
        # - Texte entre crochets/parenthèses : [info], (info)
        # - Hashtags : #motclé
        # - Indicateurs pub/sponsor : ad:, pub:, sponsor(ed): ...jusqu'à la fin
        # - Marqueurs courants : *NEW*, !LIVE!, X watching now
        # - Séparateurs pipe et texte suivant : | Suite du titre
        # - Symboles 'play' en début de ligne : ►
        cleaned = re.sub(
            r'[\[\(].*?[\]\)]|#\w+|\b(ad|pub|sponsor(ed)?)\b:?.*$|\*?NEW\*?|\!?LIVE\!?|\d+\s+watching now|\|.*$|^\s*►\s*',
            '', cleaned, flags=re.I | re.UNICODE
        )

        # Rendre sûr pour le système de fichiers (multi-plateforme)
        cleaned = sanitize_filename(cleaned.strip(), platform="universal")
        # Normaliser les espaces multiples en un seul espace
        cleaned = ' '.join(cleaned.split()).strip()
        # Retourner un titre par défaut si le nettoyage résulte en une chaîne vide
        return cleaned if cleaned else "Titre_Nettoye_Vide"
    except Exception as e:
        logger.error(f"Erreur lors du nettoyage du titre '{title}': {e}")
        # Solution de repli : nettoyage de base du nom de fichier
        safe_fallback = sanitize_filename(title, platform="universal") if title else "Titre_Erreur_Nettoyage"
        return safe_fallback if safe_fallback else "Titre_Erreur_Nettoyage"

@functools.lru_cache(maxsize=512)
def clean_description(text: str) -> str:
    """
    Nettoie le texte de description en supprimant le HTML, les URLs, les emojis,
    les caractères de formatage Markdown et les espaces excessifs.

    Args:
        text: La description originale.

    Returns:
        La description nettoyée.
    """
    if not text: return ""
    try:
        text = re.sub(r'<[^>]+>', ' ', text) # Supprimer les balises HTML
        text = emoji.replace_emoji(text, replace='') # Supprimer les emojis

        # Supprimer les images et liens Markdown de manière plus fiable
        text = re.sub(r'!\[.*?\]\(https?://\S+\)', '', text) # Images: ![alt](url)
        text = re.sub(r'\[(.*?)\]\(https?://\S+\)', r'\1', text) # Liens: [texte](url) -> texte

        text = re.sub(r'https?://\S+', '', text) # Supprimer les URLs restantes
        # Supprimer les caractères spéciaux/Markdown courants
        text = re.sub(r'[\`*~\[\]{}<>|#_]', '', text)

        # Normaliser les sauts de ligne et les espaces
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        text = re.sub(r'[ \t]+', ' ', text) # Remplacer espaces/tabs multiples par un seul espace
        text = re.sub(r'\n{3,}', '\n\n', text) # Réduire les lignes vides multiples à deux max

        # Conserver les caractères imprimables + newline/tab, supprimer les autres.
        # ATTENTION : Peut supprimer des caractères légitimes non-latins ou symboles.
        # Évaluer si c'est trop agressif pour le LLM cible.
        text = ''.join(char for char in text if char.isprintable() or char in '\n\t')

        return text.strip()
    except Exception as e:
        logger.error(f"Erreur lors du nettoyage de la description: {e}")
        return text # Retourner le texte original en cas d'erreur

@functools.lru_cache(maxsize=256)
def format_duration(duration_iso: str) -> str:
    """
    Formate une chaîne de durée ISO 8601 (ex: 'PT1M30S') en HH:MM:SS ou MM:SS.

    Args:
        duration_iso: La chaîne de durée au format ISO 8601.

    Returns:
        La durée formatée ou une chaîne indiquant une erreur/inconnue.
    """
    if not duration_iso: return "Durée inconnue"
    try:
        td: timedelta = isodate.parse_duration(duration_iso)
        total_seconds = int(td.total_seconds())
        if total_seconds < 0: return "Durée invalide" # Gérer les durées négatives

        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        # Afficher les heures seulement si elles sont > 0
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    except (isodate.ISO8601Error, ValueError, TypeError):
        logger.warning(f"Format de durée invalide : {duration_iso}")
        return duration_iso # Retourner l'original en cas d'erreur

@functools.lru_cache(maxsize=1024)
def _format_timestamp(seconds: float) -> str:
    """
    Formate un nombre de secondes en une chaîne de caractères HH:MM:SS.

    Args:
        seconds: Le nombre de secondes (peut être flottant).

    Returns:
        Le timestamp formaté.
    """
    try:
        if seconds < 0: seconds = 0.0 # Assurer que les secondes ne sont pas négatives
        total_seconds_int = int(seconds)
        hours, remainder = divmod(total_seconds_int, 3600)
        minutes, seconds_part = divmod(remainder, 60)
        # Toujours retourner HH:MM:SS pour la cohérence dans les transcriptions
        return f"{hours:02d}:{minutes:02d}:{seconds_part:02d}"
    except Exception as e:
        logger.warning(f"Erreur lors du formatage du timestamp pour {seconds}s: {e}")
        return "??:??:??" # Timestamp d'erreur

# ==============================================================================
# SECTION 4 : Affichage de la Progression CLI
# ==============================================================================

class ProgressStatus:
    """Constantes simples pour les statuts d'affichage de la progression."""
    PENDING = "pending"; IN_PROGRESS = "in_progress"; DONE = "done"; ERROR = "error"
    INFO = "info"; WARNING = "warning"; SORT = "sort"; QUOTA = "quota"; SKIPPED = "skipped"

class ProgressDisplay:
    """Gère l'affichage en direct de la progression dans la console en utilisant Rich."""
    # Mapping des statuts aux icônes emoji
    ICONS: Dict[str, str] = {
        ProgressStatus.PENDING: "🔘", ProgressStatus.IN_PROGRESS: "⏳", ProgressStatus.DONE: "🟢",
        ProgressStatus.ERROR: "❌", ProgressStatus.INFO: "ℹ️", ProgressStatus.WARNING: "⚠️",
        ProgressStatus.SORT: "⇅", ProgressStatus.QUOTA: "🚫", ProgressStatus.SKIPPED: "⚪"
    }
    # Mapping des statuts aux styles Rich
    STYLE_MAP: Dict[str, str] = {
        ProgressStatus.IN_PROGRESS: "yellow", ProgressStatus.DONE: "green", ProgressStatus.ERROR: "red",
        ProgressStatus.WARNING: "yellow", ProgressStatus.SORT: "cyan", ProgressStatus.QUOTA: "bold red",
        ProgressStatus.SKIPPED: "dim", ProgressStatus.PENDING: "dim", ProgressStatus.INFO: "blue"
    }
    # Mapping des types de message aux préfixes pour les messages généraux
    PREFIX_MAP: Dict[str, str] = {
        ProgressStatus.ERROR: f"{ICONS[ProgressStatus.ERROR]} ERREUR: ",
        ProgressStatus.WARNING: f"{ICONS[ProgressStatus.WARNING]} ATTENTION: ",
        ProgressStatus.QUOTA: f"{ICONS[ProgressStatus.QUOTA]} QUOTA DÉPASSÉ: ",
        ProgressStatus.SKIPPED: f"{ICONS[ProgressStatus.SKIPPED]} IGNORÉ: ",
        ProgressStatus.DONE: f"{ICONS[ProgressStatus.DONE]} SUCCÈS: ",
        ProgressStatus.INFO: f"    {ICONS[ProgressStatus.INFO]} INFO: " # Indentation pour les infos
    }

    def __init__(self):
        """Initialise le ProgressDisplay."""
        self.console: Console = Console(stderr=True, highlight=False) # Sortie sur stderr pour l'UI
        self.total_urls: int = 0 # Nombre total d'URLs à traiter
        self.output_lines: List[RenderableType] = [] # Lignes à afficher dans le Live display
        # Structure: {url_index: {step_number: {'line_index': int, 'step_name': str}}}
        self.url_steps_mapping: Dict[int, Dict[int, Dict[str, Any]]] = {}
        self.url_counter: int = 0 # Compteur pour assigner un index unique à chaque URL traitée
        self._lock: asyncio.Lock = asyncio.Lock() # Verrou pour protéger l'accès concurrent aux données partagées
        self.live: Optional[Live] = None # Instance Rich Live pour l'affichage dynamique

    def show_header(self) -> None:
        """Affiche l'en-tête initial du script."""
        self.console.print("\n[bold blue]YouTubingest CLI[/]")
        self.console.print("[dim]Extraction métadonnées, transcriptions, tags YouTube[/]\n")

    def show_menu(self) -> Tuple[str, str, str, bool, bool]:
        """
        Affiche le menu d'entrée et demande les options à l'utilisateur.

        Returns:
            Un tuple contenant: (mode_entree, valeur_entree, format_sortie, inclure_transcription, inclure_description).
        """
        self.console.print("[bold]Options d'entrée :[/]")
        self.console.print("1. URL YouTube (Chaîne, Vidéo, Playlist, Recherche)")
        self.console.print("2. Fichier d'URLs")
        mode = Prompt.ask("[blue]Mode[/]", choices=["1", "2"], default="1", console=self.console)

        default_file = "URL_dev.txt" # Fichier par défaut suggéré en mode 2
        prompt_text = "[blue]URL YouTube[/]" if mode == "1" else "[blue]Chemin Fichier[/]"
        default_value = default_file if mode == '2' and Path(default_file).exists() else None
        input_val = Prompt.ask(prompt_text, default=default_value, console=self.console)

        # --- Nouveau Prompt pour le Format de Sortie ---
        self.console.print("\n[bold]Options de sortie :[/]")
        output_format = Prompt.ask(
            "[blue]Format de sortie[/]",
            choices=["txt", "md", "yaml"], # Options disponibles
            default="txt", # Format par défaut
            console=self.console
        )
        # --- Fin Nouveau Prompt ---

        inc_transcript = Confirm.ask("\n[blue]Inclure transcriptions ?[/]", default=True, console=self.console)
        inc_desc = Confirm.ask("[blue]Inclure descriptions ?[/]", default=True, console=self.console)
        self.console.print("-" * 30) # Séparateur visuel
        # Retourne toutes les options choisies
        return mode, input_val or "", output_format, inc_transcript, inc_desc

    async def start_processing(self, total_urls: int) -> None:
        """Initialise ou réinitialise l'affichage Live pour une nouvelle série de traitements."""
        async with self._lock: # Assurer l'atomicité de la réinitialisation
            self.total_urls = total_urls
            self.output_lines, self.url_steps_mapping, self.url_counter = [], {}, 0
            if self.live is None:
                 # Créer l'instance Live si elle n'existe pas
                 self.live = Live("", refresh_per_second=4, console=self.console, transient=True, vertical_overflow="visible")
            try:
                if not self.live.is_started:
                    self.live.start(refresh=True) # Démarrer le Live display
                else:
                    # Si déjà démarré (ex: run précédent), effacer l'ancien contenu
                    self.live.update(Group(""), refresh=True)
                logger.debug(f"Affichage Live démarré/réinitialisé pour {total_urls} URLs.")
            except Exception as e:
                logger.error(f"Erreur lors du démarrage/réinitialisation de l'affichage Live: {e}", exc_info=True)

    async def show_url_header(self, url: str) -> int:
        """
        Ajoute l'en-tête pour le traitement d'une URL spécifique à l'affichage Live.

        Args:
            url: L'URL en cours de traitement.

        Returns:
            L'index assigné à cette URL pour les mises à jour futures.
        """
        async with self._lock:
            self.url_counter += 1
            url_index = self.url_counter # Index unique pour cette URL
            # Ajouter la ligne d'en-tête de l'URL
            self.output_lines.append(Text(f"\nTraitement URL {url_index}/{self.total_urls} : {url}\n", style="bold blue"))
            # Définir les étapes pour cette URL
            steps = ["Analyse URL", "Récup IDs Vidéos", "Récup Détails/Transcr.", "Tri Vidéos", "Sauvegarde"]
            self.url_steps_mapping[url_index] = {}
            # Ajouter une ligne pour chaque étape avec le statut initial 'pending'
            for i, step_name in enumerate(steps, 1):
                line = Text(f"  Étape {i}/{len(steps)} : {self.ICONS[ProgressStatus.PENDING]} {step_name}", style=self.STYLE_MAP[ProgressStatus.PENDING])
                self.output_lines.append(line)
                # Stocker l'index de la ligne et le nom de l'étape pour les mises à jour futures
                self.url_steps_mapping[url_index][i] = {'line_index': len(self.output_lines) - 1, 'step_name': step_name}
            # Mettre à jour l'affichage Live
            await self._update_live_display_unsafe()
            return url_index # Retourner l'index assigné

    async def update_step(self, url_index: int, step_number: int, status: str, progress_percent: Optional[float] = None, message: Optional[str] = None) -> None:
        """
        Met à jour le statut d'une étape spécifique pour une URL dans l'affichage Live.

        Args:
            url_index: L'index de l'URL (retourné par show_url_header).
            step_number: Le numéro de l'étape (1-based).
            status: Le nouveau statut (ex: ProgressStatus.IN_PROGRESS).
            progress_percent: Pourcentage de progression (pour statut IN_PROGRESS).
            message: Message additionnel à afficher pour l'étape.
        """
        async with self._lock:
            # Vérifier si l'URL et l'étape existent dans notre mapping
            if url_index not in self.url_steps_mapping or step_number not in self.url_steps_mapping[url_index]:
                logger.warning(f"Tentative de mise à jour d'une étape inexistante : URL {url_index}, Étape {step_number}")
                return
            try:
                step_info = self.url_steps_mapping[url_index][step_number]
                line_index, step_name = step_info['line_index'], step_info['step_name']
                num_steps = len(self.url_steps_mapping[url_index])

                # Vérifier la validité de l'index de ligne
                if not (0 <= line_index < len(self.output_lines)):
                    logger.error(f"Index de ligne invalide ({line_index}) pour étape {step_number}, URL {url_index}")
                    return

                # Construire la nouvelle ligne de texte pour l'étape
                emoji_icon = self.ICONS.get(status, self.ICONS[ProgressStatus.INFO]) # Icône par défaut INFO
                progress = f" ({progress_percent:.0f}%)" if status == ProgressStatus.IN_PROGRESS and progress_percent is not None else ""
                style = self.STYLE_MAP.get(status, self.STYLE_MAP[ProgressStatus.PENDING]) # Style par défaut PENDING
                display_msg = ""
                if message:
                    # Tronquer les messages longs pour l'affichage
                    truncated_msg = (message[:70] + '…') if len(message) > 70 else message
                    display_msg = f" ({truncated_msg})"

                # Mettre à jour la ligne correspondante dans la liste des lignes à afficher
                self.output_lines[line_index] = Text(f"  Étape {step_number}/{num_steps} : {emoji_icon} {step_name}{progress}{display_msg}", style=style)
                # Rafraîchir l'affichage Live
                await self._update_live_display_unsafe()
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour de l'étape {step_number} (URL {url_index}): {e}", exc_info=True)

    async def show_message_in_live(self, message_type: str, message: str) -> None:
        """Ajoute un message général (info, avertissement, erreur) à l'affichage Live."""
        async with self._lock:
            style = self.STYLE_MAP.get(message_type, self.STYLE_MAP[ProgressStatus.INFO])
            prefix = self.PREFIX_MAP.get(message_type, self.PREFIX_MAP[ProgressStatus.INFO])
            # Ajouter le message formaté à la fin de la liste des lignes
            self.output_lines.append(Text(f"{prefix}{message}", style=style))
            # Rafraîchir l'affichage
            await self._update_live_display_unsafe()

    # Raccourcis pour les types de messages courants
    async def show_error(self, message: str): await self.show_message_in_live(ProgressStatus.ERROR, message)
    async def show_warning(self, message: str): await self.show_message_in_live(ProgressStatus.WARNING, message)
    async def show_info(self, message: str): await self.show_message_in_live(ProgressStatus.INFO, message)
    async def show_success(self, message: str): await self.show_message_in_live(ProgressStatus.DONE, message)
    async def show_quota_exceeded(self, message: str): await self.show_message_in_live(ProgressStatus.QUOTA, message)
    async def show_skipped(self, message: str): await self.show_message_in_live(ProgressStatus.SKIPPED, message)

    def show_file_table(self, files: List[Tuple[Path, int, int]]) -> None:
        """Affiche un tableau récapitulatif des fichiers de sortie créés."""
        # Ne rien afficher si aucun fichier n'a été créé
        if not files:
            self.console.print(f"\n{self.ICONS[ProgressStatus.INFO]} [blue]INFO: Aucun fichier de données créé.[/]")
            return

        self.console.print("\n[bold underline]Fichiers Créés :[/]")
        table = Table(show_header=True, header_style="bold magenta", border_style="dim", expand=True)
        table.add_column("Fichier Relatif", style="cyan", no_wrap=False, overflow="fold", min_width=40)
        table.add_column("Tokens (estimés)", style="blue", justify="right")
        table.add_column("Vidéos", style="green", justify="right")

        total_tokens, total_videos = 0, 0
        for file_path, tokens, video_count in files:
            try:
                # Afficher le chemin relatif au dossier de travail pour la concision
                display_path = str(file_path.relative_to(config.WORK_FOLDER))
            except ValueError:
                display_path = str(file_path) # Chemin absolu si non relatif
            # Formater les nombres pour la lisibilité
            table.add_row(display_path, f"{tokens:,}".replace(",", " "), str(video_count))
            total_tokens += tokens
            total_videos += video_count

        # Ajouter une ligne de total
        table.add_row(
            Text("TOTAL", style="bold"),
            Text(f"{total_tokens:,}".replace(",", " "), style="bold blue"),
            Text(str(total_videos), style="bold green")
        )
        self.console.print(table)

    async def _update_live_display_unsafe(self) -> None:
        """Méthode interne pour mettre à jour l'affichage Rich Live (doit être appelée sous verrou)."""
        if self.live and self.live.is_started:
            try:
                # Créer un groupe Rich avec toutes les lignes actuelles
                renderable = Group(*self.output_lines)
                # Mettre à jour le contenu du Live display
                self.live.update(renderable, refresh=True)
            except Exception as e:
                logger.error(f"Erreur lors de la mise à jour de l'affichage live: {e}", exc_info=True)

    async def stop(self) -> None:
        """Arrête proprement l'affichage Live."""
        async with self._lock: # Verrouiller pour éviter les conditions de course
            if self.live and self.live.is_started:
                try:
                    self.live.stop() # Arrêter le rafraîchissement
                    logger.debug("Affichage Live arrêté.")
                except Exception as e:
                    logger.error(f"Erreur lors de l'arrêt de l'affichage Live: {e}")
            self.live = None # Réinitialiser l'instance Live

# ==============================================================================
# SECTION 5 : Client API YouTube
# ==============================================================================

class ContentType:
    """Constantes simples pour les types de contenu YouTube."""
    CHANNEL = "channel"; VIDEO = "video"; PLAYLIST = "playlist"; SEARCH = "search"
    # Types internes avant résolution vers un ID de chaîne
    _CHANNEL_HANDLE = "channel_handle"; _CHANNEL_CUSTOM = "channel_custom"; _CHANNEL_USER = "channel_user"

class YouTubeAPIClient:
    """Gère les interactions avec l'API YouTube Data v3."""
    # Patterns Regex pour identifier les types d'URL YouTube
    URL_PATTERNS: Dict[str, str] = {
        ContentType._CHANNEL_HANDLE: r"(?:https?://)?(?:www\.)?youtube\.com/@(?P<identifier>[a-zA-Z0-9_.-]+)",
        ContentType.VIDEO: r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/)(?P<identifier>[a-zA-Z0-9_-]{11})",
        ContentType.PLAYLIST: r"(?:https?://)?(?:www\.)?youtube\.com/(?:playlist|watch)\?.*?list=(?P<identifier>[a-zA-Z0-9_-]+)",
        ContentType.CHANNEL: r"(?:https?://)?(?:www\.)?youtube\.com/channel/(?P<identifier>UC[a-zA-Z0-9_-]+)", # ID de chaîne direct
        ContentType._CHANNEL_CUSTOM: r"(?:https?://)?(?:www\.)?youtube\.com/c/(?P<identifier>[a-zA-Z0-9_.-]+)",
        ContentType._CHANNEL_USER: r"(?:https?://)?(?:www\.)?youtube\.com/user/(?P<identifier>[a-zA-Z0-9_.-]+)",
        ContentType.SEARCH: r"(?:https?://)?(?:www\.)?youtube\.com/results\?search_query=(?P<query>[^&]+)" # Recherche via paramètre URL
    }
    # Types nécessitant un appel API supplémentaire pour résoudre en ID de chaîne
    RESOLVABLE_TYPES: Set[str] = {ContentType._CHANNEL_HANDLE, ContentType._CHANNEL_CUSTOM, ContentType._CHANNEL_USER}
    # Mapping des types bruts (internes ou directs) vers les types de contenu finaux
    CONTENT_TYPE_MAP: Dict[str, str] = {
        ContentType._CHANNEL_HANDLE: ContentType.CHANNEL, ContentType.VIDEO: ContentType.VIDEO,
        ContentType.PLAYLIST: ContentType.PLAYLIST, ContentType.CHANNEL: ContentType.CHANNEL,
        ContentType._CHANNEL_CUSTOM: ContentType.CHANNEL, ContentType._CHANNEL_USER: ContentType.CHANNEL,
        ContentType.SEARCH: ContentType.SEARCH
    }

    def __init__(self, api_key: str):
        """
        Initialise le client API YouTube.

        Args:
            api_key: La clé API YouTube Data v3.

        Raises:
            ValueError: Si la clé API est manquante ou si l'initialisation échoue.
        """
        logger.info("Initialisation du client API YouTube (Async)")
        if not api_key:
            logger.critical("Clé API manquante.")
            raise ValueError("Clé API YouTube non fournie.")
        try:
            # Désactiver le cache de découverte pour éviter problèmes potentiels avec async/threads
            self.youtube: Resource = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
            logger.debug("Objet Ressource API YouTube créé avec succès.")
        except Exception as e:
            logger.critical(f"Échec de l'initialisation de l'API YouTube: {e}", exc_info=True)
            raise ValueError("Impossible d'initialiser l'API YouTube. Vérifiez la clé/connexion.") from e

        # Générateur pour les délais aléatoires entre les appels API
        self._delay_generator: Callable[[], Coroutine[Any, Any, None]] = \
            lambda: asyncio.sleep(random.uniform(config.MIN_DELAY, config.MAX_DELAY) / 1000.0)

        # Cache FIFO simple pour les pages playlistItems afin de réduire les appels redondants lors de la pagination
        self._playlist_item_cache: Dict[Tuple[str, Optional[str]], Dict[str, Any]] = {}
        self._playlist_item_cache_lock: asyncio.Lock = asyncio.Lock() # Verrou pour l'accès au cache

    async def _execute_api_call(self, api_request: Any, cost: int = 1) -> Dict[str, Any]:
        """
        Exécute une requête API googleapiclient de manière asynchrone dans un thread séparé,
        gère les erreurs HTTP courantes et applique un délai.

        Args:
            api_request: L'objet requête googleapiclient (ex: youtube.videos().list(...)).
            cost: Un coût indicatif pour la journalisation (non utilisé par l'API).

        Returns:
            Le dictionnaire de réponse de l'API.

        Raises:
            QuotaExceededError: Si le quota API est dépassé.
            ValueError: Pour les erreurs de configuration/permission (403).
            HttpError: Pour les autres erreurs HTTP non gérées.
            Exception: Pour les erreurs inattendues lors de l'exécution.
        """
        request_uri = getattr(api_request, 'uri', 'URI Inconnu') # Obtenir l'URI pour les logs
        logger.debug(f"Exécution de l'appel API (coût ~{cost}): {request_uri}")
        try:
            # Exécuter la méthode synchrone execute() dans un thread
            response: Dict[str, Any] = await asyncio.to_thread(api_request.execute)
            await self._delay_generator() # Appliquer le délai après un appel réussi
            return response
        except HttpError as e:
            # Analyser l'erreur HTTP
            status_code = e.resp.status
            content_bytes = getattr(e, 'content', b'') # Contenu de la réponse d'erreur
            content_str = content_bytes.decode('utf-8', errors='replace')
            uri = getattr(e, 'uri', 'URI Inconnu') # Redondant mais sûr

            if status_code == 403: # Erreur Forbidden
                if 'quotaExceeded' in content_str or 'servingLimitExceeded' in content_str:
                    logger.critical(f"Quota API YouTube dépassé détecté (URI: {uri}).")
                    raise QuotaExceededError("Quota API YouTube dépassé.") from e
                elif 'forbidden' in content_str or 'accessNotConfigured' in content_str:
                     logger.error(f"Erreur API 403 Forbidden/AccessNotConfigured: {uri} - Vérifiez permissions/restrictions clé API.", exc_info=False)
                     raise ValueError(f"Accès interdit/non configuré (403) à {uri}. Vérifiez la clé API.") from e
                else:
                    # Autre erreur 403 non spécifique
                    logger.error(f"Erreur API 403 non gérée: {uri} - {content_str}", exc_info=False)
                    raise e # Remonter l'erreur 403 générique
            elif status_code == 404: # Erreur Not Found
                logger.warning(f"Ressource API non trouvée (404): {uri}")
                raise e # Remonter pour une gestion spécifique par l'appelant
            else:
                # Autres erreurs HTTP (ex: 500, 503)
                logger.error(f"Erreur API {status_code}: {uri} - {content_str}", exc_info=False)
                raise e # Remonter les autres erreurs HTTP
        except Exception as e:
            # Erreurs inattendues (ex: problème réseau avant l'appel)
            logger.error(f"Erreur inattendue lors de l'exécution de l'appel API ({request_uri}): {e}", exc_info=True)
            raise

    @functools.lru_cache(maxsize=config.URL_PARSE_CACHE_SIZE)
    def extract_identifier_sync(self, url: str) -> Optional[Tuple[str, str]]:
        """
        Analyse de manière synchrone une URL pour trouver l'identifiant YouTube et son type brut.
        Utilise un cache LRU pour éviter les analyses répétées.

        Args:
            url: L'URL YouTube à analyser.

        Returns:
            Un tuple (identifiant, type_brut) ou None si aucun pattern ne correspond.
        """
        logger.spam(f"Analyse URL (sync pour cache): {url}")
        if not url or not isinstance(url, str): return None
        try:
            # Priorité 1: Recherche via /results?search_query=
            parsed_url = urlparse(url)
            if 'youtube.com' in parsed_url.netloc and parsed_url.path == '/results':
                query_params = parse_qs(parsed_url.query)
                query = query_params.get('search_query', [None])[0]
                if query:
                    decoded_query = unquote_plus(query)
                    logger.debug(f"Type Recherche détecté (paramètre URL): '{decoded_query}'")
                    return decoded_query, ContentType.SEARCH

            # Priorité 2: Patterns spécifiques (vidéo, playlist, ID de chaîne) - L'ordre est important
            ordered_patterns = [ContentType.VIDEO, ContentType.PLAYLIST, ContentType.CHANNEL]
            for type_key in ordered_patterns:
                match = re.match(self.URL_PATTERNS[type_key], url)
                if match:
                    identifier = match.groupdict().get("identifier")
                    if identifier: # Vérifier que l'identifiant a été capturé
                        logger.debug(f"Pattern '{type_key}' trouvé. Type: {type_key}, ID: {identifier}")
                        return identifier, type_key

            # Priorité 3: Patterns nécessitant résolution (handle, custom, user)
            resolvable_patterns = [ContentType._CHANNEL_HANDLE, ContentType._CHANNEL_CUSTOM, ContentType._CHANNEL_USER]
            for type_key in resolvable_patterns:
                 match = re.match(self.URL_PATTERNS[type_key], url)
                 if match:
                     identifier = match.groupdict().get("identifier")
                     if identifier:
                         logger.debug(f"Pattern '{type_key}' trouvé (nécessite résolution). Type brut: {type_key}, ID brut: {identifier}")
                         return identifier, type_key # Retourner le type brut ici

            # Solution de repli: Pattern de recherche générique (si non détecté via /results?)
            # Ce regex pourrait être moins spécifique, donc en dernier recours
            search_pattern_fallback = r"(?:https?://)?(?:www\.)?youtube\.com/results\?.*?search_query=(?P<query>[^&]+)"
            match_fallback = re.match(search_pattern_fallback, url)
            if match_fallback and match_fallback.groupdict().get("query"):
                 decoded_query = unquote_plus(match_fallback.group("query"))
                 logger.debug(f"Type Recherche détecté (pattern de repli): '{decoded_query}'")
                 return decoded_query, ContentType.SEARCH

            # Si aucun pattern ne correspond
            logger.warning(f"Aucun pattern YouTube valide trouvé pour l'URL: {url}")
            return None
        except Exception as e:
            # Gérer les erreurs potentielles lors de l'analyse regex/urlparse
            logger.error(f"Erreur lors de l'analyse de l'URL '{url}': {e}", exc_info=True)
            return None

    async def extract_identifier(self, url: str) -> Optional[Tuple[str, str]]:
        """
        Extrait de manière asynchrone l'identifiant et le type de contenu final d'une URL YouTube.
        Résout les handles, URLs personnalisées et URLs utilisateur en ID de chaîne.

        Args:
            url: L'URL YouTube à traiter.

        Returns:
            Un tuple (identifiant, type_contenu_final) ou None si invalide ou échec de résolution.
            Le type_contenu_final sera l'une des valeurs de ContentType (CHANNEL, VIDEO, PLAYLIST, SEARCH).
        """
        # Utiliser la version synchrone mise en cache pour l'analyse initiale
        sync_result = self.extract_identifier_sync(url)
        if not sync_result: return None # URL invalide ou non reconnue

        identifier, raw_type_key = sync_result

        # Si le type nécessite une résolution (handle, custom, user)
        if raw_type_key in self.RESOLVABLE_TYPES:
            logger.info(f"Résolution nécessaire pour {raw_type_key}: {identifier}")
            try:
                # Appeler la méthode de résolution asynchrone
                channel_id = await self._resolve_channel_identifier(raw_type_key, identifier)
                if channel_id:
                    logger.info(f"'{identifier}' ({raw_type_key}) résolu en ID de Chaîne: {channel_id}")
                    # Le type final est 'channel' après résolution
                    return channel_id, ContentType.CHANNEL
                else:
                    # La résolution a échoué (ex: handle/custom URL invalide)
                    logger.warning(f"Échec de la résolution de '{identifier}' ({raw_type_key}) en ID de Chaîne.")
                    return None
            except QuotaExceededError:
                raise # Propager immédiatement les erreurs de quota
            except Exception as e:
                # Gérer les erreurs inattendues pendant la résolution
                logger.error(f"Erreur lors de la résolution asynchrone de {identifier} ({raw_type_key}): {e}", exc_info=True)
                return None
        else:
             # Pour les types non résolvables (video, playlist, channel_id, search)
             # Mapper le type brut vers le type de contenu final (ex: channel_id -> channel)
             final_content_type = self.CONTENT_TYPE_MAP.get(raw_type_key, raw_type_key)
             return identifier, final_content_type

    @functools.lru_cache(maxsize=config.RESOLVE_CACHE_SIZE)
    def _resolve_channel_identifier_sync_logic(self, identifier_type: str, identifier: str) -> Optional[str]:
        """
        Logique synchrone pour résoudre les handles/URLs personnalisées/utilisateurs en ID de chaîne.
        Utilise un cache LRU. C'est cette fonction qui est appelée via asyncio.to_thread.

        Args:
            identifier_type: Le type brut (_CHANNEL_HANDLE, _CHANNEL_CUSTOM, _CHANNEL_USER).
            identifier: L'identifiant extrait de l'URL (handle, nom custom, nom utilisateur).

        Returns:
            L'ID de chaîne (UC...) ou None si non trouvé ou erreur.

        Raises:
            HttpError: Si une erreur API se produit (sera attrapée par l'appelant async).
        """
        log_prefix = f"Résolution {identifier_type} '{identifier}' (logique sync)"
        try:
            # Les Handles (@nom) et URLs Custom (/c/nom) sont résolus via l'API Search
            # C'est la méthode recommandée actuellement par Google.
            if identifier_type in [ContentType._CHANNEL_HANDLE, ContentType._CHANNEL_CUSTOM]:
                 logger.debug(f"{log_prefix}: Tentative de résolution via l'API Search...")
                 # Utiliser 'fields' pour minimiser la réponse et le coût quota
                 resp = self.youtube.search().list(
                     part="id", # Seul l'ID est nécessaire
                     q=identifier, # Rechercher l'identifiant
                     type="channel", # Chercher spécifiquement une chaîne
                     maxResults=1, # On ne veut que le résultat le plus pertinent
                     fields="items(id/channelId)" # Ne récupérer que l'ID de la chaîne
                 ).execute()
                 items = resp.get("items", [])
                 if items:
                     channel_id = items[0].get("id", {}).get("channelId")
                     logger.info(f"{log_prefix}: ID de Chaîne {channel_id} trouvé via l'API Search.")
                     return channel_id
                 else:
                     # L'API Search n'a pas trouvé de correspondance exacte
                     logger.warning(f"{log_prefix}: Non trouvé via l'API Search.")
                     return None

            # Les URLs User (/user/nom) sont résolues via channels().list(forUsername=...)
            elif identifier_type == ContentType._CHANNEL_USER:
                logger.debug(f"{log_prefix}: Tentative de résolution via l'API Channels (forUsername)...")
                resp = self.youtube.channels().list(
                    part="id", # Seul l'ID est nécessaire
                    forUsername=identifier,
                    fields="items(id)" # Ne récupérer que l'ID
                ).execute()
                items = resp.get("items", [])
                if items:
                    channel_id = items[0].get("id")
                    logger.info(f"{log_prefix}: ID de Chaîne {channel_id} trouvé via l'API Channels (forUsername).")
                    return channel_id
                else:
                    # L'API Channels n'a pas trouvé de correspondance pour cet username
                    logger.warning(f"{log_prefix}: Non trouvé via l'API Channels (forUsername).")
                    return None
            else:
                # Cas non prévu
                logger.error(f"Type d'identifiant non supporté pour la résolution: {identifier_type}")
                return None

        except HttpError as e:
            # Erreur API pendant la résolution synchrone
            uri = getattr(e, 'uri', 'URI Inconnu')
            logger.warning(f"{log_prefix}: Erreur API (sync) {e.resp.status}: {uri}")
            raise e # Remonter l'erreur pour être gérée par l'appelant async
        except Exception as e:
            # Erreur inattendue dans la logique synchrone
            logger.error(f"{log_prefix}: Erreur synchrone inattendue: {e}", exc_info=True)
            raise # Remonter

    async def _resolve_channel_identifier(self, identifier_type: str, identifier: str) -> Optional[str]:
        """
        Résout de manière asynchrone un handle, une URL personnalisée ou une URL utilisateur en ID de chaîne.
        Gère les erreurs API spécifiques à la résolution.

        Args:
            identifier_type: Le type brut (_CHANNEL_HANDLE, _CHANNEL_CUSTOM, _CHANNEL_USER).
            identifier: L'identifiant à résoudre.

        Returns:
            L'ID de chaîne (UC...) ou None si échec.

        Raises:
            QuotaExceededError: Si le quota est dépassé pendant la résolution.
            ValueError: Si une erreur de permission 403 se produit.
        """
        log_prefix = f"Résolution async {identifier_type} '{identifier}'"
        try:
            # Exécuter la logique synchrone (mise en cache) dans un thread séparé
            channel_id: Optional[str] = await asyncio.to_thread(
                self._resolve_channel_identifier_sync_logic,
                identifier_type,
                identifier
            )
            return channel_id
        except HttpError as e:
            # Gérer les erreurs HTTP spécifiques à la résolution
            if e.resp.status == 404:
                logger.warning(f"{log_prefix}: Identifiant non trouvé (404).")
                return None # L'identifiant n'existe pas
            elif e.resp.status == 403:
                 # Vérifier si c'est une erreur de quota ou une autre erreur 403
                 content_bytes = getattr(e, 'content', b'')
                 if b'quotaExceeded' in content_bytes or b'servingLimitExceeded' in content_bytes:
                     raise QuotaExceededError from e # Propager l'erreur de quota
                 else:
                     # Autre erreur 403 (permissions, clé invalide, etc.)
                     raise ValueError(f"Accès interdit (403) lors de la résolution de {identifier_type} '{identifier}'. Vérifiez la clé API.") from e
            else:
                # Autres erreurs HTTP non gérées spécifiquement
                logger.error(f"{log_prefix}: Erreur API non gérée {e.resp.status}: {e}")
                raise # Remonter l'erreur
        except QuotaExceededError:
            raise # Propager immédiatement si levée par la logique sync
        except Exception as e:
            # Gérer les erreurs inattendues pendant l'exécution asynchrone
            logger.error(f"{log_prefix}: Erreur asynchrone inattendue: {e}", exc_info=True)
            return None # Considérer comme un échec de résolution

    async def get_videos_from_source(self, source_type: str, source_id_or_query: str) -> Tuple[List[str], str]:
        """
        Récupère une liste d'IDs de vidéos potentiels basés sur le type de source
        (chaîne, playlist, vidéo unique, recherche).
        Effectue un filtrage initial (ex: par date pour les playlists).

        Args:
            source_type: Le type de contenu (ContentType.CHANNEL, etc.).
            source_id_or_query: L'ID de la ressource ou la requête de recherche.

        Returns:
            Un tuple contenant :
            - Une liste d'IDs de vidéos.
            - Un nom descriptif pour la source (ex: titre playlist, nom chaîne).

        Raises:
            QuotaExceededError: Si le quota est dépassé.
            ValueError: Si le type de source est invalide ou si une ressource n'est pas trouvée (ex: playlist 404).
            HttpError: Pour d'autres erreurs API non gérées.
        """
        logger.info(f"Récupération asynchrone des IDs vidéo pour {source_type}: {source_id_or_query[:100]}...")
        video_ids: List[str] = []
        source_name = f"{source_type.capitalize()}: {source_id_or_query[:50]}" # Nom par défaut

        try:
            if source_type == ContentType.CHANNEL:
                channel_id = source_id_or_query
                # Récupérer l'ID de la playlist "Uploads" et le nom de la chaîne
                uploads_playlist_id, source_name = await self._get_channel_uploads_playlist_id(channel_id)
                if not uploads_playlist_id:
                    raise ValueError(f"Impossible de trouver l'ID de la playlist 'uploads' pour l'ID de chaîne {channel_id}")
                logger.info(f"Récupération des vidéos de la playlist uploads '{uploads_playlist_id}' (Chaîne: '{source_name}')")
                # Utiliser l'itérateur asynchrone pour récupérer les IDs
                video_ids = [vid_id async for vid_id in self._yield_video_ids_from_playlist(uploads_playlist_id)]

            elif source_type == ContentType.PLAYLIST:
                playlist_id = source_id_or_query
                try:
                    # Essayer de récupérer le titre de la playlist pour un meilleur nom de source
                    req = self.youtube.playlists().list(part="snippet", id=playlist_id, fields="items(snippet/title)")
                    resp = await self._execute_api_call(req, cost=1)
                    # Mettre à jour source_name si le titre est trouvé
                    if resp.get('items'):
                        source_name = resp['items'][0].get('snippet', {}).get('title', source_name)
                except HttpError as e:
                    # Gérer spécifiquement le cas où la playlist n'existe pas
                    if e.resp.status == 404:
                        raise ValueError(f"Playlist non trouvée (ID: {playlist_id})") from e
                    else:
                        raise # Propager les autres erreurs API
                logger.info(f"Récupération des vidéos de la playlist '{source_name}' (ID: {playlist_id})")
                video_ids = [vid_id async for vid_id in self._yield_video_ids_from_playlist(playlist_id)]

            elif source_type == ContentType.VIDEO:
                video_id = source_id_or_query
                # Vérifier si la vidéo unique respecte les critères de base (date, durée, pas en live)
                is_valid, source_name = await self._check_single_video_validity(video_id)
                if is_valid:
                    video_ids = [video_id] # Liste contenant seulement cet ID
                else:
                    # La vidéo unique ne correspond pas, on retourne une liste vide
                    logger.info(f"La vidéo unique {video_id} ('{source_name}') ne correspond pas aux critères, ignorée.")
                    video_ids = []

            elif source_type == ContentType.SEARCH:
                # Récupérer les IDs via la fonction de recherche
                video_ids, source_name = await self._search_videos(source_id_or_query)

            else:
                # Gérer les types de source inconnus
                raise ValueError(f"Type de source non supporté : {source_type}")

            logger.info(f"{len(video_ids)} ID(s) vidéo potentiel(s) trouvé(s) pour la source '{source_name}'.")
            return video_ids, source_name

        except QuotaExceededError:
            raise # Propager immédiatement
        except (ValueError, HttpError) as e:
            # Erreurs attendues (ex: playlist non trouvée, type invalide)
            logger.error(f"Erreur lors de la récupération des vidéos pour la source {source_type} '{source_id_or_query}': {e}")
            raise # Remonter pour gestion dans le moteur principal
        except Exception as e:
            # Erreurs inattendues
            logger.error(f"Erreur inattendue lors de la récupération des vidéos: {e}", exc_info=True)
            raise # Remonter

    async def _get_channel_uploads_playlist_id(self, channel_id: str) -> Tuple[Optional[str], str]:
        """Récupère l'ID de la playlist 'uploads' et le titre de la chaîne pour un ID de chaîne donné."""
        default_name = f"Chaîne ID: {channel_id}" # Nom par défaut si le titre n'est pas trouvé
        try:
            req = self.youtube.channels().list(
                part="snippet,contentDetails", # Besoin du snippet pour le titre, contentDetails pour la playlist uploads
                id=channel_id,
                fields="items(snippet/title,contentDetails/relatedPlaylists/uploads)" # Minimiser les champs
            )
            resp = await self._execute_api_call(req, cost=1) # Coût faible
            if not resp.get('items'):
                logger.warning(f"Chaîne non trouvée (ID: {channel_id}) lors de la récupération de la playlist uploads.")
                return None, default_name
            # Extraire les informations de la réponse
            item = resp['items'][0]
            channel_name = item.get('snippet', {}).get('title', default_name)
            playlist_id = item.get('contentDetails', {}).get('relatedPlaylists', {}).get('uploads')
            if not playlist_id:
                 # Certaines chaînes peuvent ne pas avoir de playlist uploads visible
                 logger.warning(f"Impossible de trouver l'ID de la playlist uploads pour la chaîne '{channel_name}' ({channel_id}).")
            return playlist_id, channel_name
        except HttpError as e:
            # Gérer spécifiquement l'erreur 404 (chaîne non trouvée)
            if e.resp.status == 404:
                logger.warning(f"Chaîne non trouvée (404) pour ID: {channel_id}")
                return None, default_name
            else:
                raise # Propager les autres erreurs API
        except Exception as e:
            # Gérer les erreurs inattendues
            logger.error(f"Erreur lors de la récupération de l'ID de la playlist uploads pour {channel_id}: {e}", exc_info=True)
            return None, default_name # Retourner None en cas d'erreur

    async def _check_single_video_validity(self, video_id: str) -> Tuple[bool, str]:
        """Vérifie si une vidéo unique respecte les critères de date, durée et statut live."""
        default_name = f"Vidéo ID: {video_id}" # Nom par défaut
        try:
            # Demander les champs nécessaires pour la validation
            fields = "items(id,snippet(title,publishedAt,liveBroadcastContent),contentDetails/duration)"
            req = self.youtube.videos().list(part="snippet,contentDetails", id=video_id, fields=fields)
            resp = await self._execute_api_call(req, cost=1) # Coût faible pour une seule vidéo

            if not resp.get('items'):
                logger.warning(f"Vidéo non trouvée (ID: {video_id}) lors de la vérification de validité.")
                return False, default_name
            # Extraire les données de la réponse
            item = resp['items'][0]
            video_name = item.get('snippet', {}).get('title', default_name)
            duration_iso = item.get('contentDetails', {}).get('duration')
            live_status = item.get('snippet', {}).get('liveBroadcastContent', 'none') # 'none', 'live', 'upcoming', 'completed'
            published_at_str = item.get('snippet', {}).get('publishedAt')

            # Vérifier la date de publication
            date_ok = False
            if published_at_str:
                try:
                    ts = published_at_str
                    if not ts.endswith('Z'): ts += 'Z' # Assurer format UTC
                    pub_dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    date_ok = pub_dt >= config.LIMIT_DATE # Comparer à la date limite configurée
                except (ValueError, TypeError):
                    logger.warning(f"Format de date invalide '{published_at_str}' pour la vidéo {video_id}.")
                    date_ok = False # Considérer comme invalide si la date ne peut être parsée

            # Vérifier la durée et le statut live en utilisant l'helper
            duration_live_ok = self._is_valid_video(duration_iso, live_status)

            # La vidéo est valide si la date ET la durée/statut sont OK
            return date_ok and duration_live_ok, video_name

        except HttpError as e:
            # Gérer l'erreur 404 (vidéo non trouvée)
            if e.resp.status == 404:
                logger.warning(f"Vidéo non trouvée (404) pour ID: {video_id}")
                return False, default_name
            else:
                raise # Propager les autres erreurs API
        except Exception as e:
            # Gérer les erreurs inattendues
            logger.error(f"Erreur lors de la vérification de validité de la vidéo {video_id}: {e}", exc_info=True)
            return False, default_name # Considérer comme invalide en cas d'erreur

    async def _search_videos(self, query: str, max_results: Optional[int] = None) -> Tuple[List[str], str]:
        """Effectue une recherche YouTube et récupère les IDs des vidéos, gérant la pagination et les filtres."""
        logger.info(f"Exécution de la recherche asynchrone pour la requête : '{query}'")
        max_r = max_results if max_results is not None else config.MAX_SEARCH_RESULTS
        # Si max_results est 0 ou négatif, retourner immédiatement
        if max_r <= 0: return [], f"Recherche: {query} (0 résultats demandés)"

        # Analyser la requête pour séparer les mots-clés des filtres API
        parsed_query, api_params = self._parse_search_query(query)
        video_ids: List[str] = []
        next_page_token: Optional[str] = None
        retrieved_count = 0
        # Construire un nom de source descriptif incluant les filtres
        filter_desc = f" ({len(api_params)} filtre(s))" if api_params else ""
        source_name = f"Recherche '{parsed_query}'{filter_desc}"

        # Boucler tant qu'il y a des pages et que la limite n'est pas atteinte
        while retrieved_count < max_r:
            try:
                # Calculer combien de résultats demander pour ce lot
                batch_size = min(config.BATCH_SIZE, max_r - retrieved_count)
                # Si batch_size est 0 ou moins, on a atteint la limite
                if batch_size <= 0: break

                # Préparer les paramètres pour l'appel search.list
                params = {
                    "q": parsed_query, # Mots-clés principaux
                    "part": "id", # On ne veut que l'ID de la vidéo
                    "type": "video", # Chercher uniquement des vidéos
                    "maxResults": batch_size,
                    "pageToken": next_page_token, # Pour la pagination
                    **api_params # Ajouter les filtres parsés (ex: publishedAfter)
                }
                # Minimiser les champs retournés pour économiser quota/bande passante
                params["fields"] = "items(id/videoId),nextPageToken"
                logger.debug(f"Préparation de l'appel API Search avec params: {params}")

                req = self.youtube.search().list(**params)
                # L'API Search a un coût quota élevé (100 unités)
                resp = await self._execute_api_call(req, cost=100)

                # Extraire les IDs de vidéos de la réponse
                items = resp.get('items', [])
                new_ids = [item['id']['videoId'] for item in items if item.get('id', {}).get('videoId')]
                video_ids.extend(new_ids)
                retrieved_count += len(new_ids)
                logger.debug(f"Lot de recherche a retourné {len(new_ids)} IDs. Total récupéré: {retrieved_count}/{max_r}.")

                # Récupérer le token pour la page suivante
                next_page_token = resp.get('nextPageToken')
                if not next_page_token:
                    logger.debug("Plus de pages dans les résultats de recherche.")
                    break # Sortir de la boucle while
            except HttpError as e:
                 # Gérer spécifiquement l'erreur "invalid search filter"
                 content_bytes = getattr(e, 'content', b'')
                 if e.resp.status == 400 and b'invalid search filter' in content_bytes:
                     logger.error(f"Erreur de recherche (400 Bad Request - Filtre invalide?): Requête='{query}', Params={api_params}")
                     # Lever une erreur plus descriptive
                     raise ValueError(f"Filtre de recherche invalide fourni pour la requête '{query}'.") from e
                 else:
                     raise # Propager les autres erreurs API
            except QuotaExceededError:
                raise # Propager immédiatement
            except Exception as e:
                # Gérer les erreurs inattendues pendant la recherche
                logger.error(f"Erreur inattendue lors de la recherche pour '{query}': {e}", exc_info=True)
                break # Arrêter la recherche en cas d'erreur inattendue

        logger.info(f"Recherche pour '{query}' terminée. Trouvé {len(video_ids)} IDs vidéo.")
        return video_ids, source_name

    def _parse_search_query(self, query: str) -> Tuple[str, Dict[str, Any]]:
        """
        Analyse une chaîne de requête de recherche pour séparer les mots-clés
        des opérateurs de filtre de l'API (ex: before:, after:, channel:, etc.).

        Args:
            query: La chaîne de requête brute entrée par l'utilisateur.

        Returns:
            Un tuple contenant :
            - La chaîne de requête nettoyée ('q' pour l'API).
            - Un dictionnaire des paramètres API dérivés des opérateurs.
        """
        logger.debug(f"Analyse de la requête de recherche : {query}")
        api_params: Dict[str, Any] = {}
        # Mapping des préfixes opérateurs vers les noms de paramètres API et validateurs/formateurs optionnels
        op_map: Dict[str, Optional[Tuple[str, Optional[Callable[[str], Optional[Any]]]]]] = {
            'intitle:': None, 'description:': None, # Ceux-ci sont ajoutés au paramètre 'q'
            'before:': ('publishedBefore', self._format_date_for_api), # Date avant YYYY-MM-DD
            'after:': ('publishedAfter', self._format_date_for_api),   # Date après YYYY-MM-DD
            'channel:': ('channelId', None), # Attend un ID de chaîne (UC...)
            'duration:': ('videoDuration', lambda x: x.lower() if x.lower() in ['short', 'medium', 'long', 'any'] else None),
            'definition:': ('videoDefinition', lambda x: x.lower() if x.lower() in ['high', 'standard', 'any'] else None),
            'license:': ('videoLicense', lambda x: {'creativecommon':'creativeCommon'}.get(x.lower(), x.lower() if x.lower() in ['youtube', 'any'] else 'any')),
            'dimension:': ('videoDimension', lambda x: x.lower() if x.lower() in ['2d', '3d', 'any'] else None),
            'caption:': ('videoCaption', lambda x: {'caption':'closedCaption','nocaption':'none'}.get(x.lower(), 'any')), # 'closedCaption' ou 'none'
            'embeddable:': ('videoEmbeddable', lambda x: {'true':'true','false':'false'}.get(x.lower(), 'any')), # 'true' ou 'false'
            'syndicated:': ('videoSyndicated', lambda x: {'true':'true','false':'false'}.get(x.lower(), 'any')), # 'true' ou 'false'
            'order:': ('order', lambda x: x.lower() if x.lower() in ['date', 'rating', 'relevance', 'title', 'videoCount', 'viewCount'] else None) # Ordre de tri
        }

        # Dictionnaire pour stocker les valeurs trouvées pour chaque opérateur
        found_operators: Dict[str, List[str]] = {op: [] for op in op_map}
        # Liste pour stocker les parties de la requête qui ne sont pas des opérateurs/valeurs
        remaining_query_parts: List[str] = []
        # Regex pour capturer : "phrases entre guillemets", op:"valeur entre guillemets", op:valeursimple, mot_simple
        pattern = re.compile(r'"([^"]+)"|(\w+):"([^"]+)"|(\w+):(\S+)|(\S+)')

        # Itérer sur toutes les correspondances dans la requête
        for match in pattern.finditer(query):
            groups = match.groups()
            if groups[0] is not None: # "phrase entre guillemets"
                remaining_query_parts.append(f'"{groups[0]}"')
            elif groups[1] is not None: # op:"valeur entre guillemets" (groups[1]=op, groups[2]=val)
                op_key = groups[1].lower() + ':' # Construire la clé opérateur (ex: 'before:')
                if op_key in op_map: found_operators[op_key].append(groups[2]) # Stocker la valeur si l'opérateur est connu
                else: remaining_query_parts.append(match.group(0)) # Sinon, traiter comme un terme normal
            elif groups[3] is not None: # op:valeursimple (groups[3]=op, groups[4]=val)
                op_key = groups[3].lower() + ':'
                if op_key in op_map: found_operators[op_key].append(groups[4])
                else: remaining_query_parts.append(match.group(0))
            elif groups[5] is not None: # mot_simple
                 # Vérifier si le mot ressemble à un opérateur sans valeur (ex: "before" seul)
                 if (groups[5].lower() + ':') in op_map:
                     logger.warning(f"Opérateur '{groups[5]}:' trouvé sans valeur associée. Ignoré.")
                 else:
                     # C'est un terme de recherche normal
                     remaining_query_parts.append(groups[5])

        # Traiter les opérateurs trouvés
        q_final_terms = remaining_query_parts[:] # Commencer avec les termes non-opérateurs
        for op, values in found_operators.items():
            if not values: continue # Ignorer si aucune valeur n'a été trouvée pour cet opérateur
            value = values[-1] # Utiliser la dernière valeur spécifiée pour un opérateur donné

            if op in ['intitle:', 'description:']:
                 # Ajouter ces opérateurs directement à la chaîne de requête 'q'
                 q_final_terms.append(f'{op}{value}')
                 logger.debug(f"Ajout du terme '{op}{value}' à la requête 'q'")
            elif op in op_map and op_map[op]:
                 # Cet opérateur correspond à un paramètre API
                 api_param_key, formatter = op_map[op]
                 # Formater/valider la valeur si nécessaire
                 formatted_value = formatter(value) if formatter else value
                 if formatted_value is not None:
                     # Ajouter au dictionnaire des paramètres API
                     api_params[api_param_key] = formatted_value
                     logger.debug(f"Définition du paramètre API : {api_param_key} = {formatted_value}")
                 else:
                     # La valeur n'est pas valide pour cet opérateur
                     logger.warning(f"Valeur '{value}' invalide pour l'opérateur '{op}'. Paramètre API '{api_param_key}' ignoré.")

        # Construire la chaîne de requête 'q' finale
        final_q = " ".join(q_final_terms).strip()
        logger.debug(f"Requête 'q' finale pour l'API : '{final_q}'")
        logger.debug(f"Paramètres API finaux : {api_params}")
        return final_q, api_params

    @functools.lru_cache(maxsize=128)
    def _format_date_for_api(self, date_str: str) -> Optional[str]:
        """Formate une chaîne YYYY-MM-DD ou YYYYMMDD au format RFC 3339 pour l'API."""
        try:
            # Accepter les deux formats courants
            dt = datetime.strptime(date_str.replace('-', ''), "%Y%m%d")
            # Retourner au format UTC au début de la journée
            return dt.replace(tzinfo=timezone.utc).strftime("%Y-%m-%dT00:00:00Z")
        except (ValueError, TypeError):
            logger.warning(f"Format de date invalide pour le filtre API : '{date_str}'. Attendu YYYY-MM-DD.")
            return None # Retourner None si le format est invalide

    async def _fetch_playlist_page(self, playlist_id: str, page_token: Optional[str]) -> Dict[str, Any]:
        """Récupère une seule page d'éléments de playlist, en utilisant un cache manuel."""
        cache_key = (playlist_id, page_token)
        # Vérifier le cache avant l'appel API
        async with self._playlist_item_cache_lock:
            if cache_key in self._playlist_item_cache:
                logger.spam(f"Cache HIT pour playlist {playlist_id} page {page_token}")
                return self._playlist_item_cache[cache_key]

        logger.debug(f"Cache MISS pour playlist {playlist_id} page {page_token}. Appel API...")
        req = self.youtube.playlistItems().list(
            part="snippet", # snippet contient publishedAt et resourceId.videoId
            playlistId=playlist_id,
            maxResults=config.BATCH_SIZE,
            pageToken=page_token,
            fields="items(snippet(publishedAt,resourceId/videoId)),nextPageToken" # Champs minimaux
        )
        try:
            resp = await self._execute_api_call(req, cost=1) # Coût faible
            # Mettre en cache le résultat après l'appel réussi
            async with self._playlist_item_cache_lock:
                 # Éviction FIFO simple si le cache est plein
                 if len(self._playlist_item_cache) >= config.PLAYLIST_ITEM_CACHE_SIZE:
                     try:
                         # Retirer l'élément le plus ancien (premier inséré)
                         self._playlist_item_cache.pop(next(iter(self._playlist_item_cache)))
                     except StopIteration: pass # Le cache était vide
                 self._playlist_item_cache[cache_key] = resp
                 logger.spam(f"Page mise en cache pour playlist {playlist_id} page {page_token}")
            return resp
        except HttpError as e:
            # Gérer l'erreur 404 (playlist non trouvée)
            if e.resp.status == 404:
                 logger.warning(f"Playlist {playlist_id} non trouvée (404) lors de la récupération de la page {page_token}.")
                 # Lever une erreur spécifique pour être gérée par l'appelant
                 raise ValueError(f"Playlist {playlist_id} non trouvée") from e
            else:
                raise # Propager les autres erreurs API
        except QuotaExceededError:
            raise # Propager immédiatement

    async def _yield_video_ids_from_playlist(self, playlist_id: str) -> AsyncIterator[str]:
        """
        Itérateur asynchrone qui produit les IDs de vidéos d'une playlist,
        en filtrant par date de publication.
        """
        logger.info(f"Récupération asynchrone des IDs vidéo de la playlist : {playlist_id}")
        next_page_token: Optional[str] = None
        processed_item_count, yielded_count = 0, 0
        limit_dt = config.LIMIT_DATE # Date limite configurée
        has_more_pages = True

        # Boucler tant qu'il y a des pages à récupérer
        while has_more_pages:
            try:
                page_token_log = '(première page)' if next_page_token is None else f"{next_page_token[:10]}..."
                logger.debug(f"Récupération du lot playlist {playlist_id}, page token: {page_token_log}")
                # Récupérer la page (potentiellement depuis le cache)
                resp = await self._fetch_playlist_page(playlist_id, next_page_token)
                items = resp.get('items', [])
                if not items:
                    logger.debug(f"Aucun élément retourné sur cette page pour la playlist {playlist_id}.")
                    break # Fin de la playlist

                ids_in_page: List[str] = []
                # Drapeau pour arrêter la pagination tôt si on ne trouve que des vidéos trop anciennes
                # (Suppose un tri chronologique inverse dans la réponse API, courant pour les uploads)
                stop_pagination_early = False

                # Traiter chaque élément de la page
                for item in items:
                    processed_item_count += 1
                    snippet = item.get('snippet', {})
                    video_id = snippet.get('resourceId', {}).get('videoId')
                    published_at_str = snippet.get('publishedAt')

                    # Vérifier si les données essentielles sont présentes
                    if not video_id or not published_at_str:
                        logger.warning(f"Élément incomplet dans la playlist {playlist_id}: {item}")
                        continue # Ignorer cet élément

                    try:
                        # Analyser la date de publication
                        ts = published_at_str
                        if not ts.endswith('Z'): ts += 'Z' # Assurer UTC
                        published_at_dt = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

                        # Vérifier si la vidéo est assez récente
                        if published_at_dt >= limit_dt:
                            ids_in_page.append(video_id)
                        else:
                            # Vidéo trop ancienne
                            logger.log(SPAM_LEVEL_NUM, f"Vidéo {video_id} de la playlist {playlist_id} est trop ancienne ({published_at_dt}).")
                            # Si cette page ne contient QUE des vidéos trop anciennes, on peut probablement arrêter
                            if not ids_in_page:
                                stop_pagination_early = True

                    except (ValueError, TypeError):
                        # Gérer les dates invalides
                        logger.warning(f"Format de date invalide '{published_at_str}' pour vidéo {video_id} dans playlist {playlist_id}.")
                        # Traiter les vidéos avec date invalide comme ne respectant pas les critères

                # Produire (yield) les IDs valides trouvés sur cette page
                for vid_id in ids_in_page:
                    yield vid_id
                    yielded_count += 1

                # Passer à la page suivante
                next_page_token = resp.get('nextPageToken')
                # Arrêter s'il n'y a plus de page ou si on a décidé d'arrêter tôt
                if not next_page_token or stop_pagination_early:
                    log_msg = "Pagination de la playlist terminée"
                    if stop_pagination_early and next_page_token:
                        log_msg += " (arrêt anticipé car vidéos trop anciennes)"
                    logger.info(f"{log_msg} pour {playlist_id}.")
                    has_more_pages = False

            except QuotaExceededError:
                raise # Propager immédiatement
            except ValueError as e: # Erreur spécifique (ex: playlist non trouvée)
                 logger.error(f"Erreur lors de la récupération de la playlist {playlist_id}: {e}")
                 raise # Arrêter le traitement pour cette source
            except Exception as e:
                # Gérer les erreurs inattendues pendant la pagination
                page_token_log = '(première page)' if next_page_token is None else f"{next_page_token[:10]}..."
                logger.error(f"Erreur inattendue playlist {playlist_id} page {page_token_log}: {e}", exc_info=True)
                raise # Arrêter le traitement pour cette source

        logger.info(f"Playlist {playlist_id}: {processed_item_count} éléments traités, {yielded_count} IDs potentiels produits après filtre date.")

    def _is_valid_video(self, duration_iso: Optional[str], live_status: Optional[str]) -> bool:
        """Vérifie si une vidéo respecte les critères de durée et de statut live."""
        # Accepter 'none' (VOD), 'completed' (live terminé). Exclure 'live', 'upcoming'.
        # Accepter aussi None comme statut (probablement VOD).
        if live_status not in ('none', 'completed', None):
            logger.log(SPAM_LEVEL_NUM, f"Vidéo filtrée (statut live non 'none' ou 'completed'): {live_status}")
            return False

        # Vérifier la durée
        if not duration_iso:
            logger.log(SPAM_LEVEL_NUM, "Vidéo filtrée (durée manquante)")
            return False
        try:
            duration: timedelta = isodate.parse_duration(duration_iso)
            # Vérifier si la durée est supérieure ou égale à la durée minimale configurée
            is_long_enough = duration >= config.MIN_DURATION
            if not is_long_enough:
                 logger.log(SPAM_LEVEL_NUM, f"Vidéo filtrée (durée {duration} < {config.MIN_DURATION})")
            return is_long_enough
        except (isodate.ISO8601Error, TypeError):
             # Gérer les formats de durée invalides
             logger.warning(f"Format de durée invalide '{duration_iso}', vidéo filtrée.")
             return False

    async def get_video_details_batch(self, video_ids: List[str]) -> List[Video]:
        """
        Récupère les informations détaillées pour une liste d'IDs de vidéos par lots.
        Filtre les vidéos basées sur la durée et le statut live après récupération.

        Args:
            video_ids: Une liste d'IDs de vidéos à traiter.

        Returns:
            Une liste d'objets Video valides avec leurs détails.
        """
        if not video_ids: return []
        # Assurer l'unicité tout en préservant l'ordre si possible (important si l'ordre source compte)
        unique_ids = list(dict.fromkeys(video_ids))
        logger.info(f"Récupération/filtrage asynchrone des détails pour {len(unique_ids)} ID(s) vidéo unique(s)...")

        valid_videos_with_details: List[Video] = []
        tasks: List[asyncio.Task] = [] # Liste pour stocker les tâches de récupération de lots

        # Créer les tâches pour récupérer les lots en parallèle
        for i in range(0, len(unique_ids), config.BATCH_SIZE):
            batch_ids = unique_ids[i : i + config.BATCH_SIZE]
            # Créer une tâche pour chaque lot
            tasks.append(asyncio.create_task(self._fetch_video_details_batch(batch_ids)))

        # Exécuter les tâches de récupération de lots de manière concurrente
        # return_exceptions=True permet de récupérer les résultats ou les exceptions
        batch_results: List[Union[List[Dict[str, Any]], Exception]] = await asyncio.gather(*tasks, return_exceptions=True)

        processed_ids: Set[str] = set() # Suivre les IDs traités pour éviter doublons
        # Traiter les résultats de chaque lot
        for i, result in enumerate(batch_results):
            batch_num = i + 1
            if isinstance(result, QuotaExceededError):
                # Si un lot échoue à cause du quota, arrêter tout
                logger.critical(f"Quota dépassé lors de la récupération du lot de détails {batch_num}.")
                raise result # Propager immédiatement
            elif isinstance(result, Exception):
                # Logger l'erreur pour ce lot mais continuer avec les autres lots réussis
                logger.error(f"Erreur lors de la récupération du lot de détails {batch_num}: {result}", exc_info=isinstance(result, HttpError))
            elif isinstance(result, list):
                # Le lot a été récupéré avec succès
                logger.debug(f"Lot de détails {batch_num}: Reçu {len(result)} éléments vidéo bruts.")
                # Traiter chaque vidéo dans le lot
                for item in result:
                    video_id = item.get('id')
                    # Ignorer si pas d'ID ou déjà traité (sécurité)
                    if not video_id or video_id in processed_ids: continue

                    # Effectuer la validation finale basée sur les détails récupérés
                    duration_iso = item.get('contentDetails', {}).get('duration')
                    live_status = item.get('snippet', {}).get('liveBroadcastContent', 'none')

                    if self._is_valid_video(duration_iso, live_status):
                        # La vidéo est valide, créer l'objet Video et l'ajouter
                        video_obj = Video.from_api_response(item)
                        valid_videos_with_details.append(video_obj)
                        processed_ids.add(video_id)
                        logger.log(SPAM_LEVEL_NUM, f"Vidéo {video_id} validée après récupération des détails.")
                    else:
                        # La vidéo n'est pas valide selon les critères finaux
                        logger.log(SPAM_LEVEL_NUM, f"Vidéo {video_id} filtrée après récupération des détails (durée/statut live).")
            else:
                 # Cas inattendu où le résultat n'est ni une liste ni une exception
                 logger.error(f"Type de résultat inattendu pour le lot de détails {batch_num}: {type(result)}")

        logger.info(f"Récupération/filtrage des détails terminé. {len(valid_videos_with_details)} vidéos valides retenues sur {len(unique_ids)} IDs uniques.")
        return valid_videos_with_details

    async def _fetch_video_details_batch(self, batch_ids: List[str]) -> List[Dict[str, Any]]:
        """Récupère les détails pour un seul lot d'IDs de vidéos."""
        if not batch_ids: return []
        ids_string = ",".join(batch_ids)
        logger.debug(f"Appel API videos.list asynchrone pour lot de détails ({len(batch_ids)} IDs)")
        try:
            # Demander les champs nécessaires pour créer l'objet Video et pour la validation
            fields="items(id,snippet(title,description,channelId,channelTitle,publishedAt,defaultLanguage,defaultAudioLanguage,tags,liveBroadcastContent),contentDetails/duration)"
            req = self.youtube.videos().list(
                part="snippet,contentDetails",
                id=ids_string,
                fields=fields,
                maxResults=len(batch_ids) # Indiquer le nombre max attendu
            )
            # videos.list a un coût modéré (environ 5 unités ?)
            resp = await self._execute_api_call(req, cost=5)
            # Retourner la liste des éléments vidéo
            return resp.get("items", [])
        except QuotaExceededError:
            logger.critical(f"Quota dépassé pendant la récupération des détails du lot ({len(batch_ids)} IDs)")
            raise
        except HttpError as e:
            # Gérer les erreurs HTTP pendant la récupération du lot
            logger.error(f"HttpError lors de la récupération du lot de détails ({len(batch_ids)} IDs): {e.resp.status} - {getattr(e, 'uri', 'URI Inconnu')}")
            raise e # Propager pour gestion potentielle en amont
        except Exception as e:
            # Gérer les erreurs inattendues
            logger.error(f"Erreur inattendue lors de la récupération du lot de détails ({len(batch_ids)} IDs): {e}", exc_info=True)
            raise # Propager

# ==============================================================================
# SECTION 6 : Gestionnaire de Transcriptions
# ==============================================================================

class TranscriptManager:
    """Gère la récupération, le traitement et la mise en cache des transcriptions vidéo."""
    # Cache pour les transcriptions finales traitées {video_id: Optional[{"language": lang, "transcript": text}]}
    # Contient aussi les résultats négatifs (None) pour éviter de réessayer inutilement
    _final_transcript_cache: Dict[str, Optional[Dict[str, str]]] = {}
    _final_transcript_cache_lock: asyncio.Lock = asyncio.Lock() # Verrou pour ce cache

    # Suivi des erreurs persistantes par ID vidéo pour éviter les tentatives répétées
    _transcript_fetch_errors: Dict[str, Exception] = {}

    # Sémaphore pour limiter le nombre de requêtes concurrentes à l'API de transcription
    _semaphore: asyncio.Semaphore = asyncio.Semaphore(config.TRANSCRIPT_SEMAPHORE_LIMIT)

    @staticmethod
    @functools.lru_cache(maxsize=2048) # Cache pour les lignes de transcription fréquemment nettoyées
    def _clean_transcript_line(text: str) -> str:
        """Nettoie une seule ligne de texte de transcription."""
        if not text: return ""
        try:
            # Remplacer les sauts de ligne internes par des espaces
            cleaned = text.replace('\n', ' ').replace('\r', ' ')
            # Supprimer les emojis
            cleaned = emoji.replace_emoji(cleaned, replace='')
            # Supprimer les caractères de contrôle sauf tabulation (sauts de ligne déjà gérés) et certains caractères invisibles/zéro-largeur
            cleaned = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\u200B-\u200D\uFEFF]', '', cleaned)
            # Supprimer les caractères Markdown/spéciaux courants
            cleaned = re.sub(r'[\`*_{}\[\]<>|]', '', cleaned)
            # Normaliser les espaces multiples en un seul espace
            return re.sub(r'\s+', ' ', cleaned).strip()
        except Exception:
            # En cas d'erreur (peu probable), retourner le texte original
            logger.warning(f"Erreur lors du nettoyage de la ligne de transcription : '{text[:50]}...'", exc_info=False)
            return text

    def _format_transcript_by_blocks_sync(self, transcript_data: List[Dict[str, Any]], lang_code: str, video_id: str, origin_log: str) -> Optional[str]:
        """
        Formate les données brutes de transcription (liste de dicts avec 'start', 'text')
        en blocs horodatés. S'exécute de manière synchrone.

        Args:
            transcript_data: Liste de dictionnaires [{'start': float, 'text': str, 'duration': float}, ...].
            lang_code: Le code langue de la transcription.
            video_id: L'ID de la vidéo pour la journalisation.
            origin_log: Chaîne décrivant l'origine (ex: 'MANUELLE préférée') pour les logs.

        Returns:
            La transcription formatée en chaîne de caractères, ou None si échec.
        """
        if not transcript_data:
            logger.warning(f"Données de transcription brutes vides fournies (formatage sync) depuis {origin_log} pour {video_id} ({lang_code})")
            return None

        # Durée de chaque bloc de transcription en secondes
        block_duration = float(config.TRANSCRIPT_BLOCK_DURATION_SECONDS)
        if block_duration <= 0:
            logger.error(f"Durée de bloc de transcription invalide configurée ({block_duration}s). Formatage impossible.")
            return None

        # Regrouper les segments de texte nettoyés par index de bloc temporel
        blocks: Dict[int, List[str]] = {}
        max_block_index = -1 # Suivre le dernier bloc ayant du contenu
        valid_segments_found = False # Drapeau pour vérifier si au moins un segment est valide

        for entry in transcript_data:
            segment_start_time = entry.get('start')
            segment_text = entry.get('text')

            # Valider les types des données du segment
            if not isinstance(segment_start_time, (int, float)) or not isinstance(segment_text, str):
                logger.log(SPAM_LEVEL_NUM, f"Segment ignoré (formatage sync) à cause de types invalides : start={type(segment_start_time)}, text={type(segment_text)}")
                continue

            # Nettoyer le texte du segment
            cleaned_segment_text = self._clean_transcript_line(segment_text)
            # Ignorer si le nettoyage résulte en une chaîne vide
            if not cleaned_segment_text:
                 logger.log(SPAM_LEVEL_NUM, f"Segment ignoré après nettoyage (formatage sync) (original='{segment_text}')")
                 continue

            valid_segments_found = True # Marquer qu'on a trouvé au moins un segment valide
            # Calculer l'index du bloc basé sur le temps de début
            block_index = int(segment_start_time // block_duration)
            # Ajouter le texte nettoyé au bloc correspondant
            if block_index not in blocks: blocks[block_index] = []
            blocks[block_index].append(cleaned_segment_text)
            # Mettre à jour l'index du dernier bloc
            max_block_index = max(max_block_index, block_index)

        # Si aucun segment valide n'a été trouvé après nettoyage
        if not valid_segments_found:
            logger.warning(f"Aucun segment de transcription valide trouvé après nettoyage (formatage sync) depuis {origin_log} pour {video_id} ({lang_code})")
            return None

        # Assembler la chaîne de caractères finale formatée
        formatted_lines: List[str] = []
        # Itérer sur tous les blocs possibles jusqu'au dernier trouvé pour conserver la chronologie
        # et représenter implicitement les silences (blocs sans texte)
        for current_index in range(max_block_index + 1):
            block_start_seconds = float(current_index * block_duration)
            timestamp_str = _format_timestamp(block_start_seconds) # Formater le timestamp du début de bloc
            # Si le bloc contient du texte
            if current_index in blocks:
                # Joindre tous les segments de texte du bloc avec un espace
                full_block_text = " ".join(blocks[current_index])
                formatted_lines.append(f"[{timestamp_str}] {full_block_text}")
            # Optionnel : Ajouter une ligne vide ou un marqueur pour les blocs sans texte
            # else:
            #    formatted_lines.append(f"[{timestamp_str}]") # Ligne avec juste le timestamp

        # Vérifier si le formatage a produit des lignes (ne devrait pas arriver si valid_segments_found est True)
        if not formatted_lines:
            logger.warning(f"Transcription formatée est vide (formatage sync) malgré segments valides depuis {origin_log} pour {video_id} ({lang_code})")
            return None

        # Joindre toutes les lignes formatées avec un saut de ligne
        full_transcript = "\n".join(formatted_lines)
        logger.debug(f"Transcription {origin_log} formatée OK (blocs sync {block_duration}s) pour {video_id} ({lang_code}), {len(formatted_lines)} blocs générés.")
        return full_transcript

    @functools.lru_cache(maxsize=config.TRANSCRIPT_CACHE_SIZE)
    def _list_transcripts_sync(self, video_id: str) -> Tuple[List[Transcript], Optional[Exception]]:
        """
        Liste de manière synchrone les transcriptions disponibles pour un ID vidéo.
        Utilise un cache LRU.

        Args:
            video_id: L'ID de la vidéo.

        Returns:
            Un tuple contenant :
            - Une liste d'objets Transcript disponibles.
            - Une Exception si une erreur s'est produite (y compris non-disponibilité), ou None si succès.
        """
        logger.debug(f"Appel synchrone list_transcripts pour {video_id}")
        try:
            # YouTubeTranscriptApi.list_transcripts retourne un générateur, le convertir en liste pour le cache
            transcript_list = list(YouTubeTranscriptApi.list_transcripts(video_id))
            return transcript_list, None # Succès
        except (TranscriptsDisabled, NoTranscriptFound) + YouTubeTranscriptApiErrors.TRANSCRIPT_FETCH_ERRORS as e:
            # Erreurs attendues indiquant la non-disponibilité
            logger.warning(f"{e.__class__.__name__} rencontrée pour {video_id} (liste sync).")
            return [], e # Retourner liste vide et l'exception spécifique
        except Exception as e:
            # Erreurs inattendues lors du listage
            logger.error(f"Erreur inattendue list_transcripts {video_id} (sync): {e}", exc_info=True)
            return [], e # Retourner liste vide et l'exception générique

    def _fetch_transcript_sync(self, transcript: Transcript) -> Tuple[Optional[List[Dict[str, Any]]], Optional[Exception]]:
        """
        Récupère de manière synchrone le contenu d'un objet Transcript spécifique.

        Args:
            transcript: L'objet Transcript à récupérer.

        Returns:
            Un tuple contenant :
            - Les données brutes sous forme de liste de dictionnaires, ou None si échec.
            - Une Exception si une erreur s'est produite, ou None si succès.
        """
        video_id = transcript.video_id
        lang_code = transcript.language_code
        logger.debug(f"Appel synchrone fetch_transcript pour {video_id} ({lang_code})")
        try:
            # transcript.fetch() retourne un itérable d'objets FetchedTranscriptSnippet
            fetched_snippets = transcript.fetch()

            # Convertir les snippets en une liste de dictionnaires standardisés
            transcript_data_list: List[Dict[str, Any]] = []
            for snippet in fetched_snippets:
                # Utiliser getattr pour accéder aux attributs de manière sûre
                start_time = getattr(snippet, 'start', None)
                duration = getattr(snippet, 'duration', None) # La durée peut être None
                text_content = getattr(snippet, 'text', None)

                # Validation basique des types des champs essentiels
                if isinstance(start_time, (int, float)) and isinstance(text_content, str):
                    transcript_data_list.append({
                        'start': start_time,
                        'duration': duration, # Conserver même si None
                        'text': text_content
                    })
                else:
                    # Logguer les snippets mal formés
                    logger.warning(f"Snippet de transcription mal formé ignoré pour {video_id} ({lang_code}): start={start_time}, text={text_content}")

            # Vérifier si des snippets valides ont été trouvés
            if not transcript_data_list:
                 logger.warning(f"La récupération n'a retourné aucun snippet valide pour {video_id} ({lang_code})")
                 # Retourner une liste vide, le formateur gérera ce cas
                 return [], None

            # Succès, retourner la liste des données
            return transcript_data_list, None

        except CouldNotRetrieveTranscript as e:
             # Erreur spécifique de l'API lors de la récupération
             logger.error(f"Impossible de récupérer le contenu de la transcription {video_id} ({lang_code}) (sync): {e}", exc_info=False)
             return None, e # Retourner None pour les données et l'exception
        except Exception as e:
             # Erreurs inattendues pendant la récupération
             logger.error(f"Erreur inattendue fetch transcript {video_id} ({lang_code}) (sync): {e}", exc_info=True)
             return None, e # Retourner None et l'exception

    def _select_best_transcript(self,
                                transcripts: List[Transcript],
                                video_id: str,
                                default_language: Optional[str],
                                default_audio_language: Optional[str]
                               ) -> Tuple[Optional[Transcript], str]:
        """
        Sélectionne la meilleure transcription disponible selon un ordre de préférence.

        Args:
            transcripts: Liste des objets Transcript disponibles pour la vidéo.
            video_id: ID de la vidéo (pour logs).
            default_language: Langue par défaut des métadonnées de la vidéo.
            default_audio_language: Langue audio par défaut de la vidéo.

        Returns:
            Un tuple contenant :
            - L'objet Transcript sélectionné, ou None si aucune n'est adaptée.
            - Une chaîne décrivant l'origine de la sélection (pour logs).
        """
        if not transcripts:
            return None, "aucune disponible" # Cas simple : pas de transcriptions listées

        # Construire l'ordre de préférence des langues :
        # 1. Langue audio par défaut (base)
        # 2. Langue des métadonnées par défaut (base)
        # 3. Langues configurées dans config.TRANSCRIPT_LANGUAGES
        pref_langs_base = [lang.split('-')[0] for lang in [default_audio_language, default_language] if lang] # Prendre la base (ex: 'fr' de 'fr-FR')
        # Utiliser dict.fromkeys pour dédoublonner tout en préservant l'ordre
        pref_langs = list(dict.fromkeys(pref_langs_base + list(config.TRANSCRIPT_LANGUAGES)))
        logger.debug(f"Ordre de préférence des langues pour {video_id}: {pref_langs}")

        # Séparer les transcriptions manuelles et générées
        available_transcripts = {t.language_code: t for t in transcripts}
        available_manual = {lc: t for lc, t in available_transcripts.items() if not t.is_generated}
        available_generated = {lc: t for lc, t in available_transcripts.items() if t.is_generated}

        # Fonction helper pour chercher une langue (correspondance exacte puis langue de base)
        def find_lang(lang_code: str, source_dict: Dict[str, Transcript]) -> Optional[Transcript]:
            """Cherche une langue dans un dictionnaire de transcriptions."""
            # Chercher correspondance exacte (ex: 'fr-FR')
            if lang_code in source_dict: return source_dict[lang_code]
            # Si pas trouvé, chercher la langue de base (ex: 'fr')
            base_lang = lang_code.split('-')[0]
            # Vérifier la langue de base seulement si elle est différente du code original
            if base_lang != lang_code and base_lang in source_dict: return source_dict[base_lang]
            # Non trouvé
            return None

        # Logique de sélection par priorité :
        # 1. Chercher dans les langues préférées parmi les transcriptions MANUELLES
        for lang in pref_langs:
            transcript = find_lang(lang, available_manual)
            if transcript: return transcript, "MANUELLE préférée"
        # 2. Chercher dans les langues préférées parmi les transcriptions GÉNÉRÉES
        for lang in pref_langs:
            transcript = find_lang(lang, available_generated)
            if transcript: return transcript, "GÉNÉRÉE préférée"
        # 3. Si toujours pas trouvé, prendre N'IMPORTE QUELLE transcription MANUELLE (repli)
        if available_manual:
            # Retourner la première trouvée (l'ordre peut varier mais garantit une manuelle si existe)
            first_manual = next(iter(available_manual.values()))
            return first_manual, "MANUELLE (repli)"
        # 4. Si toujours pas trouvé, prendre N'IMPORTE QUELLE transcription GÉNÉRÉE (dernier recours)
        if available_generated:
            first_generated = next(iter(available_generated.values()))
            return first_generated, "GÉNÉRÉE (repli)"

        # Si on arrive ici, c'est qu'il n'y avait aucune transcription exploitable
        return None, "aucune trouvée correspondant aux critères"

    async def get_transcript(self, video_id: str, default_language: Optional[str] = None, default_audio_language: Optional[str] = None) -> Optional[Dict[str, str]]:
        """
        Récupère de manière asynchrone la meilleure transcription disponible pour un ID vidéo,
        la formate en blocs horodatés et met en cache le résultat (positif ou négatif).

        Args:
            video_id: L'ID de la vidéo YouTube.
            default_language: Langue par défaut des métadonnées (aide à la sélection).
            default_audio_language: Langue audio par défaut (aide à la sélection).

        Returns:
            Un dictionnaire {"language": code, "transcript": texte_formaté} ou None si échec/non disponible.
        """
        # Vérifier le cache final en premier (contient les succès et les échecs connus)
        async with self._final_transcript_cache_lock:
            if video_id in self._final_transcript_cache:
                logger.spam(f"Cache final HIT pour transcription {video_id}")
                return self._final_transcript_cache[video_id] # Peut être None si échec précédent mis en cache
            # Vérifier aussi s'il y a une erreur persistante connue pour cet ID
            if video_id in self._transcript_fetch_errors:
                 logger.warning(f"Récupération transcription ignorée pour {video_id} à cause d'une erreur persistante connue : {self._transcript_fetch_errors[video_id]}")
                 return None # Ne pas réessayer

        # Acquérir le sémaphore pour limiter les requêtes concurrentes
        async with self._semaphore:
            logger.info(f"Tentative de récupération asynchrone de transcription pour {video_id}")

            # --- Étape 1: Lister les transcriptions disponibles (via appel sync mis en cache) ---
            try:
                transcripts, list_error = await asyncio.to_thread(self._list_transcripts_sync, video_id)
                if list_error:
                    # Gérer les erreurs attendues où les transcriptions ne sont simplement pas disponibles
                    if isinstance(list_error, (TranscriptsDisabled, NoTranscriptFound) + YouTubeTranscriptApiErrors.TRANSCRIPT_FETCH_ERRORS):
                        logger.warning(f"Transcriptions non disponibles pour {video_id}: {list_error.__class__.__name__}")
                        # Mettre en cache le résultat négatif et l'erreur persistante
                        async with self._final_transcript_cache_lock:
                            self._final_transcript_cache[video_id] = None
                            self._transcript_fetch_errors[video_id] = list_error
                        return None
                    else:
                        # Remonter les erreurs inattendues lors du listage
                        raise list_error
            except Exception as e:
                 # Gérer les erreurs inattendues pendant l'appel asynchrone à list_transcripts
                 logger.error(f"Erreur lors de l'appel asynchrone à list_transcripts pour {video_id}: {e}", exc_info=True)
                 # Mettre en cache le résultat négatif en cas d'erreur de listage inattendue
                 async with self._final_transcript_cache_lock: self._final_transcript_cache[video_id] = None
                 return None

            # --- Étape 2: Sélectionner la meilleure transcription parmi celles disponibles ---
            target_transcript, log_origin = self._select_best_transcript(
                transcripts, video_id, default_language, default_audio_language
            )

            # Si aucune transcription appropriée n'a été trouvée
            if not target_transcript:
                logger.warning(f"Aucune transcription adaptée trouvée pour {video_id} selon les préférences ({log_origin}).")
                # Mettre en cache le résultat négatif
                async with self._final_transcript_cache_lock: self._final_transcript_cache[video_id] = None
                return None

            # --- Étape 3: Récupérer le contenu de la transcription sélectionnée ---
            logger.debug(f"Tentative de récupération asynchrone pour {video_id} ({target_transcript.language_code}) - Origine: {log_origin}")
            try:
                # Exécuter l'appel de récupération synchrone dans un thread
                transcript_data, fetch_error = await asyncio.to_thread(self._fetch_transcript_sync, target_transcript)

                # Gérer les erreurs de récupération
                if fetch_error:
                    logger.warning(f"Échec de la récupération de la transcription {log_origin} pour {video_id} ({target_transcript.language_code}): {fetch_error}")
                    # Mettre en cache l'erreur si elle est probablement persistante
                    if isinstance(fetch_error, CouldNotRetrieveTranscript):
                         async with self._final_transcript_cache_lock:
                             # Ne pas écraser une erreur précédente si elle existe déjà
                             if video_id not in self._transcript_fetch_errors:
                                 self._transcript_fetch_errors[video_id] = fetch_error
                    # Ne pas mettre en cache de résultat négatif ici, l'erreur pourrait être temporaire
                    return None # Indiquer l'échec pour cette tentative

                # --- Étape 4: Formater la transcription récupérée ---
                if transcript_data is not None: # Peut être une liste vide si fetch OK mais pas de contenu
                    # Exécuter le formatage synchrone dans un thread
                    formatted_text = await asyncio.to_thread(
                        self._format_transcript_by_blocks_sync,
                        transcript_data, target_transcript.language_code, video_id, log_origin
                    )

                    if formatted_text is not None:
                        # Succès ! Mettre en cache et retourner le résultat.
                        logger.info(f"Transcription récupérée et formatée avec succès pour {video_id} ({target_transcript.language_code}) - Origine: {log_origin}")
                        result = {"language": target_transcript.language_code, "transcript": formatted_text}
                        async with self._final_transcript_cache_lock:
                            self._final_transcript_cache[video_id] = result
                        return result
                    else:
                        # Le formatage a échoué ou a résulté en un texte vide
                        logger.warning(f"Le formatage a échoué ou a résulté en une transcription vide pour {video_id} ({target_transcript.language_code})")
                        # Mettre en cache un résultat négatif si le formatage échoue de manière constante
                        async with self._final_transcript_cache_lock:
                            self._final_transcript_cache[video_id] = None
                        return None
                else:
                    # Cas où fetch_error était None, mais transcript_data est None (ne devrait pas arriver)
                     logger.warning(f"La récupération de la transcription a retourné None sans erreur pour {video_id} ({target_transcript.language_code})")
                     async with self._final_transcript_cache_lock:
                         self._final_transcript_cache[video_id] = None
                     return None

            except Exception as e:
                 # Capturer les erreurs inattendues pendant le processus de récupération/formatage
                 logger.error(f"Erreur inattendue pendant le processus get_transcript pour {video_id} ({target_transcript.language_code}): {e}", exc_info=True)
                 # Mettre en cache un résultat négatif en cas d'erreur inattendue
                 async with self._final_transcript_cache_lock:
                     self._final_transcript_cache[video_id] = None
                 return None

        # Point de sortie si le sémaphore expire ou autre échec non géré
        logger.error(f"Le traitement de la transcription a échoué de manière inattendue pour {video_id} après le sémaphore.")
        async with self._final_transcript_cache_lock:
            self._final_transcript_cache[video_id] = None
        return None

# ==============================================================================
# SECTION 7 : Gestionnaire de Fichiers
# ==============================================================================

# Tentative de chargement global de l'encodeur Tiktoken
ENCODING: Optional[tiktoken.Encoding] = None
try:
    ENCODING = tiktoken.get_encoding("cl100k_base")
    logger.debug("Encodeur Tiktoken cl100k_base chargé avec succès.")
except Exception as e:
    logger.warning(f"Impossible de charger l'encodeur Tiktoken : {e}. Le comptage de tokens pour le découpage de fichiers sera désactivé.")

def save_video_data_files(
    videos: List[Video],
    source_name: str,
    output_format: str, # 'txt', 'md', 'yaml'
    include_description: bool = True,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> List[Tuple[Path, int, int]]:
    """
    Sauvegarde les données vidéo (métadonnées, description, transcription) dans des fichiers
    au format spécifié (txt, md, yaml), en les découpant en parties si nécessaire
    en fonction du nombre estimé de tokens.

    Args:
        videos: Liste d'objets Video à sauvegarder (supposée triée).
        source_name: Nom descriptif de la source (ex: titre playlist) utilisé pour les noms de fichiers.
        output_format: Le format de sortie souhaité ('txt', 'md', 'yaml').
        include_description: Inclure la description de la vidéo dans la sortie.
        progress_callback: Fonction optionnelle pour rapporter la progression (index_video_courante, total_videos).

    Returns:
        Une liste de tuples, chaque tuple contenant (Chemin_fichier_créé, tokens_estimés, nombre_videos).
    """
    if not videos:
        logger.info("Aucune vidéo fournie pour la sauvegarde.")
        return []

    logger.info(f"Début du processus de sauvegarde pour la source '{source_name}' ({len(videos)} vidéos) au format : {output_format.upper()}")

    created_files: List[Tuple[Path, int, int]] = [] # Liste pour stocker les infos des fichiers créés
    current_part_number = 1 # Numéro de la partie en cours
    # Stocker les données formatées (chaîne pour txt/md, dict pour yaml)
    current_part_data: Union[List[str], List[Dict[str, Any]]]
    current_part_tokens = 0 # Tokens estimés pour la partie en cours
    current_part_video_count = 0 # Nombre de vidéos dans la partie en cours
    total_videos_processed = 0 # Compteur global pour le callback de progression

    # Générer un nom de fichier de base sûr à partir du nom de la source
    base_filename = clean_title(source_name) or f"Resultats_{datetime.now():%Y%m%d_%H%M%S}"
    save_folder = config.VIDEOS_FOLDER # Dossier de sauvegarde configuré
    file_extension = f".{output_format}" # Extension basée sur le format

    # Déterminer la fonction de formatage et initialiser la liste de données de la partie
    formatter: Callable[[Video, bool], Union[str, Dict[str, Any]]]
    if output_format == 'yaml':
        formatter = lambda v, inc_desc: v.to_dict(inc_desc)
        current_part_data = [] # Liste de dictionnaires pour YAML
    elif output_format == 'md':
        formatter = lambda v, inc_desc: v.to_markdown(inc_desc)
        current_part_data = [] # Liste de chaînes Markdown
    else: # Par défaut : txt
        formatter = lambda v, inc_desc: v.to_texte(inc_desc)
        current_part_data = [] # Liste de chaînes texte

    # Itérer sur chaque vidéo à sauvegarder
    for idx, video in enumerate(videos):
        logger.debug(f"Préparation de la vidéo {idx+1}/{len(videos)} ({video.id}) pour sauvegarde en {output_format.upper()}.")
        try:
            # Formater les données de la vidéo selon le format choisi
            formatted_data: Union[str, Dict[str, Any]] = formatter(video, include_description)
            item_tokens = 0 # Tokens estimés pour cette vidéo
            item_str_representation = "" # Représentation chaîne pour l'estimation des tokens

            # Obtenir la représentation chaîne pour l'estimation
            if isinstance(formatted_data, str):
                item_str_representation = formatted_data
            elif isinstance(formatted_data, dict):
                # Pour YAML, estimer les tokens en dumpant temporairement l'item unique
                try:
                    # Utiliser des options pour un dump YAML lisible
                    item_str_representation = yaml.dump(
                        formatted_data, allow_unicode=True, sort_keys=False, width=120, default_flow_style=False
                    )
                except Exception as yaml_err:
                    logger.warning(f"Impossible de dumper le dict vidéo en chaîne pour l'estimation des tokens ({video.id}): {yaml_err}")
                    item_str_representation = str(formatted_data) # Solution de repli

            # Estimer les tokens si l'encodeur est disponible et une limite est définie
            if ENCODING and config.MAX_TOKENS_PER_FILE > 0 and item_str_representation:
                try:
                    item_tokens = len(ENCODING.encode(item_str_representation))
                except Exception as enc_e:
                    logger.warning(f"Échec de l'encodage Tiktoken pour la représentation de la vidéo {video.id}: {enc_e}. Tokens comptés comme 0.")

            # Vérifier si l'ajout de cette vidéo dépasse la limite de tokens pour la partie en cours
            # Découper seulement si une limite est définie (> 0) et si la partie contient déjà des vidéos
            if (current_part_video_count > 0 and
                config.MAX_TOKENS_PER_FILE > 0 and
                current_part_tokens + item_tokens > config.MAX_TOKENS_PER_FILE):

                # Sauvegarder la partie actuelle avant d'en commencer une nouvelle
                part_filename = f"{base_filename}_partie-{current_part_number:02d}{file_extension}"
                part_filepath = save_folder / part_filename
                logger.debug(f"Limite de tokens ({config.MAX_TOKENS_PER_FILE}) atteinte. Sauvegarde de la partie {current_part_number} ({current_part_tokens} tokens, {current_part_video_count} vidéos) -> {part_filepath.name}")

                # Appeler la fonction de sauvegarde appropriée selon le format
                save_successful = False
                if output_format == 'yaml':
                    # Assurer que current_part_data est bien une liste de dicts
                    if all(isinstance(item, dict) for item in current_part_data):
                        save_successful = _save_yaml_content(part_filepath, current_part_data)
                    else:
                        logger.error(f"Type de données incorrect pour la sauvegarde YAML de la partie {current_part_number}.")
                else: # txt or md
                    # Assurer que current_part_data est bien une liste de str
                    if all(isinstance(item, str) for item in current_part_data):
                        save_successful = _save_formatted_text(part_filepath, current_part_data, output_format)
                    else:
                         logger.error(f"Type de données incorrect pour la sauvegarde {output_format.upper()} de la partie {current_part_number}.")

                # Enregistrer les informations du fichier si la sauvegarde a réussi
                if save_successful:
                    created_files.append((part_filepath, current_part_tokens, current_part_video_count))
                else:
                    logger.error(f"Échec de la sauvegarde de la partie {current_part_number} vers {part_filepath.name}")

                # Réinitialiser pour la nouvelle partie
                current_part_number += 1
                # Réinitialiser la liste de données en fonction du format
                if output_format == 'yaml': current_part_data = []
                else: current_part_data = []
                current_part_tokens = 0
                current_part_video_count = 0

            # Ajouter les données formatées de la vidéo actuelle à la partie en cours
            # Type checker peut avoir du mal ici, mais la logique est correcte
            current_part_data.append(formatted_data) # type: ignore
            current_part_tokens += item_tokens
            current_part_video_count += 1
            total_videos_processed += 1

            # Rapporter la progression via le callback
            if progress_callback:
                progress_callback(total_videos_processed, len(videos))

        except Exception as e:
            # Gérer les erreurs lors du traitement d'une vidéo spécifique
            logger.error(f"Erreur lors du traitement de la vidéo {video.id} pour la sauvegarde: {e}", exc_info=True)
            # Continuer avec la vidéo suivante

    # Sauvegarder le contenu restant dans la dernière partie
    if current_part_data:
        # Déterminer si c'est la seule partie (pas de suffixe _partie-XX)
        is_single_part = (current_part_number == 1 and not created_files)
        final_filename = f"{base_filename}{file_extension}" if is_single_part else f"{base_filename}_partie-{current_part_number:02d}{file_extension}"
        final_filepath = save_folder / final_filename
        part_desc = "unique" if is_single_part else f"{current_part_number} (finale)"
        logger.debug(f"Sauvegarde de la partie {part_desc} ({current_part_tokens} tokens, {current_part_video_count} vidéos) -> {final_filepath.name}")

        # Appeler la fonction de sauvegarde appropriée
        save_successful = False
        if output_format == 'yaml':
            if all(isinstance(item, dict) for item in current_part_data):
                save_successful = _save_yaml_content(final_filepath, current_part_data) # type: ignore
            else: logger.error("Type de données incorrect pour sauvegarde YAML finale.")
        else: # txt or md
            if all(isinstance(item, str) for item in current_part_data):
                save_successful = _save_formatted_text(final_filepath, current_part_data, output_format) # type: ignore
            else: logger.error(f"Type de données incorrect pour sauvegarde {output_format.upper()} finale.")

        # Enregistrer les informations du fichier si succès
        if save_successful:
            created_files.append((final_filepath, current_part_tokens, current_part_video_count))
        else:
            logger.error(f"Échec de la sauvegarde de la partie {part_desc} vers {final_filepath.name}")

    logger.info(f"Sauvegarde terminée pour la source '{source_name}'. Créé {len(created_files)} fichier(s) dans '{save_folder.relative_to(config.WORK_FOLDER)}'.")
    return created_files

def _save_formatted_text(file_path: Path, content_list: List[str], format_type: str) -> bool:
    """Sauvegarde une liste de chaînes (TXT ou MD) dans un fichier."""
    if not content_list:
        logger.warning(f"Tentative de sauvegarde de contenu texte vide vers {file_path}. Ignoré.")
        return False
    try:
        logger.debug(f"Écriture de {len(content_list)} blocs de contenu dans le fichier {format_type.upper()} : {file_path.name}")
        # Choisir le séparateur en fonction du format
        separator = "\n\n---\n\n" if format_type == 'md' else "\n\n" + "=" * 80 + "\n\n"
        # Utiliser newline='' pour éviter les doubles sauts de ligne potentiels sous Windows
        with file_path.open("w", encoding="utf-8", errors="replace", newline='') as f:
            f.write(separator.join(content_list))
        logger.debug(f"Fichier {format_type.upper()} écrit avec succès : {file_path.name}")
        return True
    except OSError as e:
        logger.error(f"Erreur OS lors de l'écriture du fichier {file_path}: {e}")
        return False
    except Exception as e:
        logger.error(f"Erreur inattendue lors de l'écriture du fichier {file_path}: {e}", exc_info=True)
        return False

def _save_yaml_content(file_path: Path, data_list: List[Dict[str, Any]]) -> bool:
    """Sauvegarde une liste de dictionnaires dans un fichier YAML."""
    if not data_list:
        logger.warning(f"Tentative de sauvegarde d'une liste de données vide vers le fichier YAML {file_path}. Ignoré.")
        return False
    try:
        logger.debug(f"Écriture de {len(data_list)} entrées de données vidéo dans le fichier YAML : {file_path.name}")
        # Utiliser PyYAML pour écrire la liste de dictionnaires
        with file_path.open("w", encoding="utf-8") as f:
            # allow_unicode=True pour préserver les caractères non-ASCII
            # sort_keys=False pour garder l'ordre des clés défini dans to_dict
            # width=120 pour un formatage plus large
            # default_flow_style=False pour un style bloc (plus lisible)
            yaml.dump(data_list, f, allow_unicode=True, sort_keys=False, width=120, default_flow_style=False)
        logger.debug(f"Fichier YAML écrit avec succès : {file_path.name}")
        return True
    except yaml.YAMLError as e:
        # Erreur spécifique à YAML
        logger.error(f"Erreur YAML lors de l'écriture du fichier {file_path}: {e}")
        return False
    except OSError as e:
        # Erreur liée au système de fichiers
        logger.error(f"Erreur OS lors de l'écriture du fichier {file_path}: {e}")
        return False
    except Exception as e:
        # Autres erreurs inattendues
        logger.error(f"Erreur inattendue lors de l'écriture du fichier {file_path}: {e}", exc_info=True)
        return False

def read_urls_from_file(file_path_str: str) -> List[str]:
    """Lit les URLs depuis un fichier texte, ignorant les lignes vides et les commentaires (#)."""
    path = Path(file_path_str)
    logger.info(f"Lecture des URLs depuis le fichier : {path.resolve()}")
    if not path.is_file():
        logger.error(f"Fichier d'URLs non trouvé : {path.resolve()}")
        return [] # Retourner liste vide si fichier non trouvé

    urls: List[str] = []
    try:
        # Spécifier explicitement l'encodage utf-8
        with path.open('r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                stripped_line = line.strip()
                # Ajouter si la ligne n'est pas vide et ne commence pas par #
                if stripped_line and not stripped_line.startswith('#'):
                    urls.append(stripped_line)
                elif stripped_line.startswith('#'):
                     # Logguer les commentaires ignorés au niveau SPAM
                     logger.log(SPAM_LEVEL_NUM, f"Ligne {line_num} ignorée (commentaire) dans {path.name}")
        logger.info(f"{len(urls)} URLs lues depuis {path.name}")
        return urls
    except Exception as e:
        # Gérer les erreurs de lecture de fichier
        logger.error(f"Erreur lors de la lecture du fichier d'URLs {path.resolve()}: {e}", exc_info=True)
        return [] # Retourner liste vide en cas d'erreur

# ==============================================================================
# SECTION 8 : Moteur du Scraper
# ==============================================================================

class YoutubeScraperEngine:
    """Orchestre le processus de récupération et de sauvegarde des données YouTube pour plusieurs URLs."""
    TOTAL_STEPS: int = 5 # Nombre total d'étapes pour l'affichage de la progression

    def __init__(self, api_client: YouTubeAPIClient, transcript_manager: TranscriptManager, progress_display: ProgressDisplay):
        """
        Initialise le moteur du scraper.

        Args:
            api_client: Instance du client API YouTube.
            transcript_manager: Instance du gestionnaire de transcriptions.
            progress_display: Instance du gestionnaire d'affichage de la progression.
        """
        self.api_client: YouTubeAPIClient = api_client
        self.transcript_manager: TranscriptManager = transcript_manager
        self.progress_display: ProgressDisplay = progress_display
        self.quota_reached: bool = False # Indicateur pour arrêter le traitement si le quota est atteint

    async def _mark_steps_as_status(self, url_index: int, start_step: int, message: str, status: str) -> None:
        """Marque toutes les étapes à partir de start_step avec le statut et le message donnés."""
        # Utiliser l'icône correspondant au statut, ou l'icône d'erreur par défaut
        icon_status = status if status in ProgressDisplay.ICONS else ProgressStatus.ERROR
        # Itérer sur les étapes restantes (ou toutes si start_step=1)
        for step in range(start_step, self.TOTAL_STEPS + 1):
            # Vérifier si l'étape existe pour cet index d'URL avant de la mettre à jour
            if url_index in self.progress_display.url_steps_mapping and step in self.progress_display.url_steps_mapping[url_index]:
                 # Utiliser le message principal pour la première étape marquée, un message générique ensuite
                 step_message = message if step == start_step else "Étape précédente échouée/arrêtée"
                 await self.progress_display.update_step(url_index, step, icon_status, message=step_message)

    @staticmethod
    def _get_sort_key(video: Video) -> datetime:
        """Retourne la date de publication datetime pour le tri (utilise min datetime si inconnu)."""
        dt = video.get_published_at_datetime()
        # Utiliser datetime.min avec fuseau horaire UTC pour les vidéos sans date valide
        # pour assurer un tri cohérent (généralement au début).
        return dt if dt else datetime.min.replace(tzinfo=timezone.utc)

    # --- Méthodes privées pour chaque étape du traitement d'une URL ---

    async def _process_step_1_analyze(self, url: str, url_index: int) -> Optional[Tuple[str, str]]:
        """Traite l'Étape 1 : Analyse de l'URL."""
        step = 1
        await self.progress_display.update_step(url_index, step, ProgressStatus.IN_PROGRESS, message="Analyse URL...")
        identifier_info = await self.api_client.extract_identifier(url)
        if not identifier_info:
            raise ValueError("Format d'URL invalide ou non reconnu") # Levé pour être attrapé par process_url
        identifier, content_type = identifier_info
        await self.progress_display.update_step(url_index, step, ProgressStatus.DONE, message=f"Type: {content_type}")
        return identifier, content_type

    async def _process_step_2_get_ids(self, url_index: int, content_type: str, identifier: str) -> Tuple[List[str], str]:
        """Traite l'Étape 2 : Récupération des IDs Vidéo."""
        step = 2
        await self.progress_display.update_step(url_index, step, ProgressStatus.IN_PROGRESS, message="Recherche vidéos...")
        video_ids, source_name = await self.api_client.get_videos_from_source(content_type, identifier)
        if not video_ids:
            # Avertir mais ne pas lever d'erreur, retourner liste vide
            await self.progress_display.show_warning(f"0 vidéo trouvée ou valide pour '{source_name}' (filtre initial)")
            await self.progress_display.update_step(url_index, step, ProgressStatus.WARNING, message="0 vidéo trouvée/valide")
            return [], source_name # Retourner liste vide et nom de source
        await self.progress_display.update_step(url_index, step, ProgressStatus.DONE, message=f"{len(video_ids)} vidéo(s) potentielle(s)")
        return video_ids, source_name

    async def _process_step_3_get_details_transcripts(self, url_index: int, video_ids: List[str], source_name: str, include_transcript: bool) -> Tuple[List[Video], int]:
        """Traite l'Étape 3 : Récupération des Détails & Transcriptions."""
        step = 3
        await self.progress_display.update_step(url_index, step, ProgressStatus.IN_PROGRESS, message="Récup. détails...")
        videos_details = await self.api_client.get_video_details_batch(video_ids)
        if not videos_details:
            # Avertir mais ne pas lever d'erreur
            await self.progress_display.show_warning(f"Aucune vidéo valide après récupération des détails pour '{source_name}'.")
            await self.progress_display.update_step(url_index, step, ProgressStatus.WARNING, message="0 vidéo valide post-détails")
            return [], 0 # Retourner liste vide

        final_vid_count = len(videos_details)
        transcript_count = 0
        # Traiter les transcriptions seulement si demandé
        if include_transcript:
            await self.progress_display.update_step(url_index, step, ProgressStatus.IN_PROGRESS, message=f"Récup. transcriptions ({final_vid_count} vidéos)...")
            # Cette méthode gère sa propre progression interne pour les transcriptions
            videos_details, transcript_count = await self._process_transcripts_concurrently(videos_details, url_index, step)
            final_vid_count = len(videos_details) # Mettre à jour au cas où des erreurs critiques se produisent

        # Vérifier s'il reste des vidéos après le traitement des transcriptions
        if final_vid_count == 0:
             await self.progress_display.show_warning(f"Aucune vidéo restante après traitement des transcriptions pour '{source_name}'.")
             await self.progress_display.update_step(url_index, step, ProgressStatus.WARNING, message="0 vidéo après transcripts")
             return [], 0

        # Marquer l'étape comme terminée
        await self.progress_display.update_step(url_index, step, ProgressStatus.DONE, message=f"{final_vid_count} vidéo(s), {transcript_count} transcript(s)")
        return videos_details, transcript_count

    async def _process_step_4_sort(self, url_index: int, videos_details: List[Video], source_name: str) -> List[Video]:
        """Traite l'Étape 4 : Tri des Vidéos."""
        step = 4
        await self.progress_display.update_step(url_index, step, ProgressStatus.SORT, message="Tri chronologique...")
        try:
            # Trier la liste de vidéos en place par date de publication
            videos_details.sort(key=self._get_sort_key)
            logger.info(f"Tri chronologique terminé pour {len(videos_details)} vidéos de '{source_name}'.")
            await self.progress_display.update_step(url_index, step, ProgressStatus.DONE, message=f"{len(videos_details)} triée(s)")
            return videos_details
        except Exception as sort_e:
            # Gérer les erreurs potentielles pendant le tri
            logger.error(f"Erreur lors du tri des vidéos pour '{source_name}': {sort_e}", exc_info=True)
            await self.progress_display.update_step(url_index, step, ProgressStatus.ERROR, message=f"Erreur de tri: {sort_e}")
            raise # Remonter l'erreur pour arrêter le traitement de cette URL

    async def _process_step_5_save(self, url_index: int, videos_details: List[Video], source_name: str, output_format: str, include_description: bool) -> List[Tuple[Path, int, int]]:
        """Traite l'Étape 5 : Sauvegarde des Fichiers dans le format spécifié."""
        step = 5
        await self.progress_display.update_step(url_index, step, ProgressStatus.IN_PROGRESS, message=f"Sauvegarde ({output_format.upper()})...")

        loop = asyncio.get_running_loop()
        # Définir un wrapper de callback synchrone pour mettre à jour l'affichage async depuis le thread sync
        def progress_callback_sync(current: int, total: int):
            """Callback synchrone pour la progression de la sauvegarde."""
            if total > 0:
                percent = (current / total) * 100
                message = f"{current}/{total}"
                # Planifier l'exécution de la coroutine de mise à jour dans la boucle d'événements principale
                asyncio.run_coroutine_threadsafe(
                    self.progress_display.update_step(url_index, step, ProgressStatus.IN_PROGRESS, percent, message),
                    loop
                )

        # Exécuter la fonction de sauvegarde (potentiellement longue) dans un thread séparé
        created_files = await asyncio.to_thread(
            save_video_data_files, # Utiliser la fonction de sauvegarde mise à jour
            videos_details,
            source_name,
            output_format, # Passer le format de sortie
            include_description,
            progress_callback_sync # Passer le callback synchrone
        )
        # Marquer l'étape comme terminée
        await self.progress_display.update_step(url_index, step, ProgressStatus.DONE, message=f"{len(created_files)} fichier(s) ({output_format.upper()})")
        return created_files

    # --- Méthode principale de traitement d'une URL ---
    async def process_url(self, url: str, url_index: int, output_format: str, include_transcript: bool, include_description: bool) -> List[Tuple[Path, int, int]]:
        """
        Traite une seule URL à travers toutes les étapes : analyse, récupération IDs,
        récupération détails/transcriptions, tri, sauvegarde.
        Gère les erreurs et les exceptions de quota pour le flux de traitement de cette URL.

        Args:
            url: L'URL YouTube à traiter.
            url_index: L'index séquentiel de cette URL dans la liste globale.
            output_format: Le format de sortie souhaité ('txt', 'md', 'yaml').
            include_transcript: Faut-il inclure les transcriptions ?
            include_description: Faut-il inclure les descriptions ?

        Returns:
            Une liste des fichiers créés pour cette URL, ou une liste vide en cas d'échec majeur.
        """
        all_files_for_this_url: List[Tuple[Path, int, int]] = []
        source_name = url # Nom de source par défaut
        current_step = 0 # Suivre l'étape actuelle pour les logs d'erreur

        try:
            # Afficher l'en-tête pour cette URL (retourne l'index réel utilisé par ProgressDisplay)
            actual_url_index = await self.progress_display.show_url_header(url)
            # S'assurer qu'on utilise le bon index pour les mises à jour suivantes
            if actual_url_index != url_index:
                 logger.warning(f"Désaccord d'index URL : attendu {url_index}, obtenu {actual_url_index}. Utilisation de {actual_url_index}.")
                 url_index = actual_url_index # Corriger l'index

            # --- Exécution des étapes séquentielles ---
            current_step = 1
            identifier_info = await self._process_step_1_analyze(url, url_index)
            if not identifier_info: return [] # Erreur gérée dans la méthode step
            identifier, content_type = identifier_info

            current_step = 2
            video_ids, source_name = await self._process_step_2_get_ids(url_index, content_type, identifier)
            if not video_ids:
                # Si aucune vidéo trouvée, marquer les étapes restantes comme ignorées et retourner
                await self._mark_steps_as_status(url_index, current_step + 1, "Aucune vidéo trouvée/valide", ProgressStatus.SKIPPED)
                return []

            current_step = 3
            videos_details, _ = await self._process_step_3_get_details_transcripts(url_index, video_ids, source_name, include_transcript)
            if not videos_details:
                # Si aucune vidéo après détails/transcripts, marquer et retourner
                await self._mark_steps_as_status(url_index, current_step + 1, "Aucune vidéo après détails/transcripts", ProgressStatus.SKIPPED)
                return []

            current_step = 4
            # Le tri peut lever une exception, qui sera attrapée ci-dessous
            videos_details = await self._process_step_4_sort(url_index, videos_details, source_name)

            current_step = 5
            # La sauvegarde peut aussi échouer, mais gère ses erreurs internes
            created_files = await self._process_step_5_save(url_index, videos_details, source_name, output_format, include_description)
            all_files_for_this_url.extend(created_files)

        except QuotaExceededError:
            # Gérer spécifiquement l'erreur de quota
            error_msg = "Quota API YouTube dépassé"
            logger.critical(f"{error_msg} lors du traitement de l'URL {url_index} ({url}) à l'étape {current_step}.")
            await self.progress_display.show_quota_exceeded("Traitement arrêté pour les URLs suivantes.")
            # Marquer les étapes restantes comme échouées à cause du quota
            await self._mark_steps_as_status(url_index, current_step, error_msg, ProgressStatus.QUOTA)
            self.quota_reached = True # Mettre le drapeau pour arrêter le traitement global
        except (ValueError, HttpError) as e:
            # Gérer les erreurs attendues (URL invalide, ressource non trouvée, etc.)
            error_msg = str(e)
            logger.error(f"Erreur lors du traitement de l'URL {url_index} ({url}) à l'étape {current_step}: {error_msg}", exc_info=isinstance(e, HttpError))
            await self.progress_display.show_error(f"Erreur: {error_msg}")
            # Marquer les étapes restantes comme échouées
            await self._mark_steps_as_status(url_index, current_step, error_msg, ProgressStatus.ERROR)
        except Exception as e_global:
            # Gérer les erreurs critiques inattendues
            error_msg = f"Erreur inattendue: {e_global}"
            logger.critical(f"Erreur critique lors du traitement de l'URL {url_index} ({url}) à l'étape {current_step}: {error_msg}", exc_info=True)
            await self.progress_display.show_error(f"Erreur Critique: {error_msg}")
            # Marquer toutes les étapes à partir de l'étape actuelle (ou 1 si erreur très tôt) comme échouées
            start_fail_step = current_step if current_step > 0 else 1
            await self._mark_steps_as_status(url_index, start_fail_step, f"Critique: {error_msg}", ProgressStatus.ERROR)

        # Retourner la liste des fichiers créés pour cette URL (peut être vide si erreur)
        return all_files_for_this_url

    async def _process_transcripts_concurrently(self, videos: List[Video], url_index: int, step_number: int) -> Tuple[List[Video], int]:
        """Récupère les transcriptions de manière concurrente pour une liste de vidéos et met à jour la progression."""
        total_v = len(videos)
        if total_v == 0: return [], 0 # Rien à faire

        # Créer les tâches coroutines pour récupérer chaque transcription
        coroutines = [
            self.transcript_manager.get_transcript(
                video.id, video.default_language, video.default_audio_language
            ) for video in videos
        ]

        logger.debug(f"Lancement de {len(coroutines)} tâches de transcription concurrentes pour URL {url_index}")
        # Exécuter les tâches avec asyncio.gather, récupérer résultats ou exceptions
        results: List[Union[Optional[Dict[str, str]], Exception]] = await asyncio.gather(*coroutines, return_exceptions=True)
        logger.debug(f"Reçu {len(results)} résultats/exceptions de la récupération concurrente des transcriptions pour URL {url_index}")

        processed_vids: List[Video] = [] # Liste pour conserver les vidéos après traitement
        found_count = 0 # Compteur de transcriptions trouvées
        failed_count = 0 # Compteur d'échecs/absences
        tasks_completed = 0 # Compteur pour la progression

        # Traiter les résultats de gather
        for i, result in enumerate(results):
            tasks_completed += 1
            video = videos[i] # Obtenir l'objet Video correspondant

            # Mettre à jour l'affichage de la progression de manière fluide
            percent = (tasks_completed / total_v) * 100
            message = f"Traitement transcription {tasks_completed}/{total_v}"
            # Appeler la mise à jour de l'étape (ne bloque pas longtemps)
            await self.progress_display.update_step(url_index, step_number, ProgressStatus.IN_PROGRESS, percent, message)

            if isinstance(result, Exception):
                # Une exception a été retournée par gather pour cette tâche
                logger.warning(f"La récupération asynchrone de transcription a échoué pour {video.id} (via gather): {result}", exc_info=False)
                failed_count += 1
                # Conserver l'objet vidéo même si la transcription échoue
                processed_vids.append(video)
            elif result and isinstance(result, dict) and result.get("transcript"):
                # Transcription récupérée et formatée avec succès
                video.transcript = result # Attacher le dict transcript à l'objet vidéo
                video.video_transcript_language = result.get('language') # Stocker la langue réelle
                found_count += 1
                logger.log(SPAM_LEVEL_NUM, f"Transcription assignée pour {video.id} (Langue: {video.video_transcript_language})")
                processed_vids.append(video)
            else:
                # Le résultat est None ou un dict vide (non trouvé ou formatage échoué)
                failed_count += 1
                logger.log(SPAM_LEVEL_NUM, f"Transcription non trouvée ou vide pour {video.id}")
                processed_vids.append(video) # Conserver la vidéo

        logger.info(f"Traitement des transcriptions pour URL {url_index} terminé : {found_count} trouvées, {failed_count} échouées/absentes sur {total_v}.")
        # Retourner la liste des vidéos (certaines peuvent maintenant avoir une transcription) et le nombre trouvé
        return processed_vids, found_count

    async def process_urls(self, urls: List[str], output_format: str, include_transcript: bool, include_description: bool) -> List[Tuple[Path, int, int]]:
        """
        Traite une liste d'URLs séquentiellement, orchestrant le scraping pour chacune.
        S'arrête si le quota API est dépassé.

        Args:
            urls: La liste des URLs YouTube à traiter.
            output_format: Le format de sortie souhaité ('txt', 'md', 'yaml').
            include_transcript: Faut-il inclure les transcriptions ?
            include_description: Faut-il inclure les descriptions ?

        Returns:
            Une liste de tous les fichiers créés pour toutes les URLs traitées avec succès.
        """
        all_created_files: List[Tuple[Path, int, int]] = [] # Accumulateur pour tous les fichiers
        total_urls_to_process = len(urls)
        # Démarrer l'affichage Live pour l'ensemble du processus
        await self.progress_display.start_processing(total_urls_to_process)

        # Itérer sur chaque URL fournie
        for url_idx, url in enumerate(urls, 1):
            # Arrêter immédiatement si le quota a été atteint lors du traitement d'une URL précédente
            if self.quota_reached:
                logger.warning(f"Quota API atteint. Ignorer URL {url_idx}/{total_urls_to_process}: {url}")
                # Marquer les étapes comme ignorées si l'en-tête a déjà été affiché pour cet index
                # (évite d'ajouter de nouvelles lignes si l'erreur survient avant show_url_header)
                if url_idx <= self.progress_display.url_counter:
                     await self._mark_steps_as_status(url_idx, 1, "Quota API dépassé", ProgressStatus.QUOTA)
                continue # Passer à l'URL suivante (qui sera aussi ignorée)

            files_for_current_url: List[Tuple[Path, int, int]] = []
            try:
                # Traiter l'URL actuelle (gère ses propres erreurs internes, y compris QuotaExceededError)
                files_for_current_url = await self.process_url(
                    url, url_idx, output_format, include_transcript, include_description
                )
                # Ajouter les fichiers créés pour cette URL à la liste globale
                all_created_files.extend(files_for_current_url)
            except QuotaExceededError:
                # Devrait être attrapée dans process_url, mais sécurité ici.
                # Le drapeau self.quota_reached est déjà mis à True.
                logger.info(f"QuotaExceededError attrapée pour URL {url_idx}, arrêt des URLs suivantes.")
            except Exception as e:
                # Attraper les erreurs critiques inattendues qui remonteraient de process_url
                logger.critical(f"Erreur critique non gérée pour URL {url_idx} ({url}): {e}", exc_info=True)
                await self.progress_display.show_error(f"Erreur Critique traitant {url}: {e}")
                # Marquer les étapes comme échouées si l'en-tête a été affiché
                if url_idx <= self.progress_display.url_counter:
                    await self._mark_steps_as_status(url_idx, 1, f"Critique: {e}", ProgressStatus.ERROR)
                # Continuer avec l'URL suivante malgré l'erreur critique sur celle-ci ?
                # Pour l'instant, oui. On pourrait choisir de s'arrêter ici (break).
            finally:
                # Ajouter une petite pause entre chaque URL, même si pas d'erreur de quota,
                # pour être un peu plus respectueux envers l'API/système.
                if not self.quota_reached:
                    await asyncio.sleep(0.1)

        # Arrêter l'affichage Live après avoir traité toutes les URLs (ou arrêté à cause du quota)
        await self.progress_display.stop()
        # Retourner la liste complète des fichiers créés
        return all_created_files

# ==============================================================================
# SECTION 9 : Interface CLI et Point d'Entrée
# ==============================================================================

async def main_cli() -> int:
    """Fonction principale asynchrone pour l'application en ligne de commande."""
    console = Console(stderr=True) # Utiliser stderr pour l'interface utilisateur
    progress_display = ProgressDisplay() # Initialiser le gestionnaire d'affichage
    exit_code = 0 # Code de sortie par défaut (succès)

    try:
        # Afficher l'en-tête du script
        progress_display.show_header()

        # --- Vérification de la Configuration ---
        try:
            # Vérifier la présence de la clé API
            if not config.API_KEY:
                raise ValueError("Clé API YouTube (YOUTUBE_API_KEY) non trouvée dans les variables d'environnement.")
            logger.info(f"Configuration chargée. Dossier de travail : {config.WORK_FOLDER}")
        except ValueError as config_err:
            # Afficher l'erreur de configuration et quitter
            console.print(f"\n[bold red]ERREUR DE CONFIGURATION:[/]\n{config_err}")
            return 1 # Code de sortie 1 pour erreur de config

        # --- Entrée Utilisateur ---
        # Obtenir le mode, la valeur d'entrée, le format de sortie et les options d'inclusion
        mode, input_value, output_format, include_transcript, include_description = progress_display.show_menu()
        # Vérifier si une valeur d'entrée a été fournie
        if not input_value:
            console.print("\n[bold red]ERREUR : URL ou chemin de fichier manquant.[/]")
            return 1

        # --- Chargement des URLs ---
        urls: List[str] = []
        if mode == "1": # Mode URL unique
            urls = [input_value.strip()] if input_value.strip() else []
        else: # Mode fichier
            urls = read_urls_from_file(input_value)

        # Filtrer les chaînes vides potentielles après strip()
        urls = [u for u in urls if u]
        # Vérifier s'il y a des URLs valides à traiter
        if not urls:
            input_source_desc = "l'entrée utilisateur" if mode == '1' else f"le fichier '{input_value}'"
            console.print(f"\n[bold red]ERREUR : Aucune URL valide trouvée depuis {input_source_desc}.[/]")
            return 1

        logger.info(f"Début du traitement asynchrone pour {len(urls)} URL(s). Format: {output_format.upper()}, Transcriptions: {include_transcript}, Descriptions: {include_description}")

        # --- Initialisation des Composants ---
        api_client = YouTubeAPIClient(config.API_KEY)
        transcript_manager = TranscriptManager()
        engine = YoutubeScraperEngine(api_client, transcript_manager, progress_display)

        # --- Traitement Principal ---
        # Lancer le traitement des URLs et récupérer la liste des fichiers créés
        all_created_files = await engine.process_urls(
            urls, output_format, include_transcript, include_description
        )

        # --- Sortie Finale ---
        # L'affichage Live est arrêté à la fin de engine.process_urls
        # Afficher le tableau récapitulatif des fichiers
        progress_display.show_file_table(all_created_files)

        # Déterminer le code de sortie final
        if engine.quota_reached:
             console.print("\n[bold yellow]INFO : Le traitement a été interrompu car le quota API YouTube a été dépassé.[/]")
             exit_code = 2 # Code de sortie spécifique pour quota dépassé
        else:
             # Si le quota n'a pas été atteint et qu'aucune exception critique n'a stoppé le script,
             # considérer comme un succès (code 0). Des erreurs sur des URLs spécifiques
             # auront été logguées et affichées mais n'empêchent pas le succès global.
             exit_code = 0

    except ValueError as ve:
         # Attraper les erreurs de configuration ou de validation non interceptées plus tôt
         logger.critical(f"Erreur de configuration ou de validation : {ve}")
         await progress_display.stop() # Assurer l'arrêt de l'affichage
         console.print(f"\n[bold red]ERREUR : {ve}[/]")
         exit_code = 1
    except KeyboardInterrupt:
         # Gérer l'interruption par l'utilisateur (Ctrl+C)
         logger.warning("Interruption utilisateur (Ctrl+C) détectée.")
         await progress_display.stop()
         console.print("\n[yellow]Traitement interrompu par l'utilisateur.[/]")
         exit_code = 130 # Code de sortie standard pour Ctrl+C
    except Exception as e:
         # Gérer les erreurs critiques inattendues dans la fonction principale
         logger.critical(f"Erreur critique inattendue dans main_cli : {e}", exc_info=True)
         await progress_display.stop()
         # Afficher un message d'erreur clair à l'utilisateur
         console.print(f"\n[bold red]ERREUR CRITIQUE INATTENDUE:[/]\n{e}\nConsultez le fichier log : {config.WORK_FOLDER / 'youtube_scraper_async.log'}")
         exit_code = 1 # Code de sortie pour erreur générale
    finally:
        # Assurer que l'affichage Live est toujours arrêté, même en cas d'erreur précoce
        await progress_display.stop()
        logger.info(f"Exécution du script asynchrone terminée. Code de sortie final : {exit_code}")

    # Retourner le code de sortie déterminé
    return exit_code

# Point d'entrée principal du script
if __name__ == "__main__":
    final_exit_code = 1 # Code de sortie par défaut en cas d'erreur très précoce

    # Bloc try/except global pour lancer la fonction asynchrone principale
    try:
        # Exécuter la coroutine main_cli et récupérer son code de sortie
        final_exit_code = asyncio.run(main_cli())
    except KeyboardInterrupt:
        # Attraper Ctrl+C si cela se produit avant/pendant le démarrage de la boucle asyncio
        print("\n[yellow]Script interrompu pendant le démarrage ou l'arrêt.[/]")
        final_exit_code = 130
    except Exception as main_exception:
        # Attraper les erreurs fatales lors du démarrage d'asyncio.run
        print(f"\n[bold red]ERREUR FATALE AU DÉMARRAGE:[/]\n{main_exception}")
        # Essayer de logger l'erreur si possible
        try:
            logger.critical(f"Erreur fatale dans le bloc __main__ : {main_exception}", exc_info=True)
        except:
            pass # Ignorer si le logging lui-même échoue
        final_exit_code = 1
    finally:
        # Quitter le script avec le code de sortie final déterminé
        sys.exit(final_exit_code)
