// =============================================================================
// Youtubingest Frontend Script
// =============================================================================
// Handles UI interactions, API calls, state management, and dynamic updates.
// =============================================================================

// --- Application State ---
// Centralized state management object
const appState = {
    ui: {
        currentLang: 'en',           // Current interface language ('en' or 'fr')
        fontSizeMultiplier: 1,     // Multiplier for digest text area font size
        isDarkMode: false,         // Reflects the current theme
        isLoading: false,          // Is the application currently fetching/processing?
        toastTimeoutId: null,      // Timeout ID for the current toast message
        initialView: true,         // Is it the initial page load (for animations)?
    },
    history: {
        items: [],                 // Array of past search/ingest requests
        maxItems: 15,              // Maximum number of history items to store
    },
    currentRequest: {
        params: null,              // Parameters of the last/current request { url, includeTranscript, ... }
        sourceName: 'youtubingest_digest', // Default or derived source name for filenames
    },
    currentResult: {
        metadata: null,            // Full response data from the last successful request
        processedVideos: [],       // Structured video data from the last request (for MD/YAML)
        badgeValues: {             // Stored values for info badges (persist across lang changes)
            processingTimeMs: null,
            apiCallCount: null,
            apiQuotaUsed: null,
            tokenCount: null,
            highQuotaCost: false,
        },
        digestText: '',            // The generated text digest
    }
};

// --- Constants ---
const TOAST_ICONS = { success: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>', error: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>', warning: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>', info: '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>' };
const TOAST_CLASSES = { success: "toast-success", error: "toast-error", info: "toast-info", warning: "toast-warning" };
const FONT_SIZE_MIN_MULTIPLIER = 0.7;
const FONT_SIZE_MAX_MULTIPLIER = 1.5;
const FONT_SIZE_BASE_REM = 0.875;

// --- DOM Elements References ---
// Cache frequently accessed DOM elements
const domElements = {
    ingestForm: document.getElementById('ingestForm'),
    submitButton: document.getElementById('submitButton'),
    urlInput: document.getElementById('youtubeUrl'),
    highCostWarning: document.getElementById('highCostWarning'),
    confirmHighCostButton: document.getElementById('confirmHighCostButton'),
    includeTranscriptCheckbox: document.getElementById('includeTranscript'),
    includeDescriptionCheckbox: document.getElementById('includeDescription'),
    separateFilesCheckbox: document.getElementById('separateFiles'),
    transcriptIntervalSelect: document.getElementById('transcriptInterval'),
    startDateInput: document.getElementById('startDate'),
    endDateInput: document.getElementById('endDate'),
    exampleButtons: document.querySelectorAll('.example-button'),
    loadingDiv: document.getElementById('loading'),
    loadingStatusP: document.getElementById('loadingStatus'),
    errorDiv: document.getElementById('error'),
    errorMessageSpan: document.getElementById('errorMessage'),
    errorCodeSpan: document.getElementById('errorCode'),
    errorSuggestionP: document.getElementById('errorSuggestion'),
    resultsDiv: document.getElementById('results'),
    digestTextarea: document.getElementById('digest'),
    toast: document.getElementById('toast'),
    toastMessage: document.getElementById('toastMessage'),
    toastIcon: document.getElementById('toastIcon'),
    dismissToast: document.getElementById('dismissToast'),
    retryButton: document.getElementById('retryButton'),
    downloadTxtButton: document.getElementById('downloadTxtButton'),
    downloadMdButton: document.getElementById('downloadMdButton'),
    downloadYamlButton: document.getElementById('downloadYamlButton'),
    increaseFontButton: document.getElementById('increaseFontButton'),
    decreaseFontButton: document.getElementById('decreaseFontButton'),
    darkModeToggle: document.getElementById('darkModeToggle'),
    historyButton: document.getElementById('historyButton'),
    historyModal: document.getElementById('historyModal'),
    closeHistoryBtn: document.getElementById('closeHistoryBtn'),
    closeHistoryModalBtn: document.getElementById('closeHistoryModalBtn'),
    historyList: document.getElementById('historyList'),
    clearHistoryBtn: document.getElementById('clearHistoryBtn'),
    langButtons: document.querySelectorAll('.lang-button'),
    sourceNameElement: document.getElementById('source-name'),
    videoCountElement: document.getElementById('video-count'),
    processingTimeElement: document.getElementById('processing-time'), // Legacy element
    apiCallsElement: document.getElementById('api-calls'),       // Legacy element
    apiQuotaElement: document.getElementById('api-quota'),       // Legacy element
    processingTimeValueElement: document.getElementById('processing-time-value'),
    apiCallsValueElement: document.getElementById('api-calls-value'),
    apiQuotaValueElement: document.getElementById('api-quota-value'),
    tokenCountValueElement: document.getElementById('token-count-value'),
    apiCallsSuffixElement: document.getElementById('api-calls-suffix'),
    apiQuotaSuffixElement: document.getElementById('api-quota-suffix'),
    tokenCountSuffixElement: document.getElementById('token-count-suffix'),
    highQuotaCostBadge: document.getElementById('highQuotaCostBadge'),
    footerYear: document.getElementById('footerYear'),
    fontSizeTip: document.getElementById('fontSizeTip'),
};

// --- I18N Translations ---
// Moved translations object here (keep it the same as before)
const translations = {
     en: {
         pageTitle: "Youtubingest", historyButton: "History", themeButton: "Theme", githubButton: "GitHub", historyButtonLabel: "View Request History", themeButtonLabel: "Toggle dark mode", switchToEnglish: "Switch to English", switchToFrench: "Switch to French",
         mainHeading1: "Prompt-friendly", mainHeading2: "Youtube", mainDescription: "Transform a YouTube video, playlist, channel, or search<br class=\"hidden md-block\"> into text optimized for language models.",
         urlLabel: "YouTube URL or Search Term", urlPlaceholder: "Enter YouTube URL or search term here", ingestButton: "Ingest", ingestingButton: "Ingesting...",
         includeTranscriptLabel: "Include Transcript", includeTranscriptTooltip: "Fetch and include the video transcript if available.",
         includeDescriptionLabel: "Include Description", includeDescriptionTooltip: "Include the video description text in the digest.",
         separateFilesLabel: "Separate File per Video", separateFilesTooltip: "Create a separate file for each video (downloaded as a ZIP archive).",
         transcriptIntervalLabel: "Transcript Grouping (sec):", transcriptIntervalTooltip: "Group transcript lines by time interval. 'None' removes timestamps.", intervalOptionNone: "None",
         startDateLabel: "Start Date:", startDateTooltip: "Only include videos published on or after this date.",
         endDateLabel: "End Date:", endDateTooltip: "Only include videos published on or before this date.",
         exampleSectionTitle: "Or try these examples:", exampleVideo: "Simple Video", examplePlaylist: "Short Playlist", exampleChannel: "Channel (@Handle)", exampleSearch: "Text Search",
         exampleVideoLabel: "Try example: Simple Video", examplePlaylistLabel: "Try example: Short Playlist", exampleChannelLabel: "Try example: Channel (@Handle)", exampleSearchLabel: "Try example: Text Search",
         loadingInitializing: "Initializing...", loadingFetching: "Fetching information...", loadingGenerating: "Generating digest...", loadingMoment: "This might take a moment...",
         errorTitle: "Error during ingestion", errorSuggestionPrefix: "Suggestion:", retryButton: "Retry", retryButtonLabel: "Retry the last request",
         resultsInfoTitle: "Information",
         downloadButton: "Download .txt", downloadMdButton: "Download .md", downloadYamlButton: "Download .yaml", downloadTxtLabel: "Download digest as text file", downloadMdLabel: "Download digest as markdown file", downloadYamlLabel: "Download digest as YAML file",
         sourceLabel: "Source", videoCountSuffix: "video(s)", highQuotaCostBadge: "High API Cost",
         highCostWarning: "Warning: Search queries consume significant YouTube API resources (100 units per page of results). This may affect your daily usage limits.",
         confirmHighCost: "I understand, continue anyway", confirmHighCostLabel: "I understand the high cost warning, continue anyway",
         techDetailsTitle: "Technical Details", techDetailsTooltip: "Shows request processing time and estimated YouTube API usage.", processingTimeLabel: "Processing time:", apiCallsLabel: "YouTube API Calls:", apiQuotaLabel: "Estimated API Cost:", quotaUnits: "units", apiCallsShort: "calls", tokenCountSuffix: "tokens", tokenCountTooltip: "Number of tokens in the generated text (used for AI model cost estimation)",
         processingTimeBadgeTooltip: "Server processing time in milliseconds", apiCallsBadgeTooltip: "Number of YouTube API calls made for this request", apiQuotaBadgeTooltip: "Estimated YouTube API quota units used (100+ is high)",
         digestTitle: "Digest", digestTextAreaLabel: "Generated full digest", copyButton: "Copy", copyDigestLabel: "Copy digest to clipboard", increaseFontLabel: "Increase text size", decreaseFontLabel: "Decrease text size",
         historyModalTitle: "Search History", historyModalNoItems: "No items in history", historyModalClear: "Clear History", historyModalClose: "Close", closeHistoryModalLabel: "Close history modal", closeHistoryDialogLabel: "Close history dialog", clearHistoryLabel: "Clear all history items", historyItemUnknown: "Unknown Source",
         toastCopied: "Text copied", toastCopyFailed: "Copy failed", toastNothingToCopy: "Nothing to copy", toastDownloaded: "File downloaded", toastDownloadFailed: "Download failed", toastNoDigest: "No digest to download", toastZipDownloaded: "ZIP archive downloaded", toastZipFailed: "Failed to create ZIP archive", toastFontSize: "Font Size: {percent}%", toastHistoryCleared: "History cleared", toastEnterUrl: "Please enter a YouTube URL or search term.", dismissNotificationLabel: "Dismiss notification", datesSwapped: "Start date was after end date, they have been swapped.",
         footerInspired: "Frontend design inspired by", footerViewGithub: "View on GitHub", tipFontSize: "Tip: Use <kbd>Ctrl+↑/↓</kbd> or <kbd>⌘+↑/↓</kbd> to adjust text size.",
         footerThanks: "Thanks to <a href=\"https://aistudio.google.com/\" target=\"_blank\" rel=\"noopener\">Gemini 2.5 Pro</a>, <a href=\"https://claude.ai/\" target=\"_blank\" rel=\"noopener\">Claude 3.7 Sonnet</a>, <a href=\"https://www.augmentcode.com/\" target=\"_blank\" rel=\"noopener\">Augment Code</a> and <a href=\"https://zencoder.ai\" target=\"_blank\" rel=\"noopener\">ZenCoder</a>",
         buttonFeedbackCopied: "Copied!", buttonFeedbackDownloaded: "Downloaded!",
         errorQuotaExceeded: "YouTube API quota likely exceeded.", errorInvalidInput: "Invalid input provided.", errorNotFound: "Requested resource not found.", errorApiConfig: "API Configuration Error.", errorInternalServer: "Internal server error occurred.", errorServiceUnavailable: "Service temporarily unavailable.",
         suggestionQuota: "Try again later or check your API key quota.", suggestionInvalidInput: "Please check the entered URL or search term.", suggestionNotFound: "Verify the video/playlist/channel ID or search term.", suggestionApiConfig: "Check if the API key is valid and correctly configured.", digestEmpty: "Empty digest received.",
     },
     fr: {
         pageTitle: "Youtubingest", historyButton: "Historique", themeButton: "Thème", githubButton: "GitHub", historyButtonLabel: "Voir l'historique des requêtes", themeButtonLabel: "Basculer le mode sombre", switchToEnglish: "Passer en Anglais", switchToFrench: "Passer en Français",
         mainHeading1: "Adapté aux prompts", mainHeading2: "Youtube", mainDescription: "Transformez une vidéo, playlist, chaîne ou recherche YouTube<br class=\"hidden md-block\"> en texte optimisé pour les modèles de langage.",
         urlLabel: "URL YouTube ou terme de recherche", urlPlaceholder: "Entrez l'URL YouTube ou le terme de recherche ici", ingestButton: "Ingérer", ingestingButton: "Ingestion...",
         includeTranscriptLabel: "Inclure la transcription", includeTranscriptTooltip: "Récupérer et inclure la transcription de la vidéo si disponible.",
         includeDescriptionLabel: "Inclure la description", includeDescriptionTooltip: "Inclure le texte de la description de la vidéo dans le digest.",
         separateFilesLabel: "Fichier séparé par vidéo", separateFilesTooltip: "Créer un fichier séparé pour chaque vidéo (téléchargé sous forme d'archive ZIP).",
         transcriptIntervalLabel: "Intervalle de transcription (sec) :", transcriptIntervalTooltip: "Regrouper les lignes de transcription par intervalle de temps. 'Aucun' supprime les horodatages.", intervalOptionNone: "Aucun",
         startDateLabel: "Date de début :", startDateTooltip: "Inclure uniquement les vidéos publiées à partir de cette date.",
         endDateLabel: "Date de fin :", endDateTooltip: "Inclure uniquement les vidéos publiées jusqu'à cette date.",
         exampleSectionTitle: "Ou essayez ces exemples :", exampleVideo: "Vidéo simple", examplePlaylist: "Playlist courte", exampleChannel: "Chaîne (@Identifiant)", exampleSearch: "Recherche texte",
         exampleVideoLabel: "Essayer l'exemple : Vidéo simple", examplePlaylistLabel: "Essayer l'exemple : Playlist courte", exampleChannelLabel: "Essayer l'exemple : Chaîne (@Identifiant)", exampleSearchLabel: "Essayer l'exemple : Recherche texte",
         loadingInitializing: "Initialisation...", loadingFetching: "Récupération des informations...", loadingGenerating: "Génération du digest...", loadingMoment: "Cela peut prendre un moment...",
         errorTitle: "Erreur lors de l'ingestion", errorSuggestionPrefix: "Suggestion :", retryButton: "Réessayer", retryButtonLabel: "Réessayer la dernière requête",
         resultsInfoTitle: "Informations",
         downloadButton: "Télécharger .txt", downloadMdButton: "Télécharger .md", downloadYamlButton: "Télécharger .yaml", downloadTxtLabel: "Télécharger le digest en fichier texte", downloadMdLabel: "Télécharger le digest en fichier markdown", downloadYamlLabel: "Télécharger le digest en fichier YAML",
         sourceLabel: "Source", videoCountSuffix: "vidéo(s)", highQuotaCostBadge: "Coût API élevé",
         highCostWarning: "Attention : Les recherches par mots-clés consomment beaucoup de ressources YouTube (100 unités par page de résultats). Cela peut affecter votre limite quotidienne d'utilisation.",
         confirmHighCost: "J'ai compris, continuer quand même", confirmHighCostLabel: "J'ai compris l'avertissement de coût élevé, continuer quand même",
         techDetailsTitle: "Détails Techniques", techDetailsTooltip: "Affiche le temps de traitement de la requête et l'utilisation estimée de l'API YouTube.", processingTimeLabel: "Temps de traitement :", apiCallsLabel: "Appels API YouTube :", apiQuotaLabel: "Coût API estimé :", quotaUnits: "unités", apiCallsShort: "appels", tokenCountSuffix: "jetons", tokenCountTooltip: "Nombre de jetons dans le texte généré (utilisé pour estimer le coût des modèles d'IA)",
         processingTimeBadgeTooltip: "Temps de traitement côté serveur en millisecondes", apiCallsBadgeTooltip: "Nombre d'appels à l'API YouTube effectués pour cette requête", apiQuotaBadgeTooltip: "Unités de quota API YouTube estimées utilisées (100+ est élevé)",
         digestTitle: "Digest", digestTextAreaLabel: "Digest complet généré", copyButton: "Copier", copyDigestLabel: "Copier le digest dans le presse-papiers", increaseFontLabel: "Augmenter la taille du texte", decreaseFontLabel: "Diminuer la taille du texte",
         historyModalTitle: "Historique des recherches", historyModalNoItems: "Aucun élément dans l'historique", historyModalClear: "Vider l'historique", historyModalClose: "Fermer", closeHistoryModalLabel: "Fermer la modale d'historique", closeHistoryDialogLabel: "Fermer la boîte de dialogue de l'historique", clearHistoryLabel: "Vider tout l'historique", historyItemUnknown: "Source inconnue",
         toastCopied: "Texte copié", toastCopyFailed: "La copie a échoué", toastNothingToCopy: "Rien à copier", toastDownloaded: "Fichier téléchargé", toastDownloadFailed: "Le téléchargement a échoué", toastNoDigest: "Pas de digest à télécharger", toastZipDownloaded: "Archive ZIP téléchargée", toastZipFailed: "Échec de création de l'archive ZIP", toastFontSize: "Taille police : {percent}%", toastHistoryCleared: "Historique vidé", toastEnterUrl: "Veuillez entrer une URL YouTube ou un terme de recherche.", dismissNotificationLabel: "Fermer la notification", datesSwapped: "La date de début était après la date de fin, elles ont été inversées.",
         footerInspired: "Design frontend inspiré par", footerViewGithub: "Voir sur GitHub", tipFontSize: "Astuce : Utilisez <kbd>Ctrl+↑/↓</kbd> ou <kbd>⌘+↑/↓</kbd> pour ajuster la taille du texte.",
         footerThanks: "Merci à <a href=\"https://aistudio.google.com/\" target=\"_blank\" rel=\"noopener\">Gemini 2.5 Pro</a>, <a href=\"https://claude.ai/\" target=\"_blank\" rel=\"noopener\">Claude 3.7 Sonnet</a>, <a href=\"https://www.augmentcode.com/\" target=\"_blank\" rel=\"noopener\">Augment Code</a> et <a href=\"https://zencoder.ai\" target=\"_blank\" rel=\"noopener\">ZenCoder</a>",
         buttonFeedbackCopied: "Copié !", buttonFeedbackDownloaded: "Téléchargé !",
         errorQuotaExceeded: "Quota de l'API YouTube probablement dépassé.", errorInvalidInput: "Entrée invalide.", errorNotFound: "Ressource demandée non trouvée.", errorApiConfig: "Erreur de configuration de l'API.", errorInternalServer: "Erreur interne du serveur.", errorServiceUnavailable: "Service temporairement indisponible.",
         suggestionQuota: "Réessayez plus tard ou vérifiez le quota de votre clé API.", suggestionInvalidInput: "Veuillez vérifier l'URL ou le terme de recherche saisi.", suggestionNotFound: "Vérifiez l'ID de la vidéo/playlist/chaîne ou le terme de recherche.", suggestionApiConfig: "Vérifiez si la clé API est valide et correctement configurée.", digestEmpty: "Digest vide reçu.",
     }
 };

// --- I18N Helper Function ---
/**
 * Translates a given key using the current language.
 * @param {string} key - The translation key.
 * @param {object} [params={}] - Optional parameters for placeholder replacement.
 * @returns {string} The translated string or the key itself if not found.
 */
function _(key, params = {}) {
     let text = translations[appState.ui.currentLang]?.[key] ?? key;
     for (const pKey in params) {
         text = text.replace(`{${pKey}}`, params[pKey]);
     }
     return text;
 }

// --- Language Management ---
/**
 * Determines the initial language based on localStorage or browser settings.
 * @returns {string} The initial language code ('en' or 'fr').
 */
function getInitialLanguage() {
     const savedLang = localStorage.getItem('youtubingest_lang');
     if (savedLang && translations[savedLang]) return savedLang;
     const browserLang = navigator.language?.split('-')[0];
     if (browserLang && translations[browserLang]) return browserLang;
     return 'en'; // Default to English
 }

/**
 * Sets the application language and updates the UI.
 * @param {string} lang - The language code ('en' or 'fr').
 */
 function setLanguage(lang) {
     if (translations[lang]) {
         appState.ui.currentLang = lang;
         localStorage.setItem('youtubingest_lang', lang);
         updateUI();
         updateLangButtons();
         // Restore badge values after language change to ensure they reflect the last result
         // Use setTimeout to ensure DOM updates from updateUI() are likely complete
         setTimeout(restoreBadgeValues, 0);
     }
 }

/**
 * Updates the visual state of the language selection buttons.
 */
 function updateLangButtons() {
     if (!domElements.langButtons) return;
     domElements.langButtons.forEach(btn => {
         const btnLang = btn.getAttribute('data-lang');
         const isActive = (btnLang === appState.ui.currentLang);
         btn.disabled = isActive;
         btn.classList.toggle('is-active-lang', isActive);
         btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
     });
 }

// --- UI Update Function ---
/**
 * Updates all translatable text and attributes in the UI based on the current language.
 */
 function updateUI() {
     document.documentElement.setAttribute('lang', appState.ui.currentLang);
     document.title = _('pageTitle');

     // Update text content
     document.querySelectorAll('[data-translate]').forEach(el => {
         const key = el.getAttribute('data-translate');
         el.textContent = _(key);
     });

     // Update HTML content
     document.querySelectorAll('[data-translate-html]').forEach(el => {
         const key = el.getAttribute('data-translate-html');
         el.innerHTML = _(key);
     });

     // Update placeholders
     document.querySelectorAll('[data-translate-placeholder]').forEach(el => {
         const key = el.getAttribute('data-translate-placeholder');
         el.placeholder = _(key);
     });

    // Update aria-labels
     document.querySelectorAll('[data-translate-aria-label]').forEach(el => {
         const key = el.getAttribute('data-translate-aria-label');
         const currentAria = el.getAttribute('aria-label');
         const translated = _(key);
         if (translated !== key) {
            el.setAttribute('aria-label', translated);
         } else if (!currentAria && key) { // Set fallback if no label exists yet
            el.setAttribute('aria-label', key);
         }
     });

    // Update title attributes (tooltips)
      document.querySelectorAll('[data-translate-title]').forEach(el => {
         const key = el.getAttribute('data-translate-title');
          const currentTitle = el.title;
         const translated = _(key);
         if (translated !== key) {
            el.title = translated;
         } else if (!currentTitle && key) { // Set fallback if no title exists yet
            el.title = key;
         }
     });

     // Update dynamic parts like history list and results if they are visible
     updateHistoryList();
     if (domElements.resultsDiv && !domElements.resultsDiv.classList.contains('is-hidden') && appState.currentResult.metadata) {
         // Restore badge values specifically after language change
         restoreBadgeValues();
     }
     if (domElements.historyModal && domElements.historyModal.classList.contains('is-visible')) {
        // Update static modal texts if visible
        const modalTitle = domElements.historyModal.querySelector('#historyTitle');
        const clearBtn = domElements.historyModal.querySelector('#clearHistoryBtn');
        const closeBtn = domElements.historyModal.querySelector('#closeHistoryModalBtn');
        if(modalTitle) modalTitle.textContent = _('historyModalTitle');
        if(clearBtn) clearBtn.textContent = _('historyModalClear');
        if(closeBtn) closeBtn.textContent = _('historyModalClose');
     }
 }

// --- Dark Mode Functions ---
/**
 * Initializes dark mode based on localStorage or system preference.
 */
function initializeDarkMode() {
    const theme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    appState.ui.isDarkMode = (theme === 'dark' || (!theme && prefersDark));
    document.documentElement.classList.toggle('dark', appState.ui.isDarkMode);
}

/**
 * Toggles dark mode on/off and saves the preference.
 */
function toggleDarkMode() {
    appState.ui.isDarkMode = document.documentElement.classList.toggle('dark');
    localStorage.setItem('theme', appState.ui.isDarkMode ? 'dark' : 'light');
}

// --- Initialization ---
/**
 * Initializes the application on DOMContentLoaded.
 */
function initializeApp() {
    // Add class for initial animation control
    document.body.classList.add('initial-view');
    appState.ui.initialView = true;

    // Set language
    appState.ui.currentLang = getInitialLanguage();

    // Load history
    appState.history.items = loadHistoryFromStorage();

    // Initialize theme
    initializeDarkMode();

    // Set up event listeners
    setupEventListeners();

    // Update UI text
    updateUI();
    updateLangButtons();

    // Set footer year
    if(domElements.footerYear) domElements.footerYear.textContent = new Date().getFullYear();

    // Handle shared URL parameter on load
    handleUrlParameters();

    // Set initial font size for digest area
    adjustFontSize(0);
}

document.addEventListener('DOMContentLoaded', initializeApp);

// --- URL Parameter Handling ---
/**
 * Checks for and handles URL parameters (e.g., ?url=...) on load.
 */
function handleUrlParameters() {
    const urlParams = new URLSearchParams(window.location.search);
    const urlParam = urlParams.get('url');
    if (urlParam && domElements.urlInput) {
        domElements.urlInput.value = decodeURIComponent(urlParam);
        // Remove initial view class to prevent animation when loading from URL
        document.body.classList.remove('initial-view');
        appState.ui.initialView = false;
        // Auto-submit after a short delay
        setTimeout(() => {
            if (domElements.ingestForm) domElements.ingestForm.dispatchEvent(new Event('submit'));
        }, 200);
    } else {
         // Remove initial view class after animation duration if not loading from URL
         setTimeout(() => {
             document.body.classList.remove('initial-view');
             appState.ui.initialView = false;
         }, 1500); // Increased to match new animation duration (700ms + 400ms delay + 400ms buffer)
    }
}

// --- URL Pattern Detection ---
// Regular expression patterns for URL matching (same as backend, simple check here)
const URL_PATTERNS = {
    "video": /(?:youtube\.com\/(?:watch\?v=|embed\/|shorts\/)|youtu\.be\/)([a-zA-Z0-9_-]{11})/,
    "playlist": /youtube\.com\/(?:playlist|watch)\?.*?list=([a-zA-Z0-9_-]+)/,
    "channel_id": /youtube\.com\/channel\/(UC[a-zA-Z0-9_-]+)/,
    "channel_handle": /youtube\.com\/@([a-zA-Z0-9_.-]+)/,
    "channel_custom": /youtube\.com\/c\/([a-zA-Z0-9_.-]+)/,
    "channel_user": /youtube\.com\/user\/([a-zA-Z0-9_.-]+)/,
    "search_query_param": /youtube\.com\/results\?search_query=([^&]+)/,
};

/**
 * Checks if the input string is likely a search term rather than a URL.
 * @param {string} input - The input string to check.
 * @returns {boolean} True if likely a search term, false otherwise.
 */
function isLikelySearchTerm(input) {
    if (!input || typeof input !== 'string') return false;
    const cleaned = input.trim();
    if (!cleaned) return false;

    // Check if it matches any known YouTube URL pattern
    for (const pattern of Object.values(URL_PATTERNS)) {
        if (pattern.test(cleaned)) {
            return false; // It's a known YouTube URL
        }
    }

    // Basic check for general URL structure (presence of http://, https://, www., or domain.tld)
    const generalUrlPattern = /^(https?:\/\/|www\.)|\.[a-z]{2,}(\/|\?|$)/i;
    if (generalUrlPattern.test(cleaned)) {
        // It looks like a URL, but not a recognized YouTube one. Still treat as URL.
        return false;
    }

    // If none of the above, assume it's a search term
    return true;
}

// --- Event Listeners Setup ---
/**
 * Sets up all necessary event listeners for UI elements.
 */
function setupEventListeners() {
    if (domElements.ingestForm) domElements.ingestForm.addEventListener('submit', handleFormSubmit);
    if (domElements.exampleButtons) domElements.exampleButtons.forEach(button => button.addEventListener('click', handleExampleClick));

    // Listener for URL input to show/hide high cost warning
    if (domElements.urlInput) {
        domElements.urlInput.addEventListener('input', function() {
            const value = this.value.trim();
            const isSearch = isLikelySearchTerm(value);
            toggleElementVisibility(domElements.highCostWarning, isSearch);
            // Add/remove class to adjust spacing below the input group when warning is shown/hidden
            const formGroup = this.closest('.form-group');
             if (formGroup) formGroup.classList.toggle('has-warning', isSearch);
        });
    }

    // Listener for confirming high cost
    if (domElements.confirmHighCostButton) {
        domElements.confirmHighCostButton.addEventListener('click', function(e) {
            e.preventDefault(); // Prevent default button behavior
            toggleElementVisibility(domElements.highCostWarning, false); // Hide warning
            const formGroup = domElements.urlInput.closest('.form-group');
             if (formGroup) formGroup.classList.remove('has-warning'); // Remove spacing class
            if (domElements.ingestForm) domElements.ingestForm.dispatchEvent(new Event('submit')); // Manually trigger form submission
        });
    }

    if (domElements.darkModeToggle) domElements.darkModeToggle.addEventListener('click', toggleDarkMode);
    if (domElements.retryButton) domElements.retryButton.addEventListener('click', handleRetry);

    // Font size adjustment listeners
    if (domElements.increaseFontButton) domElements.increaseFontButton.addEventListener('click', () => adjustFontSize(0.1));
    if (domElements.decreaseFontButton) domElements.decreaseFontButton.addEventListener('click', () => adjustFontSize(-0.1));
    document.addEventListener('keydown', handleKeyboardShortcuts);

    // History modal listeners
    if (domElements.historyButton) domElements.historyButton.addEventListener('click', () => toggleHistoryModal(true));
    if (domElements.closeHistoryBtn) domElements.closeHistoryBtn.addEventListener('click', () => toggleHistoryModal(false));
    if (domElements.closeHistoryModalBtn) domElements.closeHistoryModalBtn.addEventListener('click', () => toggleHistoryModal(false));
    if (domElements.historyModal) domElements.historyModal.addEventListener('click', (e) => { if (e.target === domElements.historyModal) toggleHistoryModal(false); }); // Close on overlay click
    if (domElements.clearHistoryBtn) domElements.clearHistoryBtn.addEventListener('click', clearHistory);

    // Language button listeners
    if (domElements.langButtons) domElements.langButtons.forEach(button => {
         button.addEventListener('click', (e) => {
             const newLang = e.currentTarget.getAttribute('data-lang');
             setLanguage(newLang);
         });
     });

     // Download button listeners
     if (domElements.downloadTxtButton) domElements.downloadTxtButton.addEventListener('click', () => {
         downloadDigest('txt', domElements.downloadTxtButton);
     });
     if (domElements.downloadMdButton) domElements.downloadMdButton.addEventListener('click', () => {
         downloadDigest('md', domElements.downloadMdButton);
     });
     if (domElements.downloadYamlButton) domElements.downloadYamlButton.addEventListener('click', () => {
         downloadDigest('yaml', domElements.downloadYamlButton);
     });

     // Copy digest button listener (no longer inline)
     const copyDigestButton = document.getElementById('copyDigestButton');
     if (copyDigestButton) {
         copyDigestButton.addEventListener('click', () => copyToClipboard('digest', copyDigestButton));
     }
}

// --- Core Logic Functions ---

/**
 * Handles the submission of the main ingestion form.
 * @param {Event} event - The form submission event.
 */
async function handleFormSubmit(event) {
     event.preventDefault(); // Prevent default form submission
     if (appState.ui.initialView) { // Remove initial view class if submission happens before timeout
        document.body.classList.remove('initial-view');
        appState.ui.initialView = false;
     }

     // Ensure all required elements are available
     if (!domElements.urlInput || !domElements.includeTranscriptCheckbox || !domElements.includeDescriptionCheckbox || !domElements.separateFilesCheckbox || !domElements.transcriptIntervalSelect || !domElements.startDateInput || !domElements.endDateInput) {
         console.error("Form elements missing!");
         showToast("errorInternalServer", "error"); // Show generic error
         return;
     }

     const url = domElements.urlInput.value.trim();
     if (!url) {
         showToast("toastEnterUrl", "warning");
         return;
     }

     // Prevent submission if high cost warning is visible and not confirmed
     const isSearch = isLikelySearchTerm(url);
     if (isSearch && domElements.highCostWarning && !domElements.highCostWarning.classList.contains('is-hidden')) {
         // User needs to click the "Continue anyway" button first
         return;
     }

     const includeTranscript = domElements.includeTranscriptCheckbox.checked;
     const includeDescription = domElements.includeDescriptionCheckbox.checked;
     const separateFiles = domElements.separateFilesCheckbox.checked;
     const transcriptInterval = parseInt(domElements.transcriptIntervalSelect.value, 10); // NaN if 'None' selected originally (value="0"), which is handled backend

     // Validate and format date values
     let startDateValue = domElements.startDateInput.value || null;
     let endDateValue = domElements.endDateInput.value || null;

     // Basic date validation (YYYY-MM-DD)
     const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
     if (startDateValue && !dateRegex.test(startDateValue)) {
         console.warn("Invalid start date format, ignoring:", startDateValue);
         startDateValue = null;
         domElements.startDateInput.value = ''; // Clear invalid input
     }
     if (endDateValue && !dateRegex.test(endDateValue)) {
         console.warn("Invalid end date format, ignoring:", endDateValue);
         endDateValue = null;
         domElements.endDateInput.value = ''; // Clear invalid input
     }

     // Swap dates if start date is after end date
     if (startDateValue && endDateValue) {
         const startDate = new Date(startDateValue);
         const endDate = new Date(endDateValue);
         if (startDate > endDate) {
             [startDateValue, endDateValue] = [endDateValue, startDateValue];
             domElements.startDateInput.value = startDateValue; // Update UI
             domElements.endDateInput.value = endDateValue;   // Update UI
             showToast("datesSwapped", "warning");
         }
     }

     // Store current request parameters for potential retry
     appState.currentRequest.params = {
         url,
         include_transcript: includeTranscript,
         include_description: includeDescription,
         separate_files: separateFiles,
         transcript_interval: transcriptInterval,
         start_date: startDateValue,
         end_date: endDateValue
     };

     // Reset previous results
     appState.currentResult.metadata = null;
     appState.currentResult.processedVideos = [];
     appState.currentResult.digestText = '';
     appState.currentResult.badgeValues = { processingTimeMs: null, apiCallCount: null, apiQuotaUsed: null, tokenCount: null, highQuotaCost: false };

     // --- Start Loading State ---
     setLoadingState(true, "loadingInitializing");
     toggleElementVisibility(domElements.errorDiv, false);
     toggleElementVisibility(domElements.resultsDiv, false);
     toggleElementVisibility(domElements.fontSizeTip, false);
     toggleElementVisibility(domElements.loadingDiv, true);
     if(domElements.loadingDiv) domElements.loadingDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
     // --- End Loading State ---

     try {
         updateLoadingStatus("loadingFetching"); // Update status message

         // Fetch data from the backend API
         const response = await fetch('/ingest', {
             method: 'POST',
             headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
             body: JSON.stringify(appState.currentRequest.params)
         });

         updateLoadingStatus("loadingGenerating"); // Update status message

         if (!response.ok) {
             let errorData;
             try {
                 errorData = await response.json();
             } catch (parseError) {
                 errorData = { detail: `HTTP Error ${response.status}: ${response.statusText}`, error_code: `HTTP_${response.status}` };
             }
             // Map error code to translation keys for user-friendly messages
             const messageKey = mapErrorCodeToTranslationKey(errorData.error_code) || 'errorInternalServer'; // Fallback message
             const suggestionKey = mapErrorCodeToSuggestionKey(errorData.error_code);
             // Throw an error with structured data for the catch block
             throw new Error(messageKey, { cause: { ...errorData, suggestionKey } });
         }

         const responseData = await response.json();

         // Store data in appState
         appState.currentResult.metadata = responseData;
         appState.currentResult.processedVideos = responseData.videos || [];
         appState.currentResult.digestText = responseData.digest || _("digestEmpty");
         appState.currentRequest.sourceName = responseData.source_name || 'youtubingest_digest';

         // Store badge values immediately
         appState.currentResult.badgeValues.processingTimeMs = responseData.processing_time_ms;
         appState.currentResult.badgeValues.apiCallCount = responseData.api_call_count;
         appState.currentResult.badgeValues.apiQuotaUsed = responseData.api_quota_used;
         appState.currentResult.badgeValues.tokenCount = responseData.token_count;
         appState.currentResult.badgeValues.highQuotaCost = responseData.high_quota_cost || false;

         if (!responseData.videos) {
             console.warn("Backend response did not include a 'videos' array. MD/YAML formatting might be limited.");
         }

         displayResults(responseData);
         addToHistory(url, appState.currentRequest.sourceName);

         // Scroll to results after a short delay for smoother transition
         setTimeout(() => { if(domElements.resultsDiv) domElements.resultsDiv.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 100);

     } catch (error) {
         console.error("Ingestion Error:", error.cause?.detail || error.message); // Log original or fallback error
         const errorData = error.cause || {};
         // Use translated error message key from error object, or fallback
         const messageKey = error.message || 'errorInternalServer';
         displayError(messageKey, errorData.error_code, errorData.suggestionKey);
         // Scroll to error message
         setTimeout(() => { if(domElements.errorDiv) domElements.errorDiv.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, 100);
     } finally {
         setLoadingState(false); // Ensure loading state is reset regardless of outcome
     }
 }

/**
 * Maps backend error codes to user-facing translation keys.
 * @param {string} errorCode - The error code from the backend.
 * @returns {string|undefined} The corresponding translation key or undefined.
 */
function mapErrorCodeToTranslationKey(errorCode) {
    const mapping = {
        'QUOTA_EXCEEDED': 'errorQuotaExceeded', 'INVALID_INPUT': 'errorInvalidInput',
        'RESOURCE_NOT_FOUND': 'errorNotFound', 'API_CONFIG_ERROR': 'errorApiConfig',
        'INTERNAL_SERVER_ERROR': 'errorInternalServer', 'SERVICE_UNAVAILABLE': 'errorServiceUnavailable',
        // Add more mappings as needed
    };
    return mapping[errorCode];
}

/**
 * Maps backend error codes to suggestion translation keys.
 * @param {string} errorCode - The error code from the backend.
 * @returns {string|undefined} The corresponding suggestion key or undefined.
 */
function mapErrorCodeToSuggestionKey(errorCode) {
     const mapping = {
        'QUOTA_EXCEEDED': 'suggestionQuota', 'INVALID_INPUT': 'suggestionInvalidInput',
        'RESOURCE_NOT_FOUND': 'suggestionNotFound', 'API_CONFIG_ERROR': 'suggestionApiConfig',
        // Add more mappings as needed
    };
    return mapping[errorCode];
}

/**
 * Handles the retry button click by restoring the last request parameters and resubmitting.
 */
function handleRetry() {
     if (!appState.currentRequest.params) return; // No request to retry

     // Restore form fields from the stored parameters
     const params = appState.currentRequest.params;
     if(domElements.urlInput) domElements.urlInput.value = params.url;
     if(domElements.includeTranscriptCheckbox) domElements.includeTranscriptCheckbox.checked = params.include_transcript;
     if(domElements.includeDescriptionCheckbox) domElements.includeDescriptionCheckbox.checked = params.include_description;
     if(domElements.separateFilesCheckbox) domElements.separateFilesCheckbox.checked = params.separate_files;
     if(domElements.transcriptIntervalSelect) domElements.transcriptIntervalSelect.value = params.transcript_interval ?? 0; // Default to 0 ('None') if null/undefined
     if(domElements.startDateInput) domElements.startDateInput.value = params.start_date || '';
     if(domElements.endDateInput) domElements.endDateInput.value = params.end_date || '';

     // Resubmit the form
     if(domElements.ingestForm) domElements.ingestForm.dispatchEvent(new Event('submit'));
}

/**
 * Handles clicks on example buttons to populate the URL field and potentially submit.
 * @param {Event} event - The click event.
 */
function handleExampleClick(event) {
    const exampleUrl = event.currentTarget.getAttribute('data-example-url');
    if (exampleUrl && domElements.urlInput) {
        domElements.urlInput.value = exampleUrl;
        // Reset date filters when using examples for simplicity
        if(domElements.startDateInput) domElements.startDateInput.value = '';
        if(domElements.endDateInput) domElements.endDateInput.value = '';
        domElements.urlInput.focus();

        // Trigger input event to check for high-cost warning
        domElements.urlInput.dispatchEvent(new Event('input', { bubbles: true }));

        // If it's NOT a search term (i.e., a direct URL example), submit immediately
        if (!isLikelySearchTerm(exampleUrl)) {
            setTimeout(() => {
                if(domElements.ingestForm) domElements.ingestForm.dispatchEvent(new Event('submit'));
            }, 100);
        }
        // If it IS a search term, the user must manually click "Ingest" or "Continue anyway"
    }
}

/**
 * Handles keyboard shortcuts, specifically Ctrl/Cmd + Up/Down for font size.
 * @param {KeyboardEvent} event - The keydown event.
 */
function handleKeyboardShortcuts(event) {
     // Check if the focus is inside the digest textarea or its controls
     const activeElement = document.activeElement;
     const isInDigestContext = domElements.digestTextarea?.contains(activeElement) ||
                              domElements.increaseFontButton?.contains(activeElement) ||
                              domElements.decreaseFontButton?.contains(activeElement) ||
                              domElements.digestTextarea === activeElement; // Check textarea itself

     if (isInDigestContext && (event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey) {
         if (event.key === 'ArrowUp') {
             event.preventDefault();
             adjustFontSize(0.1);
         } else if (event.key === 'ArrowDown') {
             event.preventDefault();
             adjustFontSize(-0.1);
         }
     }
}

// --- UI Update Functions ---

/**
 * Sets the loading state of the application (e.g., disabling submit button).
 * @param {boolean} isLoading - Whether the application is entering loading state.
 * @param {string} [initialMessageKey="loadingInitializing"] - Translation key for the initial loading message.
 */
function setLoadingState(isLoading, initialMessageKey = "loadingInitializing") {
    appState.ui.isLoading = isLoading;
    if(domElements.submitButton) domElements.submitButton.disabled = isLoading;

    const buttonText = domElements.submitButton?.querySelector('.button-text');
    const buttonLoader = domElements.submitButton?.querySelector('.button-loader');

    if(buttonText) toggleElementVisibility(buttonText, !isLoading);
    if (buttonLoader) {
       toggleElementVisibility(buttonLoader, isLoading);
       buttonLoader.style.display = isLoading ? 'inline-flex' : 'none'; // Ensure correct display type
    }

    // Update loading text only when entering loading state
    if (isLoading && domElements.loadingStatusP) {
       domElements.loadingStatusP.textContent = _(initialMessageKey);
       const subtext = domElements.loadingStatusP.nextElementSibling;
       if (subtext) subtext.textContent = _("loadingMoment");
    }
}

/**
 * Updates the text displayed in the loading indicator.
 * @param {string} messageKey - The translation key for the loading status message.
 */
function updateLoadingStatus(messageKey) {
    if (domElements.loadingStatusP) {
        domElements.loadingStatusP.textContent = _(messageKey);
    }
}

/**
 * Displays an error message in the UI.
 * @param {string} messageKey - Translation key for the main error message.
 * @param {string|null} [code=null] - Optional error code to display.
 * @param {string|null} [suggestionKey=null] - Optional translation key for a suggested action.
 */
function displayError(messageKey, code = null, suggestionKey = null) {
    if(domElements.errorMessageSpan) domElements.errorMessageSpan.textContent = _(messageKey);

    toggleElementVisibility(domElements.errorCodeSpan, !!code);
    if(code && domElements.errorCodeSpan) domElements.errorCodeSpan.textContent = `Code: ${code}`;

    const hasSuggestion = !!(suggestionKey && _(suggestionKey) !== suggestionKey); // Check if suggestion key exists and translates
    toggleElementVisibility(domElements.errorSuggestionP, hasSuggestion);
    if(hasSuggestion && domElements.errorSuggestionP) {
        domElements.errorSuggestionP.textContent = `${_("errorSuggestionPrefix")} ${_(suggestionKey)}`;
    } else if (domElements.errorSuggestionP) {
         domElements.errorSuggestionP.textContent = ''; // Clear if no suggestion
    }

    toggleElementVisibility(domElements.errorDiv, true);
    toggleElementVisibility(domElements.resultsDiv, false); // Hide results on error
    toggleElementVisibility(domElements.fontSizeTip, false); // Hide font tip on error
    toggleElementVisibility(domElements.loadingDiv, false); // Ensure loading is hidden
}

/**
 * Displays the successful ingestion results in the UI.
 * @param {object} data - The response data object from the backend.
 */
function displayResults(data) {
    // Source Info
    updateSourceInfo(appState.currentRequest.sourceName, data.video_count);

    // Badges (using stored values in appState.currentResult.badgeValues)
    toggleElementVisibility(domElements.highQuotaCostBadge, !!appState.currentResult.badgeValues.highQuotaCost);
    updateStatsInfoBadges(); // Update badges based on stored state

    // Digest Text Area
    const sanitizedDigest = sanitizeText(appState.currentResult.digestText); // Sanitize before display
    if(domElements.digestTextarea) domElements.digestTextarea.value = sanitizedDigest;
    adjustFontSize(0); // Ensure font size is reset/correctly applied

    // Visibility
    toggleElementVisibility(domElements.resultsDiv, true);
    toggleElementVisibility(domElements.errorDiv, false);
    toggleElementVisibility(domElements.fontSizeTip, true);
    toggleElementVisibility(domElements.loadingDiv, false); // Ensure loading is hidden

    // Enable/Disable Download Buttons
    const hasDigest = !!(sanitizedDigest && sanitizedDigest.trim() && sanitizedDigest !== _("digestEmpty"));
    const hasStructuredData = !!(appState.currentResult.processedVideos && appState.currentResult.processedVideos.length > 0);
    if(domElements.downloadTxtButton) domElements.downloadTxtButton.disabled = !hasDigest;
    if(domElements.downloadMdButton) domElements.downloadMdButton.disabled = !hasStructuredData;
    if(domElements.downloadYamlButton) domElements.downloadYamlButton.disabled = !hasStructuredData;
}

/**
 * Updates the source name and video count display.
 * @param {string} sourceName - The name of the source (channel, playlist, etc.).
 * @param {number} videoCount - The number of videos processed.
 */
function updateSourceInfo(sourceName, videoCount) {
    const sanitizedSourceName = sanitizeText(sourceName || _('historyItemUnknown'));
    const sanitizedVideoCount = videoCount !== null ? String(videoCount) : '0';

    if(domElements.sourceNameElement) domElements.sourceNameElement.textContent = sanitizedSourceName;
    if(domElements.videoCountElement) domElements.videoCountElement.textContent = sanitizedVideoCount;
}

/**
 * Updates the technical detail badges based on stored state.
 */
function updateStatsInfoBadges() {
    const badges = appState.currentResult.badgeValues;
    console.log("Updating badges with stored values:", badges);

    // Update badge values
    if(domElements.processingTimeValueElement) domElements.processingTimeValueElement.textContent = formatNumber(badges.processingTimeMs);
    if(domElements.apiCallsValueElement) domElements.apiCallsValueElement.textContent = formatNumber(badges.apiCallCount); // Use formatNumber for consistency with 'null' -> '--'
    if(domElements.apiQuotaValueElement) domElements.apiQuotaValueElement.textContent = formatNumber(badges.apiQuotaUsed);
    if(domElements.tokenCountValueElement) domElements.tokenCountValueElement.textContent = formatNumber(badges.tokenCount);

    // Update badge suffixes (in case of language change)
    if(domElements.apiCallsSuffixElement) domElements.apiCallsSuffixElement.textContent = _('apiCallsShort');
    if(domElements.apiQuotaSuffixElement) domElements.apiQuotaSuffixElement.textContent = _('quotaUnits');
    if(domElements.tokenCountSuffixElement) domElements.tokenCountSuffixElement.textContent = _('tokenCountSuffix');

    // Update API Quota badge style
    const apiQuotaBadgeElement = document.getElementById('apiQuotaBadge');
    if(apiQuotaBadgeElement) {
        const isHighQuota = badges.apiQuotaUsed !== null && badges.apiQuotaUsed >= 100;
        apiQuotaBadgeElement.classList.toggle('badge-danger', isHighQuota);
        apiQuotaBadgeElement.classList.toggle('badge-info', !isHighQuota);
    }

    // Ensure badges are visible (they might be hidden initially or by errors)
    const processingTimeBadge = document.getElementById('processingTimeBadge');
    const apiCallsBadge = document.getElementById('apiCallsBadge');
    const tokenCountBadge = document.getElementById('tokenCountBadge');
    if(processingTimeBadge) toggleElementVisibility(processingTimeBadge, true);
    if(apiCallsBadge) toggleElementVisibility(apiCallsBadge, true);
    if(apiQuotaBadgeElement) toggleElementVisibility(apiQuotaBadgeElement, true);
    if(tokenCountBadge) toggleElementVisibility(tokenCountBadge, true);

    // Update legacy elements if they still exist (for safety, can be removed later)
    if(domElements.processingTimeElement) domElements.processingTimeElement.textContent = `${_('processingTimeLabel')} ${formatNumber(badges.processingTimeMs)} ms`;
    if(domElements.apiCallsElement) domElements.apiCallsElement.textContent = `${_('apiCallsLabel')} ${formatNumber(badges.apiCallCount)}`;
    if(domElements.apiQuotaElement) domElements.apiQuotaElement.textContent = `${_('apiQuotaLabel')} ${formatNumber(badges.apiQuotaUsed)} ${_('quotaUnits')}`;
}


/**
 * Restores badge values after a language change, using the centrally stored state.
 */
function restoreBadgeValues() {
    // Only restore if results are currently displayed
    if (domElements.resultsDiv && !domElements.resultsDiv.classList.contains('is-hidden') && appState.currentResult.metadata) {
        console.log("Restoring badge values after language change.");
        updateStatsInfoBadges();
    }
}


// --- Utility Functions ---

/**
 * Formats a number for display, handling null/undefined.
 * @param {number|null|undefined} num - The number to format.
 * @returns {string} The formatted number or '--'.
 */
function formatNumber(num) {
    if (num === null || num === undefined) return '--';
    try {
        // Use 'en-US' locale for consistent number formatting regardless of UI language
        return new Intl.NumberFormat('en-US').format(num);
    } catch (e) {
        console.warn("Number formatting failed:", e);
        return String(num); // Fallback to simple string conversion
    }
}

/**
 * Toggles the visibility of a DOM element using a 'is-hidden' class.
 * @param {Element|null} el - The DOM element.
 * @param {boolean} show - True to show, false to hide.
 */
function toggleElementVisibility(el, show) {
    if (el) {
        el.classList.toggle('is-hidden', !show);
    }
}

/**
 * Simple sleep function using Promises.
 * @param {number} ms - Milliseconds to sleep.
 * @returns {Promise<void>}
 */
function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Sanitizes text by setting it as textContent of a temporary element.
 * This prevents basic HTML injection.
 * @param {string} text - The input text.
 * @returns {string} The sanitized text.
 */
function sanitizeText(text) {
    if (!text || typeof text !== 'string') return '';
    const temp = document.createElement('div');
    temp.textContent = text;
    return temp.textContent;
}


/**
 * Formats an ISO 8601 date string for display (YYYY-MM-DD HH:MM:SS UTC).
 * @param {string} isoDateString - The ISO date string.
 * @returns {string} Formatted date string or 'N/A'.
 */
function formatDateForDisplay(isoDateString) {
    if (!isoDateString) return 'N/A';
    try {
        const date = new Date(isoDateString);
        if (isNaN(date.getTime())) return isoDateString; // Return original if invalid
        // Format as YYYY-MM-DD HH:MM:SS UTC
        const year = date.getUTCFullYear();
        const month = String(date.getUTCMonth() + 1).padStart(2, '0');
        const day = String(date.getUTCDate()).padStart(2, '0');
        const hours = String(date.getUTCHours()).padStart(2, '0');
        const minutes = String(date.getUTCMinutes()).padStart(2, '0');
        const seconds = String(date.getUTCSeconds()).padStart(2, '0');
        return `${year}-${month}-${day} ${hours}:${minutes}:${seconds} UTC`;
    } catch (e) {
        console.warn("Date formatting error:", e);
        return isoDateString; // Fallback
    }
}

/**
 * Formats an ISO 8601 duration string (PTnHnMnS) into H:MM:SS or M:SS.
 * @param {string} isoDuration - The ISO duration string.
 * @returns {string} Formatted duration string or 'N/A'.
 */
function formatDurationForDisplay(isoDuration) {
    if (!isoDuration || !isoDuration.startsWith("PT")) return 'N/A';
    try {
        let timeStr = isoDuration.substring(2);
        let hours = 0, minutes = 0, seconds = 0;
        const hoursMatch = timeStr.match(/(\d+)H/);
        if (hoursMatch) { hours = parseInt(hoursMatch[1]); timeStr = timeStr.replace(hoursMatch[0], ''); }
        const minutesMatch = timeStr.match(/(\d+)M/);
        if (minutesMatch) { minutes = parseInt(minutesMatch[1]); timeStr = timeStr.replace(minutesMatch[0], ''); }
        const secondsMatch = timeStr.match(/(\d+)S/);
        if (secondsMatch) { seconds = parseInt(secondsMatch[1]); }

        if (hours > 0) {
            return `${hours}:${String(minutes).padStart(2,'0')}:${String(seconds).padStart(2,'0')}`; // H:MM:SS
        } else {
            return `${minutes}:${String(seconds).padStart(2,'0')}`; // M:SS
        }
    } catch (e) {
        console.warn("Duration formatting error:", e);
        return isoDuration; // Fallback
    }
}

/**
 * Copies text content of a given element ID to the clipboard.
 * @param {string} elementId - The ID of the element containing the text.
 * @param {Element} buttonElement - The button that triggered the copy action (for feedback).
 */
function copyToClipboard(elementId, buttonElement) {
    const element = document.getElementById(elementId);
    if (!element) return;
    const textToCopy = (element.value !== undefined) ? element.value : element.textContent; // Handle textarea/input and other elements

    if (!textToCopy || !textToCopy.trim()) {
        showToast("toastNothingToCopy", "warning");
        return;
    }

    navigator.clipboard.writeText(textToCopy).then(() => {
        showButtonFeedback(buttonElement, 'buttonFeedbackCopied'); // Show visual feedback
        // showToast("toastCopied", "success"); // Feedback on button is usually enough
    }).catch(err => {
        console.error('Clipboard copy error:', err);
        showToast("toastCopyFailed", "error");
    });
}

/**
 * Downloads the current digest as a file.
 * @param {string} format - The format to download ('md', 'txt', 'yaml').
 * @param {Element} buttonElement - The button that triggered the download (for feedback).
 */
function downloadDigest(format, buttonElement) {
    if (!appState.currentResult.processedVideos || appState.currentResult.processedVideos.length === 0) {
        showToast("toastNoDigest", "warning");
        return;
    }

    try {
        // Check if we need to create separate files
        const separateFiles = domElements.separateFilesCheckbox && domElements.separateFilesCheckbox.checked;

        if (separateFiles) {
            downloadSeparateFiles(format, buttonElement);
        } else {
            downloadSingleFile(format, buttonElement);
        }
    } catch (error) {
        console.error("Download error:", error);
        showToast("toastDownloadFailed", "error");
    }
}

/**
 * Downloads all videos as separate files in a ZIP archive.
 * @param {string} format - The format to download ('md', 'txt', 'yaml').
 * @param {Element} buttonElement - The button that triggered the download (for feedback).
 */
async function downloadSeparateFiles(format, buttonElement) {
    try {
        // Dynamically import JSZip library
        if (typeof JSZip === 'undefined') {
            // If JSZip is not already loaded, create a script element to load it
            await new Promise((resolve, reject) => {
                const script = document.createElement('script');
                script.src = 'https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js';
                script.integrity = 'sha512-XMVd28F1oH/O71fzwBnV7HucLxVwtxf26XV8P4wPk26EDxuGZ91N8bsOttmnomcCD3CS5ZMRL50H0GgOHvegtg==';
                script.crossOrigin = 'anonymous';
                script.onload = resolve;
                script.onerror = reject;
                document.head.appendChild(script);
            });
        }

        // Create a new JSZip instance
        const zip = new JSZip();
        let extension, mimeType;
        const includeDescription = domElements.includeDescriptionCheckbox && domElements.includeDescriptionCheckbox.checked;

        // Set format-specific variables
        switch (format.toLowerCase()) {
            case 'md':
                extension = '.md';
                mimeType = 'text/markdown';
                break;
            case 'yaml':
                extension = '.yaml';
                mimeType = 'application/x-yaml';
                break;
            case 'txt':
            default:
                extension = '.txt';
                mimeType = 'text/plain';
                break;
        }

        // Add each video as a separate file to the ZIP
        for (const video of appState.currentResult.processedVideos) {
            let content;

            // Format content based on the selected format
            if (format.toLowerCase() === 'md') {
                content = formatVideoAsMarkdown(video, includeDescription);
            } else if (format.toLowerCase() === 'yaml') {
                content = formatVideoAsYAML(video, includeDescription);
            } else {
                content = formatVideoAsText(video, includeDescription);
            }

            const filename = generateVideoFilename(video, extension);
            zip.file(filename, content);
        }

        // Generate the ZIP file
        const zipBlob = await zip.generateAsync({ type: 'blob' });

        // Create a filename for the ZIP
        const zipFilename = generateFilename('.zip');

        // Create a temporary anchor element and trigger download
        const a = document.createElement('a');
        a.href = URL.createObjectURL(zipBlob);
        a.download = zipFilename;
        document.body.appendChild(a);
        a.click();

        // Clean up
        setTimeout(() => {
            document.body.removeChild(a);
            URL.revokeObjectURL(a.href);
        }, 100);

        showButtonFeedback(buttonElement, 'buttonFeedbackDownloaded');
        showToast("toastZipDownloaded", "success");
    } catch (error) {
        console.error("ZIP creation error:", error);
        showToast("toastZipFailed", "error");
    }
}

/**
 * Downloads all videos as a single file.
 * @param {string} format - The format to download ('md', 'txt', 'yaml').
 * @param {Element} buttonElement - The button that triggered the download (for feedback).
 */
function downloadSingleFile(format, buttonElement) {
    let content, extension, mimeType;
    const includeDescription = domElements.includeDescriptionCheckbox && domElements.includeDescriptionCheckbox.checked;

    switch (format.toLowerCase()) {
        case 'md':
            content = formatAsMarkdown(appState.currentResult.processedVideos, includeDescription);
            extension = '.md';
            mimeType = 'text/markdown';
            break;
        case 'yaml':
            content = formatAsYamlStructured(appState.currentResult.metadata, appState.currentResult.processedVideos, includeDescription);
            extension = '.yaml';
            mimeType = 'application/x-yaml';
            break;
        case 'txt':
        default:
            content = appState.currentResult.digestText;
            extension = '.txt';
            mimeType = 'text/plain';
            break;
    }

    const filename = generateFilename(extension);
    downloadFile(content, filename, mimeType, buttonElement);
}

/**
 * Triggers a browser download for the given content.
 * @param {string} content - The text content to download.
 * @param {string} filename - The desired filename.
 * @param {string} mimeType - The MIME type of the file.
 * @param {Element} buttonElement - The button that triggered the download (for feedback).
 */
function downloadFile(content, filename, mimeType, buttonElement) {
    if (!content) {
        showToast("toastNoDigest", "warning");
        return;
    }
    try {
        const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.style.display = 'none'; // Hide the link
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a); // Clean up the link element
        URL.revokeObjectURL(url);   // Free up memory
        showButtonFeedback(buttonElement, 'buttonFeedbackDownloaded'); // Show visual feedback
        showToast("toastDownloaded", "success");
    } catch (e) {
        console.error("Download error:", e);
        showToast("toastDownloadFailed", "error");
    }
}

/**
 * Generates a sanitized filename based on the current source name and extension.
 * @param {string} extension - The file extension (e.g., '.txt', '.md').
 * @returns {string} A sanitized filename.
 */
function generateFilename(extension) {
    // Use source name from state, remove filter count, trim, and sanitize
    let cleanSourceName = (appState.currentRequest.sourceName || 'youtubingest')
        .replace(/\s*\(\d+\s*filter\(s\)\)/, '') // Remove filter count like "(2 filter(s))"
        .trim();

    const safeSourceName = cleanSourceName
        .replace(/[^a-z0-9_\-\.]/gi, '_') // Replace invalid chars with underscore
        .replace(/_{2,}/g, '_')          // Collapse multiple underscores
        .replace(/^_|_$/g, '');          // Trim leading/trailing underscores

    // Ensure filename isn't empty after sanitization
    const finalName = safeSourceName || 'youtubingest';

    return `${finalName}_digest${extension}`;
}

/**
 * Generates a sanitized filename for an individual video based on its publication date and title.
 * Format: {date_publication_YYYYMMDD}_{video_title}.extension
 * @param {Object} video - The video object containing metadata.
 * @param {string} extension - The file extension (e.g., '.txt', '.md').
 * @returns {string} A sanitized filename.
 */
function generateVideoFilename(video, extension) {
    // Extract publication date and format as YYYYMMDD
    let datePrefix = 'unknown_date';
    if (video?.snippet?.publishedAt) {
        const publishDate = new Date(video.snippet.publishedAt);
        if (!isNaN(publishDate.getTime())) {
            const year = publishDate.getUTCFullYear();
            const month = String(publishDate.getUTCMonth() + 1).padStart(2, '0');
            const day = String(publishDate.getUTCDate()).padStart(2, '0');
            datePrefix = `${year}${month}${day}`;
        }
    }

    // Extract and sanitize video title
    let title = video?.snippet?.title || 'untitled_video';
    const safeTitle = title
        .replace(/[^a-z0-9_\-\.]/gi, '_') // Replace invalid chars with underscore
        .replace(/_{2,}/g, '_')          // Collapse multiple underscores
        .replace(/^_|_$/g, '')           // Trim leading/trailing underscores
        .substring(0, 50);               // Limit length to avoid excessively long filenames

    return `${datePrefix}_${safeTitle}${extension}`;
}

// --- Formatting Functions (Text, Markdown, YAML) ---

/**
 * Formats a single video as text.
 * @param {Object} video - The video object.
 * @param {boolean} includeDescription - Whether to include the description.
 * @returns {string} The formatted text.
 */
function formatVideoAsText(video, includeDescription) {
    if (!video) return '';

    // Safely access properties using optional chaining
    const title = video?.snippet?.title || 'Untitled Video';
    const videoId = video?.id || '';
    const url = videoId ? `https://youtu.be/${videoId}` : '#'; // Use shortlink
    const channelTitle = video?.snippet?.channelTitle || 'N/A';
    const channelId = video?.snippet?.channelId || '';
    const channelUrl = channelId ? `https://www.youtube.com/channel/${channelId}` : '#';
    const publishedAtISO = video?.snippet?.publishedAt || '';
    const publishedAtFormatted = formatDateForDisplay(publishedAtISO); // Format for display
    const durationISO = video?.contentDetails?.duration || '';
    const durationFormatted = formatDurationForDisplay(durationISO); // Format for display
    const tags = video?.snippet?.tags && video.snippet.tags.length ? video.snippet.tags.join(', ') : 'None';
    const description = video?.snippet?.description || '';
    const transcriptText = video?.transcript?.transcript || '';
    const transcriptLang = video?.transcript?.language || 'N/A';

    let textString = `${title}\n`;
    textString += `URL: ${url}\n`;
    textString += `Channel: ${channelTitle} (${channelUrl})\n`;
    textString += `Published: ${publishedAtFormatted}\n`;
    textString += `Duration: ${durationFormatted}\n`;
    textString += `Tags: ${tags}\n\n`;

    if (includeDescription && description) {
        textString += `Description:\n${description.trim()}\n\n`;
    }

    if (transcriptText) {
        textString += `Transcript (${transcriptLang}):\n${transcriptText.trim()}\n\n`;
    }

    return textString;
}

/**
 * Formats a single video as Markdown.
 * @param {Object} video - The video object.
 * @param {boolean} includeDescription - Whether to include the description.
 * @returns {string} The formatted Markdown.
 */
function formatVideoAsMarkdown(video, includeDescription) {
    if (!video) return '# No video data available';

    // Safely access properties using optional chaining
    const title = video?.snippet?.title || 'Untitled Video';
    const videoId = video?.id || '';
    const url = videoId ? `https://youtu.be/${videoId}` : '#'; // Use shortlink
    const channelTitle = video?.snippet?.channelTitle || 'N/A';
    const channelId = video?.snippet?.channelId || '';
    const channelUrl = channelId ? `https://www.youtube.com/channel/${channelId}` : '#';
    const publishedAtISO = video?.snippet?.publishedAt || '';
    const publishedAtFormatted = formatDateForDisplay(publishedAtISO); // Format for display
    const durationISO = video?.contentDetails?.duration || '';
    const durationFormatted = formatDurationForDisplay(durationISO); // Format for display
    const tags = video?.snippet?.tags && video.snippet.tags.length ? video.snippet.tags.join(', ') : 'None';
    const description = video?.snippet?.description || '';
    const transcriptText = video?.transcript?.transcript || '';
    const transcriptLang = video?.transcript?.language || 'N/A';

    let mdString = `# ${title}\n\n`;
    mdString += `* **URL:** <${url}>\n`;
    mdString += `* **Channel:** ${channelTitle} (<${channelUrl}>)\n`;
    mdString += `* **Published:** ${publishedAtFormatted}\n`; // Use formatted date
    mdString += `* **Duration:** ${durationFormatted}\n`;     // Use formatted duration
    mdString += `* **Tags:** ${tags}\n\n`;

    if (includeDescription && description) {
        mdString += `**Description:**\n\n${description.trim()}\n\n`;
    }

    if (transcriptText) {
        mdString += `**Transcript (${transcriptLang}):**\n\n\`\`\`\n${transcriptText.trim()}\n\`\`\`\n\n`;
    }

    return mdString;
}

/**
 * Formats a single video as YAML.
 * @param {Object} video - The video object.
 * @param {boolean} includeDescription - Whether to include the description.
 * @returns {string} The formatted YAML.
 */
function formatVideoAsYAML(video, includeDescription) {
    if (!video) return 'video: null';

    // Safely access properties
    const videoId = video?.id || '';
    const title = video?.snippet?.title || 'Untitled Video';
    const url = videoId ? `https://youtu.be/${videoId}` : '';
    const channelTitle = video?.snippet?.channelTitle || 'N/A';
    const channelId = video?.snippet?.channelId || '';
    const channelUrl = channelId ? `https://www.youtube.com/channel/${channelId}` : '';
    const publishedAtISO = video?.snippet?.publishedAt || ''; // Keep ISO format
    const durationISO = video?.contentDetails?.duration || ''; // Keep ISO format
    const tags = video?.snippet?.tags || [];
    const description = video?.snippet?.description || '';
    const transcriptText = video?.transcript?.transcript || '';
    const transcriptLang = video?.transcript?.language || '';

    let yamlString = `id: ${escapeYamlString(videoId)}\n`;
    yamlString += `title: ${escapeYamlString(title)}\n`;
    yamlString += `url: ${escapeYamlString(url)}\n`;
    yamlString += `channel_name: ${escapeYamlString(channelTitle)}\n`;
    yamlString += `channel_url: ${escapeYamlString(channelUrl)}\n`;
    yamlString += `published_at_iso8601: ${escapeYamlString(publishedAtISO)}\n`; // Keep ISO
    yamlString += `duration_iso8601: ${escapeYamlString(durationISO)}\n`; // Keep ISO

    // Format tags as YAML list
    if (tags.length > 0) {
        yamlString += 'tags:\n';
        tags.forEach(tag => {
            yamlString += `  - ${escapeYamlString(tag)}\n`;
        });
    } else {
        yamlString += 'tags: []\n'; // Empty list
    }

    // Add description using literal block scalar (|) if included
    if (includeDescription) {
        yamlString += 'description: |\n';
        yamlString += indentYamlBlockScalar(description.trim(), '  ') + '\n';
    } else {
        yamlString += 'description: null\n'; // Use null if not included
    }

    // Add transcript if available
    if (transcriptText) {
        yamlString += 'transcript:\n';
        yamlString += `  language: ${escapeYamlString(transcriptLang)}\n`;
        yamlString += '  text: |\n'; // Literal block scalar
        yamlString += indentYamlBlockScalar(transcriptText.trim(), '    ') + '\n'; // Indent under text:
    } else {
        yamlString += 'transcript: null\n'; // Use null if no transcript
    }

    return yamlString;
}

/**
 * Formats processed video data into a Markdown string.
 * @param {Array} videos - Array of video data objects from appState.currentResult.processedVideos.
 * @param {boolean} includeDescription - Whether to include the video description.
 * @returns {string} The formatted Markdown string.
 */
function formatAsMarkdown(videos, includeDescription) {
    if (!videos || videos.length === 0) {
        return `# No video data available for Markdown export.\n\nCheck if the backend response included the 'videos' array.`;
    }

    const sourceName = appState.currentResult.metadata?.source_name || 'YouTube Content';
    let mdString = `# ${sourceName}\n\n`;

    videos.forEach((video, index) => {
        // Safely access properties using optional chaining
        const title = video?.snippet?.title || 'Untitled Video';
        const videoId = video?.id || '';
        const url = videoId ? `https://youtu.be/${videoId}` : '#'; // Use shortlink
        const channelTitle = video?.snippet?.channelTitle || 'N/A';
        const channelId = video?.snippet?.channelId || '';
        const channelUrl = channelId ? `https://www.youtube.com/channel/${channelId}` : '#';
        const publishedAtISO = video?.snippet?.publishedAt || '';
        const publishedAtFormatted = formatDateForDisplay(publishedAtISO); // Format for display
        const durationISO = video?.contentDetails?.duration || '';
        const durationFormatted = formatDurationForDisplay(durationISO); // Format for display
        const tags = video?.snippet?.tags && video.snippet.tags.length ? video.snippet.tags.join(', ') : 'None';
        const description = video?.snippet?.description || '';
        const transcriptText = video?.transcript?.transcript || '';
        const transcriptLang = video?.transcript?.language || 'N/A';

        mdString += `## ${title}\n\n`;
        mdString += `* **URL:** <${url}>\n`;
        mdString += `* **Channel:** ${channelTitle} (<${channelUrl}>)\n`;
        mdString += `* **Published:** ${publishedAtFormatted}\n`; // Use formatted date
        mdString += `* **Duration:** ${durationFormatted}\n`;     // Use formatted duration
        mdString += `* **Tags:** ${tags}\n\n`;

        if (includeDescription && description) {
            mdString += `**Description:**\n\n${description.trim()}\n\n`;
        }

        if (transcriptText) {
            mdString += `**Transcript (${transcriptLang}):**\n\n\`\`\`\n${transcriptText.trim()}\n\`\`\`\n\n`;
        }

        if (index < videos.length - 1) {
            mdString += "---\n\n"; // Separator
        }
    });

    return mdString;
}

// --- YAML Formatter Helpers ---
/**
 * Escapes a string for safe inclusion in YAML, quoting if necessary.
 * @param {*} str - The value to escape (will be converted to string).
 * @returns {string} The YAML-safe string.
 */
function escapeYamlString(str) {
    if (str === null || str === undefined) return 'null';
    if (typeof str !== 'string') str = String(str);

    // Use JSON.stringify for reliable quoting and escaping, then remove outer quotes if not needed.
    const jsonString = JSON.stringify(str);

    // When JSON.stringify is just the original string + quotes, it means no special chars needed escaping.
    // We might still need quotes for YAML reasons (e.g., starts with number, contains ': ').
    const needsYamlQuotes = /[:{}[\],&*#?|\-<> =!%@`]|^\s|\s$|^[Tt]rue$|^[Ff]alse$|^[Nn]ull$|^[+-]?\d/.test(str) || str.includes('\n');

    if (needsYamlQuotes) {
        return jsonString; // Keep the JSON quotes and escapes
    } else {
        // If YAML doesn't strictly require quotes, return the raw string
        // Check if JSON added quotes unnecessarily (only alphanumeric/simple symbols)
        const simpleStringRegex = /^[a-zA-Z0-9_.\/ ]+$/; // Adjust regex for allowed unquoted chars
         if (simpleStringRegex.test(str) && !/^[\d.]/.test(str) && !/:\s/.test(str) && !/^\s|\s$/.test(str)) {
             // Seems safe to unquote for YAML
             return str;
         } else {
            // Keep JSON quotes if unsure or complex
            return jsonString;
         }
    }
}

/**
 * Indents each line of a string for YAML block scalars.
 * @param {string} text - The text to indent.
 * @param {string} [indent='    '] - The indentation string (usually spaces).
 * @returns {string} The indented text block.
 */
function indentYamlBlockScalar(text, indent = '    ') {
    if (text === null || text === undefined) return indent + 'null'; // Explicit null
    if (text === '') return indent + '""'; // Explicit empty string
    // Ensure consistent line endings (LF) and apply indentation
    return String(text).replace(/\r\n/g, '\n').split('\n').map(line => indent + line).join('\n');
}

/**
 * Formats processed video data and metadata into a structured YAML string.
 * @param {object} resultData - Metadata object from appState.currentResult.metadata.
 * @param {Array} videos - Array of video data objects from appState.currentResult.processedVideos.
 * @param {boolean} includeDescription - Whether to include the video description.
 * @returns {string} The formatted YAML string.
 */
function formatAsYamlStructured(resultData, videos, includeDescription) {
    // Start with metadata if available
    let yamlString = '';
    if (resultData) {
        yamlString += `source_name: ${escapeYamlString(resultData.source_name)}\n`;
        yamlString += `video_count: ${resultData.video_count ?? 0}\n`;
        yamlString += `processing_time_ms: ${resultData.processing_time_ms ?? 'null'}\n`;
        yamlString += `api_call_count: ${resultData.api_call_count ?? 'null'}\n`;
        yamlString += `api_quota_used: ${resultData.api_quota_used ?? 'null'}\n`;
        yamlString += `high_quota_cost: ${resultData.high_quota_cost ? 'true' : 'false'}\n`;
        yamlString += `token_count: ${resultData.token_count ?? 'null'}\n`;
        // Include request parameters used
        if (appState.currentRequest.params) {
            yamlString += 'request_parameters:\n';
            yamlString += `  url: ${escapeYamlString(appState.currentRequest.params.url)}\n`;
            yamlString += `  include_transcript: ${appState.currentRequest.params.include_transcript}\n`;
            yamlString += `  include_description: ${appState.currentRequest.params.include_description}\n`;
            yamlString += `  separate_files: ${appState.currentRequest.params.separate_files}\n`;
            yamlString += `  transcript_interval: ${appState.currentRequest.params.transcript_interval ?? 0}\n`;
            yamlString += `  start_date: ${escapeYamlString(appState.currentRequest.params.start_date)}\n`; // Will be 'null' if not set
            yamlString += `  end_date: ${escapeYamlString(appState.currentRequest.params.end_date)}\n`;     // Will be 'null' if not set
        }
    }

    // Add videos array
    yamlString += 'videos:\n';
    if (!videos || videos.length === 0) {
        yamlString += '[]\n'; // Empty list
    } else {
        videos.forEach(video => {
            // Safely access properties
            const videoId = video?.id || '';
            const title = video?.snippet?.title || 'Untitled Video';
            const url = videoId ? `https://youtu.be/${videoId}` : '';
            const channelTitle = video?.snippet?.channelTitle || 'N/A';
            const channelId = video?.snippet?.channelId || '';
            const channelUrl = channelId ? `https://www.youtube.com/channel/${channelId}` : '';
            const publishedAtISO = video?.snippet?.publishedAt || ''; // Keep ISO format
            const durationISO = video?.contentDetails?.duration || ''; // Keep ISO format
            const tags = video?.snippet?.tags || [];
            const description = video?.snippet?.description || '';
            const transcriptText = video?.transcript?.transcript || '';
            const transcriptLang = video?.transcript?.language || '';

            yamlString += `- id: ${escapeYamlString(videoId)}\n`;
            yamlString += `  title: ${escapeYamlString(title)}\n`;
            yamlString += `  url: ${escapeYamlString(url)}\n`;
            yamlString += `  channel_name: ${escapeYamlString(channelTitle)}\n`;
            yamlString += `  channel_url: ${escapeYamlString(channelUrl)}\n`;
            yamlString += `  published_at_iso8601: ${escapeYamlString(publishedAtISO)}\n`; // Keep ISO
            yamlString += `  duration_iso8601: ${escapeYamlString(durationISO)}\n`; // Keep ISO

            // Format tags as YAML list
            if (tags.length > 0) {
                yamlString += '  tags:\n';
                tags.forEach(tag => {
                    yamlString += `    - ${escapeYamlString(tag)}\n`;
                });
            } else {
                yamlString += '  tags: []\n'; // Empty list
            }

            // Add description using literal block scalar (|) if included
            if (includeDescription) {
                yamlString += '  description: |\n';
                yamlString += indentYamlBlockScalar(description.trim(), '    ') + '\n';
            } else {
                yamlString += '  description: null\n'; // Use null if not included
            }

            // Add transcript if available
            if (transcriptText) {
                yamlString += '  transcript:\n';
                yamlString += `    language: ${escapeYamlString(transcriptLang)}\n`;
                yamlString += '    text: |\n'; // Literal block scalar
                yamlString += indentYamlBlockScalar(transcriptText.trim(), '      ') + '\n'; // Indent under text:
            } else {
                yamlString += '  transcript: null\n'; // Use null if no transcript
            }
        });
    }

    return yamlString;
}


/**
 * Shows temporary feedback text on a button (e.g., "Copied!").
 * @param {Element|null} buttonElement - The button element.
 * @param {string} feedbackTextKey - The translation key for the feedback text.
 */
function showButtonFeedback(buttonElement, feedbackTextKey) {
     const text = _(feedbackTextKey);
     if (buttonElement && !buttonElement.classList.contains('feedback-active')) {
         buttonElement.classList.add('feedback-active');
         buttonElement.setAttribute('data-feedback-text', text);
         const originalDisabled = buttonElement.disabled;
         buttonElement.disabled = true; // Temporarily disable during feedback
         setTimeout(() => {
             buttonElement.classList.remove('feedback-active');
             buttonElement.removeAttribute('data-feedback-text');
             buttonElement.disabled = originalDisabled; // Restore original state
         }, 1500); // Feedback duration
     }
}

/**
 * Adjusts the font size of the digest textarea.
 * @param {number} increment - The amount to increment/decrement the multiplier (e.g., 0.1 or -0.1).
 */
function adjustFontSize(increment) {
    // Ensure multiplier is valid, reset if not
    if (typeof appState.ui.fontSizeMultiplier !== 'number' || isNaN(appState.ui.fontSizeMultiplier)) {
         appState.ui.fontSizeMultiplier = 1;
    }

    // Calculate new multiplier, clamped within min/max bounds
    const newMultiplier = Math.max(FONT_SIZE_MIN_MULTIPLIER, Math.min(FONT_SIZE_MAX_MULTIPLIER, appState.ui.fontSizeMultiplier + increment));

    // Apply only if multiplier actually changed
    if (newMultiplier !== appState.ui.fontSizeMultiplier || increment === 0) { // Apply on increment=0 for initial set
        appState.ui.fontSizeMultiplier = newMultiplier;
        if(domElements.digestTextarea) {
            const newSizeRem = FONT_SIZE_BASE_REM * appState.ui.fontSizeMultiplier;
            domElements.digestTextarea.style.fontSize = `${newSizeRem}rem`;
        }
        // Show toast notification only if size was actively changed by user (increment != 0)
        if (increment !== 0) {
            showToast("toastFontSize", "info", { percent: (appState.ui.fontSizeMultiplier * 100).toFixed(0) });
        }
    }
     // Update button states based on limits
     if (domElements.increaseFontButton) domElements.increaseFontButton.disabled = appState.ui.fontSizeMultiplier >= FONT_SIZE_MAX_MULTIPLIER;
     if (domElements.decreaseFontButton) domElements.decreaseFontButton.disabled = appState.ui.fontSizeMultiplier <= FONT_SIZE_MIN_MULTIPLIER;
}


/**
 * Displays a short-lived toast notification message.
 * @param {string} messageKey - The translation key for the message.
 * @param {string} [type="success"] - The type of toast ('success', 'error', 'warning', 'info').
 * @param {object} [params={}] - Optional parameters for placeholder replacement in the message.
 */
function showToast(messageKey, type = "success", params = {}) {
     if (!domElements.toast || !domElements.toastIcon || !domElements.toastMessage) return;

     const message = _(messageKey, params);
     const toastType = TOAST_CLASSES[type] || TOAST_CLASSES['info'];
     const iconSVG = TOAST_ICONS[type] || TOAST_ICONS['info'];

     domElements.toast.className = `toast ${toastType}`; // Reset and set type class
     domElements.toastIcon.innerHTML = iconSVG;
     domElements.toastMessage.textContent = message;

     // Clear existing timeout if a toast is already showing
     if (appState.ui.toastTimeoutId) clearTimeout(appState.ui.toastTimeoutId);

     domElements.toast.classList.add("show"); // Make toast visible

     // Set a new timeout to hide the toast
     appState.ui.toastTimeoutId = setTimeout(() => {
         domElements.toast.classList.remove("show");
         appState.ui.toastTimeoutId = null;
     }, 3000); // Toast duration
}

// Setup listener for the dismiss button (if it exists)
if (domElements.dismissToast) {
    domElements.dismissToast.addEventListener('click', () => {
        if (domElements.toast) {
            domElements.toast.classList.remove("show");
            if (appState.ui.toastTimeoutId) {
                clearTimeout(appState.ui.toastTimeoutId);
                appState.ui.toastTimeoutId = null;
            }
        }
    });
}

// --- History Functions ---

/**
 * Adds a new item to the search history (and localStorage).
 * @param {string} url - The URL or search term used.
 * @param {string} sourceName - The derived source name for the item.
 */
function addToHistory(url, sourceName) {
     if (!url) return;
     const newItem = {
         url: url,
         sourceName: sourceName || _('historyItemUnknown'), // Use translated fallback
         timestamp: Date.now()
        };

     // Remove any existing item with the same URL to avoid duplicates and move to top
     appState.history.items = appState.history.items.filter(item => item.url !== url);

     // Add the new item to the beginning of the array
     appState.history.items.unshift(newItem);

     // Limit the history size
     if (appState.history.items.length > appState.history.maxItems) {
         appState.history.items.pop(); // Remove the oldest item
     }

     saveHistoryToStorage();

     // Update the history list in the UI if the modal is currently visible
     if (domElements.historyModal && domElements.historyModal.classList.contains('is-visible')) {
         updateHistoryList();
     }
}

/**
 * Loads the search history from localStorage.
 * @returns {Array} The array of history items.
 */
function loadHistoryFromStorage() {
     try {
         const storedHistory = localStorage.getItem('youtubingest_history');
         // Basic validation: ensure it's an array
         if (storedHistory) {
             const parsed = JSON.parse(storedHistory);
             return Array.isArray(parsed) ? parsed : [];
         }
         return [];
     } catch (e) {
         console.error("Error loading history from localStorage:", e);
         localStorage.removeItem('youtubingest_history'); // Clear potentially corrupted data
         return [];
     }
}

/**
 * Saves the current search history array to localStorage.
 */
function saveHistoryToStorage() {
     try {
         localStorage.setItem('youtubingest_history', JSON.stringify(appState.history.items));
     } catch (e) {
         console.error("Error saving history to localStorage:", e);
         // Consider notifying the user if storage fails repeatedly
     }
}

/**
 * Clears the search history from the state and localStorage.
 */
function clearHistory() {
     appState.history.items = [];
     saveHistoryToStorage();
     updateHistoryList(); // Update the displayed list in the modal
     showToast("toastHistoryCleared", "info");
}

/**
 * Updates the history list displayed in the modal UI.
 */
function updateHistoryList() {
     if (!domElements.historyList || !domElements.clearHistoryBtn) return;

     domElements.historyList.innerHTML = ''; // Clear current list items

     if (appState.history.items.length === 0) {
         // Display empty message and disable clear button
         const li = document.createElement('li');
         li.className = 'history-empty-message';
         li.textContent = _('historyModalNoItems');
         li.setAttribute('role', 'status');
         domElements.historyList.appendChild(li);
         domElements.clearHistoryBtn.disabled = true;
         return;
     }

     // Enable clear button if history exists
     domElements.clearHistoryBtn.disabled = false;

     // Define locale for date formatting based on current UI language
     const locale = appState.ui.currentLang === 'fr' ? 'fr-FR' : 'en-US';
     const dateOptions = { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute:'2-digit' };

     // Create and append list items for each history entry
     appState.history.items.forEach(item => {
         const li = document.createElement('li');
         li.className = 'history-item';
         li.setAttribute('role', 'option'); // Semantically, these are options to select
         li.setAttribute('tabindex', '0'); // Make items focusable

         const date = new Date(item.timestamp);
         // Use Intl.DateTimeFormat for more robust localization
         const formattedDate = new Intl.DateTimeFormat(locale, dateOptions).format(date);

         // Sanitize display name and URL before inserting
         const displayName = sanitizeText(item.sourceName || _('historyItemUnknown'));
         const displayUrl = sanitizeText(item.url);

         li.innerHTML = `
             <div class="history-item-content">
                 <span class="history-item-name" title="${displayName}">${displayName}</span>
                 <div class="history-item-details">
                     <span class="history-item-url" title="${displayUrl}">${displayUrl}</span>
                     <span class="history-item-date">${formattedDate}</span>
                 </div>
             </div>`;

         // Add event listener to load the history item when clicked or Enter/Space is pressed
         const loadHistoryItem = () => {
             if(domElements.urlInput) domElements.urlInput.value = item.url;
             // Reset date filters when loading from history
             if(domElements.startDateInput) domElements.startDateInput.value = '';
             if(domElements.endDateInput) domElements.endDateInput.value = '';
             toggleHistoryModal(false); // Close modal
             if(domElements.ingestForm) domElements.ingestForm.dispatchEvent(new Event('submit')); // Submit form
         };

         li.addEventListener('click', loadHistoryItem);
         li.addEventListener('keydown', (event) => {
             if (event.key === 'Enter' || event.key === ' ') {
                 event.preventDefault(); // Prevent space from scrolling
                 loadHistoryItem();
             }
         });

         domElements.historyList.appendChild(li);
     });
}

/**
 * Toggles the visibility of the history modal.
 * @param {boolean} show - True to show the modal, false to hide it.
 */
function toggleHistoryModal(show) {
     if (!domElements.historyModal) return;
     if (show) {
         updateHistoryList(); // Ensure list is up-to-date when showing
         domElements.historyModal.classList.add('is-visible');
         // Focus the close button for accessibility after a short delay for transition
         setTimeout(() => domElements.closeHistoryBtn?.focus(), 100);
     } else {
         domElements.historyModal.classList.remove('is-visible');
         // Optionally return focus to the button that opened the modal
         domElements.historyButton?.focus();
     }
 }
