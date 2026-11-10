# État du projet — 10 novembre 2026

Application Next.js/MapLibre et FastAPI, traitement en mémoire sans stockage permanent des observations.

- Analyses officielles New York et San Francisco validées lors des intégrations précédentes.
- Recherche Web Tavily opérationnelle ; modèle OpenRouter configuré séparément par l’opérateur.
- Boucle de recherche bornée et inspection sans IA de secours en cas d’indisponibilité du modèle.
- Lecteurs CSV/XLSX/JSON/GeoJSON et contrôles déterministes disponibles. Une nouvelle source ne devient pas automatiquement un connecteur scientifique validé.
- Le dernier essai de découverte sur Vienne a rencontré HTTP 429 côté modèle. Une analyse mondiale autonome complète n’est pas démontrée.
- Vérification du 10 novembre : 170 tests backend réussis, 2 tests live exclus. Les 13 tests frontend avaient réussi précédemment. Les dernières relances du build et des tests live n’ont pas de résultat récupérable et ne sont pas déclarées validées.

Les documents de vérification antérieurs décrivent leurs propres dates de test. Les clés Census, OpenRouter et Tavily sont exclues du dépôt ; renseigner un fichier `.env` local d’après `.env.example`.
