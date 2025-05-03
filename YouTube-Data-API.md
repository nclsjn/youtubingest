# Documentation Technique partielle de l'API YouTube Data (v3)

Cette documentation technique couvre plusieurs méthodes de l'API YouTube Data (v3) fournies par Google pour les développeurs. Chaque section décrit une méthode spécifique, ses paramètres, les structures de requête et de réponse, les erreurs possibles, ainsi que des exemples d'utilisation.

---

## Captions: list | YouTube Data API | Google pour les Développeurs

### Description

Retourne une liste de pistes de sous-titres associées à une vidéo spécifiée. Notez que la réponse de l'API ne contient pas les sous-titres réels et que la méthode [captions.download](https://developers.google.com/youtube/v3/docs/captions/download) permet de récupérer une piste de sous-titres.

**Impact sur le quota :** Un appel à cette méthode a un [coût de quota](https://developers.google.com/youtube/v3/getting-started#quota) de 50 unités.

### Cas d'utilisation courants

* Gérer et afficher les sous-titres disponibles pour une vidéo spécifique.
* Intégrer des fonctionnalités de traduction automatique des sous-titres dans une application.

### Requête

#### Requête HTTP

```http
GET https://www.googleapis.com/youtube/v3/captions
```

#### Autorisation

Cette requête nécessite une autorisation avec au moins l'un des scopes suivants ([en savoir plus sur l'authentification et l'autorisation](https://developers.google.com/youtube/v3/guides/authentication)).

| Scope |
| --- |
| `https://www.googleapis.com/auth/youtube.force-ssl` |
| `https://www.googleapis.com/auth/youtubepartner` |

#### Paramètres

Le tableau suivant liste les paramètres pris en charge par cette requête. Tous les paramètres listés sont des paramètres de requête.

| Paramètre | Type | Description |
| --- | --- | --- |
| `part` (requis) | `string` | Spécifie les parties de la ressource `caption` que la réponse de l'API inclura. Les valeurs possibles sont `id` et `snippet`. |
| `videoId` (requis) | `string` | Spécifie l'ID de la vidéo YouTube pour laquelle l'API doit retourner les pistes de sous-titres. |
| `id` (optionnel) | `string` | Spécifie une liste séparée par des virgules d'IDs identifiant les ressources `caption` à récupérer. Chaque ID doit identifier une piste de sous-titres associée à la vidéo spécifiée. |
| `onBehalfOfContentOwner` (optionnel) | `string` | Utilisé uniquement dans une requête correctement [autorisé](https://developers.google.com/youtube/v3/guides/authentication). Destiné exclusivement aux partenaires de contenu YouTube. Indique que les informations d'identification d'autorisation de la requête identifient un utilisateur CMS YouTube agissant au nom du propriétaire de contenu spécifié. |

#### Corps de la Requête

Ne fournissez pas de corps de requête lors de l'appel de cette méthode.

### Réponse

Si la méthode réussit, elle renvoie un corps de réponse avec la structure suivante :

```json
{
  "kind": "youtube#captionListResponse",
  "etag": "etag_value",
  "items": [
    {
      // Ressource caption
    }
  ]
}
```

#### Propriétés

| Propriété | Type | Description |
| --- | --- | --- |
| `kind` | `string` | Identifie le type de ressource API. La valeur sera `youtube#captionListResponse`. |
| `etag` | `etag` | L'Etag de cette ressource. |
| `items[]` | `list` | Une liste de sous-titres correspondant aux critères de la requête. |

### Erreurs

Le tableau suivant identifie les messages d'erreur que l'API pourrait renvoyer en réponse à un appel de cette méthode. Veuillez consulter la documentation des [messages d'erreur](https://developers.google.com/youtube/v3/docs/errors) pour plus de détails.

| Type d'erreur | Détail de l'erreur | Description |
| --- | --- | --- |
| `forbidden (403)` | `forbidden` | Une ou plusieurs pistes de sous-titres n'ont pas pu être récupérées car les permissions associées à la requête ne sont pas suffisantes. La requête pourrait ne pas être correctement autorisée. |
| `notFound (404)` | `captionNotFound` | Une ou plusieurs des pistes de sous-titres spécifiées n'ont pas pu être trouvées. Cette erreur se produit si le paramètre `videoId` identifie une vidéo réelle, mais le paramètre `id` identifie des IDs de pistes de sous-titres qui n'existent pas ou qui sont associées à d'autres vidéos. Vérifiez les valeurs des paramètres `id` et `videoId` de la requête pour vous assurer qu'elles sont correctes. |
| `notFound (404)` | `videoNotFound` | La vidéo identifiée par le paramètre `videoId` n'a pas pu être trouvée. |

### Exemples

*Les exemples de code ont été supprimés.*

---

## Channels: list | YouTube Data API | Google pour les Développeurs

### Description

**Remarque :** La propriété `[statistics.subscriberCount](https://developers.google.com/youtube/v3/docs/channels#statistics.subscriberCount)` de la ressource `channel` a été mise à jour pour refléter un changement de politique YouTube affectant la manière dont les comptes de abonnés sont affichés. Pour plus d'informations, consultez [Historique des Révisions](https://developers.google.com/youtube/v3/revision_history#release_notes_09_10_2019) ou le [Centre d'Aide YouTube](https://support.google.com/youtube/answer/6051134).

Retourne une collection de zéro ou plusieurs ressources `channel` qui correspondent aux critères de la requête.

**Impact sur le quota :** Un appel à cette méthode a un [coût de quota](https://developers.google.com/youtube/v3/getting-started#quota) de 1 unité.

### Cas d'utilisation courants

* Récupérer des informations détaillées sur un ou plusieurs canaux YouTube.
* Afficher les statistiques et les paramètres de branding d'un canal spécifique.

### Requête

#### Requête HTTP

```http
GET https://www.googleapis.com/youtube/v3/channels
```

#### Autorisation

Une requête qui récupère la partie `auditDetails` pour une ressource `channel` doit fournir un jeton d'autorisation contenant le scope `https://www.googleapis.com/auth/youtubepartner-channel-audit`. De plus, tout jeton utilisant ce scope doit être révoqué lorsque le MCN décide d'accepter ou de rejeter le canal ou dans les deux semaines suivant la date d'émission du jeton.

#### Paramètres

Le tableau suivant liste les paramètres pris en charge par cette requête. Tous les paramètres listés sont des paramètres de requête.

| Paramètre | Type | Description |
| --- | --- | --- |
| `part` (requis) | `string` | Spécifie une liste séparée par des virgules d'une ou plusieurs propriétés de la ressource `channel` que la réponse de l'API inclura. Si le paramètre identifie une propriété contenant des propriétés enfant, les propriétés enfant seront incluses dans la réponse. Par exemple, dans une ressource `channel`, la propriété `contentDetails` contient d'autres propriétés, telles que `uploads`. Ainsi, si vous définissez `part=contentDetails`, la réponse de l'API contiendra également toutes ces propriétés imbriquées. Les noms de parties disponibles incluent : `auditDetails`, `brandingSettings`, `contentDetails`, `contentOwnerDetails`, `id`, `localizations`, `snippet`, `statistics`, `status`, `topicDetails`. |
| **Filtres** *(spécifiez exactement un des paramètres suivants)* |  |  |
| `categoryId` | `string` | **Déprécié.** Spécifiait une [catégorie guide YouTube](https://developers.google.com/youtube/v3/docs/guideCategories) et pouvait être utilisé pour demander des canaux YouTube associés à cette catégorie. |
| `forHandle` | `string` | Spécifie un identifiant YouTube, demandant ainsi le canal associé à cet identifiant. La valeur du paramètre peut être précédée du symbole `@`. Par exemple, pour récupérer la ressource du canal "Google for Developers", définissez la valeur du paramètre `forHandle` sur `GoogleDevelopers` ou `@GoogleDevelopers`. |
| `forUsername` | `string` | Spécifie un nom d'utilisateur YouTube, demandant ainsi le canal associé à ce nom d'utilisateur. |
| `id` | `string` | Spécifie une liste séparée par des virgules d'IDs de canaux YouTube pour les ressources à récupérer. Dans une ressource `channel`, la propriété `id` spécifie l'ID du canal YouTube. |
| `managedByMe` | `boolean` | Utilisé uniquement dans une requête correctement [autorisé](https://developers.google.com/youtube/v3/guides/authentication). Destiné exclusivement aux partenaires de contenu YouTube. Définissez la valeur de ce paramètre sur `true` pour demander à l'API de ne retourner que les canaux gérés par le propriétaire de contenu spécifié dans le paramètre `onBehalfOfContentOwner`. L'utilisateur doit être authentifié en tant que compte CMS lié au propriétaire de contenu spécifié et `onBehalfOfContentOwner` doit être fourni. |
| `mine` | `boolean` | Utilisé uniquement dans une requête correctement [autorisé](https://developers.google.com/youtube/v3/guides/authentication). Définissez la valeur de ce paramètre sur `true` pour demander à l'API de ne retourner que les canaux appartenant à l'utilisateur authentifié. |

| Paramètre | Type | Description |
| --- | --- | --- |
| `hl` | `string` | Instruis l'API de récupérer les métadonnées localisées de la ressource pour une langue d'application spécifique prise en charge par le site YouTube. La valeur du paramètre doit être un code de langue inclus dans la liste retournée par la méthode [i18nLanguages.list](https://developers.google.com/youtube/v3/docs/i18nLanguages/list). Si les détails localisés sont disponibles dans cette langue, l'objet `snippet.localized` de la ressource contiendra les valeurs localisées. Sinon, il contiendra les détails de la ressource dans la langue par défaut de la ressource. |
| `maxResults` | `unsigned integer` | Spécifie le nombre maximal d'éléments qui doivent être retournés dans l'ensemble de résultats. Les valeurs acceptables sont de `0` à `50`, inclusivement. La valeur par défaut est `5`. |
| `onBehalfOfContentOwner` | `string` | Utilisé uniquement dans une requête correctement [autorisé](https://developers.google.com/youtube/v3/guides/authentication) et destiné exclusivement aux partenaires de contenu YouTube. Indique que les informations d'identification d'autorisation de la requête identifient un utilisateur CMS YouTube agissant au nom du propriétaire de contenu spécifié. Permet aux propriétaires de contenu de s'authentifier une fois et d'accéder à toutes leurs données de vidéos et de canaux sans fournir d'informations d'identification pour chaque canal individuel. |
| `pageToken` | `string` | Identifie une page spécifique dans l'ensemble de résultats qui doit être retournée. Dans une réponse API, les propriétés `nextPageToken` et `prevPageToken` identifient d'autres pages qui pourraient être récupérées. |

#### Corps de la Requête

Ne fournissez pas de corps de requête lors de l'appel de cette méthode.

### Réponse

Si la méthode réussit, elle renvoie un corps de réponse avec la structure suivante :

```json
{
  "kind": "youtube#channelListResponse",
  "etag": "etag_value",
  "nextPageToken": "string",
  "prevPageToken": "string",
  "pageInfo": {
    "totalResults": 100,
    "resultsPerPage": 5
  },
  "items": [
    {
      // Ressource channel
    }
  ]
}
```

#### Propriétés

| Propriété | Type | Description |
| --- | --- | --- |
| `kind` | `string` | Identifie le type de ressource API. La valeur sera `youtube#channelListResponse`. |
| `etag` | `etag` | L'Etag de cette ressource. |
| `nextPageToken` | `string` | Le jeton qui peut être utilisé comme valeur du paramètre `pageToken` pour récupérer la page suivante dans l'ensemble de résultats. |
| `prevPageToken` | `string` | Le jeton qui peut être utilisé comme valeur du paramètre `pageToken` pour récupérer la page précédente dans l'ensemble de résultats. Notez que cette propriété n'est pas incluse dans la réponse de l'API si la requête API a défini le paramètre `managedByMe` sur `true`. |
| `pageInfo` | `object` | L'objet `pageInfo` encapsule les informations de pagination pour l'ensemble de résultats. |
| `pageInfo.totalResults` | `integer` | Le nombre total de résultats dans l'ensemble de résultats. |
| `pageInfo.resultsPerPage` | `integer` | Le nombre de résultats inclus dans la réponse de l'API. |
| `items[]` | `list` | Une liste de canaux correspondant aux critères de la requête. |

### Erreurs

Le tableau suivant identifie les messages d'erreur que l'API pourrait renvoyer en réponse à un appel de cette méthode. Pour plus de détails, consultez [YouTube Data API - Erreurs](https://developers.google.com/youtube/v3/docs/errors).

| Type d'erreur | Détail de l'erreur | Description |
| --- | --- | --- |
| `badRequest (400)` | `invalidCriteria` | Un maximum d'un des filtres suivants peut être spécifié : `id`, `categoryId`, `mine`, `managedByMe`, `forHandle`, `forUsername`. En cas d'authentification du propriétaire de contenu via le paramètre `onBehalfOfContentOwner`, seuls `id` ou `managedByMe` peuvent être spécifiés. |
| `forbidden (403)` | `channelForbidden` | Le canal spécifié par le paramètre `id` ne prend pas en charge la requête ou la requête n'est pas correctement autorisée. |
| `notFound (404)` | `categoryNotFound` | La catégorie identifiée par le paramètre `categoryId` ne peut pas être trouvée. Utilisez la méthode [guideCategories.list](https://developers.google.com/youtube/v3/docs/guideCategories/list) pour récupérer une liste de valeurs valides. |
| `notFound (404)` | `channelNotFound` | Le canal spécifié dans le paramètre `id` ne peut pas être trouvé. |

### Exemples

*Les exemples de code ont été supprimés.*

---

## PlaylistItems: list | YouTube Data API | Google pour les Développeurs

### Description

Retourne une collection d'éléments de playlist qui correspondent aux paramètres de la requête API. Vous pouvez récupérer tous les éléments d'une playlist spécifiée ou récupérer un ou plusieurs éléments de playlist par leurs IDs uniques.

**Impact sur le quota :** Un appel à cette méthode a un [coût de quota](https://developers.google.com/youtube/v3/getting-started#quota) de 1 unité.

### Cas d'utilisation courants

* Afficher les vidéos contenues dans une playlist spécifique.
* Gérer les éléments de playlist (ajouter, supprimer, réorganiser).

### Requête

#### Requête HTTP

```http
GET https://www.googleapis.com/youtube/v3/playlistItems
```

#### Paramètres

Le tableau suivant liste les paramètres pris en charge par cette requête. Tous les paramètres listés sont des paramètres de requête.

| Paramètre | Type | Description |
| --- | --- | --- |
| `part` (requis) | `string` | Spécifie une liste séparée par des virgules d'une ou plusieurs propriétés de la ressource `playlistItem` que la réponse de l'API inclura. Les valeurs possibles incluent : `contentDetails`, `id`, `snippet`, `status`. Si une partie contient des propriétés enfant, ces dernières seront également incluses dans la réponse. |
| **Filtres** *(spécifiez exactement un des paramètres suivants)* |  |  |
| `id` | `string` | Spécifie une liste séparée par des virgules d'un ou plusieurs IDs uniques d'éléments de playlist. |
| `playlistId` | `string` | Spécifie l'ID unique de la playlist pour laquelle vous souhaitez récupérer les éléments de playlist. Notez que chaque requête pour récupérer des éléments de playlist doit spécifier une valeur pour le paramètre `id` ou `playlistId`. |
| `videoId` | `string` | Spécifie que la requête doit retourner uniquement les éléments de playlist contenant la vidéo spécifiée. |

| Paramètre | Type | Description |
| --- | --- | --- |
| `hl` | `string` | Instruis l'API de récupérer les métadonnées localisées de la ressource pour une langue d'application spécifique prise en charge par le site YouTube. La valeur doit être un code de langue inclus dans la liste retournée par la méthode [i18nLanguages.list](https://developers.google.com/youtube/v3/docs/i18nLanguages/list). |
| `maxResults` | `unsigned integer` | Spécifie le nombre maximal d'éléments qui doivent être retournés dans l'ensemble de résultats. Les valeurs acceptables sont de `0` à `50`, inclusivement. La valeur par défaut est `5`. |
| `onBehalfOfContentOwner` | `string` | Utilisé uniquement dans une requête correctement [autorisé](https://developers.google.com/youtube/v3/guides/authentication) et destiné exclusivement aux partenaires de contenu YouTube. Indique que les informations d'identification d'autorisation de la requête identifient un utilisateur CMS YouTube agissant au nom du propriétaire de contenu spécifié. |
| `pageToken` | `string` | Identifie une page spécifique dans l'ensemble de résultats qui doit être retournée. Dans une réponse API, les propriétés `nextPageToken` et `prevPageToken` identifient d'autres pages qui pourraient être récupérées. |

#### Corps de la Requête

Ne fournissez pas de corps de requête lors de l'appel de cette méthode.

### Réponse

Si la méthode réussit, elle renvoie un corps de réponse avec la structure suivante :

```json
{
  "kind": "youtube#playlistItemListResponse",
  "etag": "etag_value",
  "nextPageToken": "string",
  "prevPageToken": "string",
  "pageInfo": {
    "totalResults": 100,
    "resultsPerPage": 5
  },
  "items": [
    {
      // Ressource playlistItem
    }
  ]
}
```

#### Propriétés

| Propriété | Type | Description |
| --- | --- | --- |
| `kind` | `string` | Identifie le type de ressource API. La valeur sera `youtube#playlistItemListResponse`. |
| `etag` | `etag` | L'Etag de cette ressource. |
| `nextPageToken` | `string` | Le jeton qui peut être utilisé comme valeur du paramètre `pageToken` pour récupérer la page suivante dans l'ensemble de résultats. |
| `prevPageToken` | `string` | Le jeton qui peut être utilisé comme valeur du paramètre `pageToken` pour récupérer la page précédente dans l'ensemble de résultats. |
| `pageInfo` | `object` | L'objet `pageInfo` encapsule les informations de pagination pour l'ensemble de résultats. |
| `pageInfo.totalResults` | `integer` | Le nombre total de résultats dans l'ensemble de résultats. |
| `pageInfo.resultsPerPage` | `integer` | Le nombre de résultats inclus dans la réponse de l'API. |
| `items[]` | `list` | Une liste d'éléments de playlist correspondant aux critères de la requête. |

### Exemples

*Les exemples de code ont été supprimés.*

---

## Search: list | YouTube Data API | Google pour les Développeurs

### Description

Retourne une collection de résultats de recherche qui correspondent aux paramètres de requête spécifiés dans la requête API. Par défaut, un ensemble de résultats de recherche identifie les ressources correspondantes `[video](https://developers.google.com/youtube/v3/docs/videos)`, `[channel](https://developers.google.com/youtube/v3/docs/channels)` et `[playlist](https://developers.google.com/youtube/v3/docs/playlists)`, mais vous pouvez également configurer les requêtes pour ne récupérer qu'un type spécifique de ressource.

**Impact sur le quota :** Un appel à cette méthode a un [coût de quota](https://developers.google.com/youtube/v3/getting-started#quota) de 100 unités.

### Cas d'utilisation courants

* Rechercher des vidéos, canaux ou playlists correspondant à un mot-clé spécifique.
* Filtrer les résultats de recherche par type de contenu, langue, région, etc.

### Requête

#### Requête HTTP

```http
GET https://www.googleapis.com/youtube/v3/search
```

#### Paramètres

Le tableau suivant liste les paramètres pris en charge par cette requête. Tous les paramètres listés sont des paramètres de requête.

| Paramètre | Type | Description |
| --- | --- | --- |
| `part` (requis) | `string` | Spécifie une liste séparée par des virgules d'une ou plusieurs propriétés de la ressource `search` que la réponse de l'API inclura. Définissez la valeur du paramètre sur `snippet`. |
| **Filtres** *(spécifiez 0 ou 1 des paramètres suivants)* |  |  |
| `forContentOwner` | `boolean` | Utilisé uniquement dans une requête correctement [autorisé](https://developers.google.com/youtube/v3/guides/authentication) et destiné exclusivement aux partenaires de contenu YouTube. Restreint la recherche pour ne récupérer que les vidéos appartenant au propriétaire de contenu identifié par le paramètre `onBehalfOfContentOwner`. |
| `forDeveloper` | `boolean` | Utilisé uniquement dans une requête correctement [autorisé](https://developers.google.com/youtube/v3/guides/authentication). Restreint la recherche pour ne récupérer que les vidéos téléchargées via l'application ou le site Web du développeur. |
| `forMine` | `boolean` | Utilisé uniquement dans une requête correctement [autorisé](https://developers.google.com/youtube/v3/guides/authentication). Restreint la recherche pour ne récupérer que les vidéos appartenant à l'utilisateur authentifié. |

| Paramètre | Type | Description |
| --- | --- | --- |
| `channelId` | `string` | Indique que la réponse de l'API ne doit contenir que les ressources créées par le canal spécifié. |
| `channelType` | `string` | Permet de restreindre une recherche à un type particulier de canal. Les valeurs acceptables sont `any` (tous les canaux) et `show` (seulement les émissions). |
| `eventType` | `string` | Restreint une recherche aux événements de diffusion. Les valeurs acceptables sont `completed`, `live`, et `upcoming`. |
| `location` | `string` | En conjonction avec le paramètre `locationRadius`, définit une zone géographique circulaire et restreint la recherche aux vidéos dont la localisation est dans cette zone. La valeur est une chaîne de caractères spécifiant les coordonnées latitude/longitude, par exemple `37.42307,-122.08427`. |
| `locationRadius` | `string` | En conjonction avec le paramètre `location`, définit un rayon autour du point central spécifié par `location`. La valeur doit être un nombre à virgule flottante suivi de l'unité de mesure (`m`, `km`, `ft`, `mi`). |
| `maxResults` | `unsigned integer` | Spécifie le nombre maximal d'éléments qui doivent être retournés dans l'ensemble de résultats. Les valeurs acceptables sont de `0` à `50`, inclusivement. La valeur par défaut est `5`. |
| `onBehalfOfContentOwner` | `string` | Utilisé uniquement dans une requête correctement [autorisé](https://developers.google.com/youtube/v3/guides/authentication) et destiné exclusivement aux partenaires de contenu YouTube. Indique que les informations d'identification d'autorisation de la requête identifient un utilisateur CMS YouTube agissant au nom du propriétaire de contenu spécifié. |
| `order` | `string` | Spécifie la méthode utilisée pour ordonner les ressources dans la réponse de l'API. Les valeurs acceptables incluent `date`, `rating`, `relevance`, `title`, `videoCount`, et `viewCount`. La valeur par défaut est `relevance`. |
| `pageToken` | `string` | Identifie une page spécifique dans l'ensemble de résultats qui doit être retournée. Dans une réponse API, les propriétés `nextPageToken` et `prevPageToken` identifient d'autres pages qui pourraient être récupérées. |
| `publishedAfter` | `datetime` | Indique que la réponse de l'API ne doit contenir que les ressources créées à partir de la date et l'heure spécifiées (format RFC 3339, ex. `1970-01-01T00:00:00Z`). |
| `publishedBefore` | `datetime` | Indique que la réponse de l'API ne doit contenir que les ressources créées avant ou à la date et l'heure spécifiées (format RFC 3339, ex. `1970-01-01T00:00:00Z`). |
| `q` | `string` | Spécifie le terme de requête à rechercher. Vous pouvez également utiliser les opérateurs booléens NOT (`-`) et OR (`|`) pour affiner la recherche. |
| `regionCode` | `string` | Instruis l'API de retourner les résultats de recherche pour les vidéos pouvant être visionnées dans le pays spécifié. La valeur du paramètre est un code de pays ISO 3166-1 alpha-2. |
| `relevanceLanguage` | `string` | Instruis l'API de retourner les résultats de recherche les plus pertinents pour la langue spécifiée. La valeur est généralement un code de langue ISO 639-1 à deux lettres, avec `zh-Hans` pour le chinois simplifié et `zh-Hant` pour le chinois traditionnel. |
| `safeSearch` | `string` | Indique si les résultats de recherche doivent inclure du contenu restreint en plus du contenu standard. Les valeurs acceptables sont `moderate` (par défaut), `none`, et `strict`. |
| `topicId` | `string` | Indique que la réponse de l'API ne doit contenir que les ressources associées au sujet spécifié. La valeur identifie un ID de sujet Freebase. Depuis la dépréciation de Freebase, YouTube supporte un ensemble restreint d'IDs de sujets. |
| `type` | `string` | Restreint une requête de recherche pour ne récupérer qu'un type particulier de ressource. Les valeurs acceptables sont `channel`, `playlist`, et `video`. La valeur par défaut est `video,channel,playlist`. |
| `videoCaption` | `string` | Indique si l'API doit filtrer les résultats de recherche de vidéos en fonction de la présence de sous-titres. Les valeurs acceptables sont `any`, `closedCaption`, et `none`. |
| `videoCategoryId` | `string` | Filtre les résultats de recherche de vidéos en fonction de leur catégorie. |
| `videoDefinition` | `string` | Permet de restreindre une recherche pour n'inclure que des vidéos en haute définition (HD) ou en définition standard (SD). Les valeurs acceptables sont `any`, `high`, et `standard`. |
| `videoDimension` | `string` | Permet de restreindre une recherche pour ne récupérer que des vidéos en 2D ou en 3D. Les valeurs acceptables sont `2d`, `3d`, et `any`. |
| `videoDuration` | `string` | Filtre les résultats de recherche de vidéos en fonction de leur durée. Les valeurs acceptables sont `any`, `long` (plus de 20 minutes), `medium` (4 à 20 minutes), et `short` (moins de 4 minutes). |
| `videoEmbeddable` | `string` | Permet de restreindre une recherche pour ne récupérer que les vidéos pouvant être intégrées dans une page Web. Les valeurs acceptables sont `any` et `true`. |
| `videoLicense` | `string` | Filtre les résultats de recherche pour n'inclure que les vidéos avec une licence particulière. Les valeurs acceptables sont `any`, `creativeCommon`, et `youtube`. |
| `videoPaidProductPlacement` | `string` | Filtre les résultats de recherche pour n'inclure que les vidéos avec des promotions payantes. Les valeurs acceptables sont `any` et `true`. |
| `videoSyndicated` | `string` | Permet de restreindre une recherche pour ne récupérer que les vidéos pouvant être lues en dehors de YouTube.com. Les valeurs acceptables sont `any` et `true`. |
| `videoType` | `string` | Permet de restreindre une recherche à un type particulier de vidéos. Les valeurs acceptables sont `any`, `episode`, et `movie`. |

#### Corps de la Requête

Ne fournissez pas de corps de requête lors de l'appel de cette méthode.

### Réponse

Si la méthode réussit, elle renvoie un corps de réponse avec la structure suivante :

```json
{
  "kind": "youtube#searchListResponse",
  "etag": "etag_value",
  "nextPageToken": "string",
  "prevPageToken": "string",
  "regionCode": "string",
  "pageInfo": {
    "totalResults": 100,
    "resultsPerPage": 5
  },
  "items": [
    {
      // Ressource search
    }
  ]
}
```

#### Propriétés

| Propriété | Type | Description |
| --- | --- | --- |
| `kind` | `string` | Identifie le type de ressource API. La valeur sera `youtube#searchListResponse`. |
| `etag` | `etag` | L'Etag de cette ressource. |
| `nextPageToken` | `string` | Le jeton qui peut être utilisé comme valeur du paramètre `pageToken` pour récupérer la page suivante dans l'ensemble de résultats. |
| `prevPageToken` | `string` | Le jeton qui peut être utilisé comme valeur du paramètre `pageToken` pour récupérer la page précédente dans l'ensemble de résultats. |
| `regionCode` | `string` | Le code de région utilisé pour la requête de recherche. La valeur est un code pays ISO à deux lettres identifiant la région. |
| `pageInfo` | `object` | L'objet `pageInfo` encapsule les informations de pagination pour l'ensemble de résultats. |
| `pageInfo.totalResults` | `integer` | Le nombre total de résultats dans l'ensemble de résultats. Cette valeur est une approximation et peut ne pas représenter une valeur exacte. La valeur maximale est 1 000 000. |
| `pageInfo.resultsPerPage` | `integer` | Le nombre de résultats inclus dans la réponse de l'API. |
| `items[]` | `list` | Une liste de résultats correspondant aux critères de recherche. |

### Erreurs

Le tableau suivant identifie les messages d'erreur que l'API pourrait renvoyer en réponse à un appel de cette méthode. Veuillez consulter la documentation des [messages d'erreur](https://developers.google.com/youtube/v3/docs/errors) pour plus de détails.

| Type d'erreur | Détail de l'erreur | Description |
| --- | --- | --- |
| `badRequest (400)` | `invalidChannelId` | Le paramètre `channelId` spécifie un ID de canal invalide. |
| `badRequest (400)` | `invalidLocation` | La valeur des paramètres `location` et/ou `locationRadius` a été mal formatée. |
| `badRequest (400)` | `invalidRelevanceLanguage` | La valeur du paramètre `relevanceLanguage` a été mal formatée. |
| `badRequest (400)` | `invalidSearchFilter` | La requête contient une combinaison invalide de filtres et/ou de restrictions de recherche. |

### Exemples

*Les exemples de code ont été supprimés.*

---

## Videos: list | YouTube Data API | Google pour les Développeurs

### Description

Retourne une liste de vidéos qui correspondent aux paramètres de requête spécifiés dans la requête API.

**Impact sur le quota :** Un appel à cette méthode a un [coût de quota](https://developers.google.com/youtube/v3/getting-started#quota) de 1 unité.

### Cas d'utilisation courants

* Récupérer des informations détaillées sur une ou plusieurs vidéos spécifiques.
* Afficher les statistiques et les détails de traitement d'une vidéo.

### Requête

#### Requête HTTP

```http
GET https://www.googleapis.com/youtube/v3/videos
```

#### Paramètres

Le tableau suivant liste les paramètres pris en charge par cette requête. Tous les paramètres listés sont des paramètres de requête.

| Paramètre | Type | Description |
| --- | --- | --- |
| `part` (requis) | `string` | Spécifie une liste séparée par des virgules d'une ou plusieurs propriétés de la ressource `video` que la réponse de l'API inclura. Les valeurs possibles incluent : `contentDetails`, `fileDetails`, `id`, `liveStreamingDetails`, `localizations`, `paidProductPlacementDetails`, `player`, `processingDetails`, `recordingDetails`, `snippet`, `statistics`, `status`, `suggestions`, `topicDetails`. Si une partie contient des propriétés enfant, ces dernières seront également incluses dans la réponse. |
| **Filtres** *(spécifiez exactement un des paramètres suivants)* |  |  |
| `chart` | `string` | Identifie le graphique que vous souhaitez récupérer. Les valeurs acceptables incluent `mostPopular`, qui retourne les vidéos les plus populaires pour une région et une catégorie de vidéo spécifiées. |
| `id` | `string` | Spécifie une liste séparée par des virgules des IDs YouTube vidéo pour les ressources à récupérer. Dans une ressource `video`, la propriété `id` spécifie l'ID de la vidéo. |
| `myRating` | `string` | Utilisé uniquement dans une requête correctement [autorisé](https://developers.google.com/youtube/v3/guides/authentication). Définissez la valeur de ce paramètre sur `like` ou `dislike` pour demander à l'API de ne retourner que les vidéos aimées ou détestées par l'utilisateur authentifié. |

| Paramètre | Type | Description |
| --- | --- | --- |
| `hl` | `string` | Instruis l'API de récupérer les métadonnées localisées de la ressource pour une langue d'application spécifique prise en charge par le site YouTube. La valeur du paramètre doit être un code de langue inclus dans la liste retournée par la méthode [i18nLanguages.list](https://developers.google.com/youtube/v3/docs/i18nLanguages/list). |
| `maxHeight` | `unsigned integer` | Spécifie la hauteur maximale du lecteur intégré retourné dans la propriété `player.embedHtml`. Les valeurs acceptables sont de `72` à `8192`, inclusivement. |
| `maxResults` | `unsigned integer` | Spécifie le nombre maximal d'éléments qui doivent être retournés dans l'ensemble de résultats. Cette option est supportée en conjonction avec le paramètre `myRating`, mais pas avec le paramètre `id`. Les valeurs acceptables sont de `1` à `50`, inclusivement. La valeur par défaut est `5`. |
| `maxWidth` | `unsigned integer` | Spécifie la largeur maximale du lecteur intégré retourné dans la propriété `player.embedHtml`. Les valeurs acceptables sont de `72` à `8192`, inclusivement. |
| `onBehalfOfContentOwner` | `string` | Utilisé uniquement dans une requête correctement [autorisé](https://developers.google.com/youtube/v3/guides/authentication) et destiné exclusivement aux partenaires de contenu YouTube. Indique que les informations d'identification d'autorisation de la requête identifient un utilisateur CMS YouTube agissant au nom du propriétaire de contenu spécifié. |
| `pageToken` | `string` | Identifie une page spécifique dans l'ensemble de résultats qui doit être retournée. Dans une réponse API, les propriétés `nextPageToken` et `prevPageToken` identifient d'autres pages qui pourraient être récupérées. |
| `regionCode` | `string` | Instruis l'API de sélectionner un graphique vidéo disponible dans la région spécifiée. Cette option ne peut être utilisée qu'en conjonction avec le paramètre `chart`. La valeur du paramètre est un code pays ISO 3166-1 alpha-2. |
| `videoCategoryId` | `string` | Identifie la catégorie de vidéo pour laquelle le graphique doit être récupéré. Cette option ne peut être utilisée qu'en conjonction avec le paramètre `chart`. La valeur par défaut est `0`. |

#### Corps de la Requête

Ne fournissez pas de corps de requête lors de l'appel de cette méthode.

### Réponse

Si la méthode réussit, elle renvoie un corps de réponse avec la structure suivante :

```json
{
  "kind": "youtube#videoListResponse",
  "etag": "etag_value",
  "nextPageToken": "string",
  "prevPageToken": "string",
  "pageInfo": {
    "totalResults": 100,
    "resultsPerPage": 5
  },
  "items": [
    {
      // Ressource video
    }
  ]
}
```

#### Propriétés

| Propriété | Type | Description |
| --- | --- | --- |
| `kind` | `string` | Identifie le type de ressource API. La valeur sera `youtube#videoListResponse`. |
| `etag` | `etag` | L'Etag de cette ressource. |
| `nextPageToken` | `string` | Le jeton qui peut être utilisé comme valeur du paramètre `pageToken` pour récupérer la page suivante dans l'ensemble de résultats. |
| `prevPageToken` | `string` | Le jeton qui peut être utilisé comme valeur du paramètre `pageToken` pour récupérer la page précédente dans l'ensemble de résultats. |
| `pageInfo` | `object` | L'objet `pageInfo` encapsule les informations de pagination pour l'ensemble de résultats. |
| `pageInfo.totalResults` | `integer` | Le nombre total de résultats dans l'ensemble de résultats. |
| `pageInfo.resultsPerPage` | `integer` | Le nombre de résultats inclus dans la réponse de l'API. |
| `items[]` | `list` | Une liste de vidéos correspondant aux critères de la requête. |

### Erreurs

Le tableau suivant identifie les messages d'erreur que l'API pourrait renvoyer en réponse à un appel de cette méthode. Consultez la documentation des [messages d'erreur](https://developers.google.com/youtube/v3/docs/errors) pour plus de détails.

| Type d'erreur | Détail de l'erreur | Description |
| --- | --- | --- |
| `badRequest (400)` | `videoChartNotFound` | Le graphique vidéo demandé n'est pas supporté ou n'est pas disponible. |
| `forbidden (403)` | `forbidden` | La requête n'est pas correctement autorisée pour accéder aux informations de fichier ou de traitement de la vidéo. Notez que les parties `fileDetails`, `processingDetails`, et `suggestions` ne sont disponibles que pour le propriétaire de la vidéo. |
| `forbidden (403)` | `forbidden` | La requête ne peut pas accéder aux informations de notation utilisateur. Cette erreur peut se produire parce que la requête n'est pas correctement autorisée pour utiliser le paramètre `myRating`. |
| `notFound (404)` | `videoNotFound` | La vidéo que vous essayez de récupérer ne peut pas être trouvée. Vérifiez la valeur du paramètre `id` de la requête pour vous assurer qu'elle est correcte. |

### Exemples

*Les exemples de code ont été supprimés.*

---

## Calculateur de Quota | YouTube Data API (v3) | Google pour les Développeurs

### Description

Le tableau ci-dessous montre le coût de quota pour appeler chaque méthode de l'API. Toutes les requêtes API, y compris les requêtes invalides, entraînent un coût de quota d'au moins une unité.

Les deux points suivants méritent d'être soulignés car ils affectent à la fois votre utilisation du quota :

- Si votre application appelle une méthode, telle que `search.list`, qui retourne plusieurs pages de résultats, chaque requête pour récupérer une page supplémentaire de résultats entraîne le coût de quota estimé.
- [YouTube Live Streaming API](https://developers.google.com/youtube/v3/live) méthodes sont, techniquement, partie de l'API YouTube Data, et les appels à ces méthodes entraînent également des coûts de quota. Par conséquent, les méthodes API pour le streaming en direct sont également listées dans le tableau.

### Coûts de Quota

| Ressource | Méthode | Coût |
| --- | --- | --- |
| **activities** | list | 1 |
| **captions** | list | 50 |
| &nbsp; | insert | 400 |
| &nbsp; | update | 450 |
| &nbsp; | delete | 50 |
| **channelBanners** | insert | 50 |
| **channels** | list | 1 |
| &nbsp; | update | 50 |
| **channelSections** | list | 1 |
| &nbsp; | insert | 50 |
| &nbsp; | update | 50 |
| &nbsp; | delete | 50 |
| **comments** | list | 1 |
| &nbsp; | insert | 50 |
| &nbsp; | update | 50 |
| &nbsp; | setModerationStatus | 50 |
| &nbsp; | delete | 50 |
| **commentThreads** | list | 1 |
| &nbsp; | insert | 50 |
| &nbsp; | update | 50 |
| **guideCategories** | list | 1 |
| **i18nLanguages** | list | 1 |
| **i18nRegions** | list | 1 |
| **members** | list | 1 |
| **membershipsLevels** | list | 1 |
| **playlistItems** | list | 1 |
| &nbsp; | insert | 50 |
| &nbsp; | update | 50 |
| &nbsp; | delete | 50 |
| **playlists** | list | 1 |
| &nbsp; | insert | 50 |
| &nbsp; | update | 50 |
| &nbsp; | delete | 50 |
| **search** | list | 100 |
| **subscriptions** | list | 1 |
| &nbsp; | insert | 50 |
| &nbsp; | delete | 50 |
| **thumbnails** | set | 50 |
| **videoAbuseReportReasons** | list | 1 |
| **videoCategories** | list | 1 |
| **videos** | list | 1 |
| &nbsp; | insert | 1600 |
| &nbsp; | update | 50 |
| &nbsp; | rate | 50 |
| &nbsp; | getRating | 1 |
| &nbsp; | reportAbuse | 50 |
| &nbsp; | delete | 50 |
| **watermarks** | set | 50 |
| &nbsp; | unset | 50 |

**Remarque :** Certaines méthodes peuvent avoir des coûts de quota très élevés (par exemple, `videos.insert` coûte 1600 unités). Il est essentiel de planifier et d'optimiser l'utilisation de votre quota en fonction des besoins de votre application.
