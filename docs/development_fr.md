# Guide de développement

Ce document fournit des informations pour les développeurs qui souhaitent contribuer au projet Youtubingest.

## Configuration de l'environnement de développement

### Prérequis

- Python 3.8 ou supérieur
- pip (gestionnaire de paquets Python)
- Clé API YouTube (obtenue depuis la [Google Cloud Console](https://console.cloud.google.com/))

### Installation

1. Clonez le dépôt :
   ```bash
   git clone https://github.com/votre-utilisateur/youtubingest.git
   cd youtubingest
   ```

2. Créez un environnement virtuel :
   ```bash
   python -m venv venv
   ```

3. Activez l'environnement virtuel :
   - Windows :
     ```bash
     venv\Scripts\activate
     ```
   - Linux/macOS :
     ```bash
     source venv/bin/activate
     ```

4. Installez les dépendances :
   ```bash
   pip install -r requirements.txt
   ```

5. Créez un fichier `.env` à la racine du projet avec votre clé API YouTube :
   ```
   YOUTUBE_API_KEY=votre_clé_api_youtube
   ```

### Exécution en mode développement

Pour exécuter l'application en mode développement :

```bash
python server.py
```

L'application sera accessible à l'adresse `http://localhost:8000`.

## Structure du projet

```
youtubingest/
├── api/                  # Définitions des routes API
│   ├── dependencies.py   # Dépendances injectables
│   └── routes.py         # Endpoints API
├── docs/                 # Documentation
├── services/             # Services métier
│   ├── engine.py         # Moteur principal
│   ├── transcript.py     # Gestion des transcriptions
│   └── youtube_api.py    # Client API YouTube
├── static/               # Fichiers statiques
├── tests/                # Tests unitaires et d'intégration
├── cache_manager.py      # Gestionnaire de cache
├── config.py             # Configuration
├── exceptions.py         # Gestion des exceptions
├── logging_config.py     # Configuration du logging
├── main.py               # Application FastAPI
├── models.py             # Modèles de données
├── server.py             # Point d'entrée du serveur
├── text_processing.py    # Traitement de texte
└── utils.py              # Utilitaires
```

## Conventions de codage

### Style de code

- Suivez [PEP 8](https://www.python.org/dev/peps/pep-0008/) pour le style de code Python
- Utilisez des noms de variables et de fonctions explicites
- Limitez la longueur des lignes à 100 caractères
- Utilisez des docstrings pour documenter les classes et les fonctions

### Docstrings

Utilisez le format Google pour les docstrings :

```python
def fonction_exemple(param1, param2):
    """Description de la fonction.

    Args:
        param1: Description du premier paramètre.
        param2: Description du deuxième paramètre.

    Returns:
        Description de la valeur de retour.

    Raises:
        ExceptionType: Description de quand l'exception est levée.
    """
    # Corps de la fonction
```

### Commentaires

- Les commentaires de code doivent être en anglais
- Utilisez des commentaires pour expliquer le "pourquoi", pas le "quoi"
- Évitez les commentaires redondants qui répètent simplement le code

## Tests

### Exécution des tests

Pour exécuter tous les tests :

```bash
python -m unittest discover
```

Pour exécuter un test spécifique :

```bash
python -m unittest tests.test_module
```

### Écriture de tests

- Écrivez des tests unitaires pour chaque nouvelle fonctionnalité
- Utilisez `unittest.IsolatedAsyncioTestCase` pour les tests asynchrones
- Utilisez des mocks pour isoler les composants externes
- Visez une couverture de code d'au moins 80%

## Gestion des dépendances

- Ajoutez les nouvelles dépendances dans `requirements.txt`
- Utilisez des versions spécifiques pour les dépendances (ex: `fastapi==0.68.0`)
- Minimisez le nombre de dépendances externes

## Processus de contribution

1. Créez une branche pour votre fonctionnalité ou correction de bug
2. Écrivez des tests pour votre code
3. Assurez-vous que tous les tests passent
4. Soumettez une pull request avec une description détaillée des changements

## Bonnes pratiques

### Performance

- Utilisez le cache pour les opérations coûteuses
- Limitez les appels à l'API YouTube pour économiser le quota
- Utilisez des opérations asynchrones pour les opérations d'I/O
- Surveillez l'utilisation de la mémoire

### Sécurité

- Ne stockez jamais de clés API ou de secrets dans le code
- Validez toutes les entrées utilisateur
- Utilisez des limites de taux pour prévenir les abus
- Suivez les bonnes pratiques OWASP

### Logging

- Utilisez le logger configuré dans `logging_config.py`
- Incluez des informations contextuelles dans les logs
- Utilisez le niveau de log approprié (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Évitez de logger des informations sensibles

## Déploiement

### Préparation pour la production

1. Définissez les variables d'environnement appropriées
2. Utilisez un serveur WSGI/ASGI comme Gunicorn ou Uvicorn
3. Configurez un proxy inverse comme Nginx
4. Utilisez HTTPS pour toutes les communications

### Variables d'environnement

- `YOUTUBE_API_KEY` : Clé API YouTube
- `HOST` : Hôte du serveur (défaut: 127.0.0.1)
- `PORT` : Port du serveur (défaut: 8000)
- `LOG_LEVEL_CONSOLE` : Niveau de log pour la console (défaut: INFO)
- `LOG_LEVEL_FILE` : Niveau de log pour les fichiers (défaut: DEBUG)
- `DEBUG` : Mode debug (défaut: false)

## Ressources

- [Documentation FastAPI](https://fastapi.tiangolo.com/)
- [Documentation API YouTube](https://developers.google.com/youtube/v3/docs)
- [Documentation asyncio](https://docs.python.org/3/library/asyncio.html)
