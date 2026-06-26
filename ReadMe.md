# Intro


Links:
- https://github.com/nsdf-fabric/nsdf-cbcflow-portal
- https://uofutah-my.sharepoint.com/:p:/r/personal/u0632547_umail_utah_edu1/_layouts/15/Doc.aspx?sourcedoc=%7BD6BFB766-61AD-4790-93F8-ADF3C49D9F52%7D&file=presentation.cbcflow-postgres-update.pptx&action=edit&mobileredirect=true

**Fist you need to have a cbcflow-portal directory one level up, because you need the Postgres db up and running. Follow instructions in `ReadMe.nsdf.md`**

Notes:
- Fixed a problem with bridged connections specific to WSL2
- new workflow lost the "commit" idea (so we don't need to track the differences). Ask/advice!?
	- we basically are loosing all the history and the diff viewer
- database will be read-only. Dropped the createEvent and schema verification
- The new logic is
    - db.py traverse the database trying to find forward/backward connections. So it;s easy to maintain if the db changes
    - it creates a JSON file 
    - then the view render it in HTML-friendly style with expandable/collapsible title

```bash
cd nsdf-cbcflow-portal
```

This service has **no `.env` of its own** — all secrets (`APP_*` and `POSTGRES_*`)
live in `../cbcflow-portal/.env`. Either point compose at it with `--env-file`
(shown below), or create a symlink once:

```bash
ln -s ../cbcflow-portal/.env .env
```

On CHPC the daemon needs root, so prefix commands with `sudo` and pass the parent
env file:

```bash
sudo docker compose --env-file ../cbcflow-portal/.env -f docker-compose.yml down
sudo docker compose --env-file ../cbcflow-portal/.env -f docker-compose.yml up -d --build
```

If you are on WSL2 (you need `bridge` mode, and no `sudo`):

```bash
docker compose --env-file ../cbcflow-portal/.env down
docker compose --env-file ../cbcflow-portal/.env -f docker-compose.yml -f docker-compose.wsl2.yml up --build
```

To run a special command:

```bash
sudo docker compose --env-file ../cbcflow-portal/.env run web /bin/bash
```

Test  http://chpc1.nationalsciencedatafabric.org:5077  


## FK graph diagram

Regenerate after a DB schema change.

Step 1 builds `fk_graph.dot` by querying Postgres:

```bash
sudo docker run --rm --network host \
  --env-file ../cbcflow-portal/.env \
    -v "$PWD":/app \
    -w /app python:3 bash -c \
    "pip install -q psycopg2-binary && python3 build_fk_graph.py fk_graph"
```

Step 2 just renders the `.dot` into a PNG. :

```bash
sudo docker run --rm \
   -v "$PWD":/app \
   -w /app \
   fgrehm/graphviz dot \
   -Tpng \
   fk_graph.dot \
   -o fk_graph.png
```

## Quickview visualization

- https://github.com/gwosc-tutorial/quickview.git
- https://colab.research.google.com/github/losc-tutorial/quickview/blob/master/index.ipynb

```bash
cd quickview
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
python3 -m jupyter lab .
python3 -m panel serve index.ipynb
```


