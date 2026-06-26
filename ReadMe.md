# Instructions

**KEEP THIS REPO PRIVATE**

```bash

# if you are NOT on WSL2
#  add `-d` to run in background
docker compose down && docker compose up --build 

# if you are on WSL2 (you need `bridge` mode)
#  add `-d` to run in background
docker compose down && docker compose -f docker-compose.yml -f docker-compose.wsl2.yml up --build 

# docker compose run
# docker compose run web /bin/bash
```

Test:

```
# http://localhost:5077
# USERNAME demo
# PASSWORD xxxx
```

# FK graph diagram

Regenerate after a DB schema change:

```bash
docker run --rm --network host -v "$PWD":/app -w /app python:3 bash -c "pip install -q psycopg2-binary && python3 build_fk_graph.py fk_graph"
docker run --rm -v "$PWD":/app -w /app fgrehm/graphviz dot -Tpng fk_graph.dot -o fk_graph.png
```

# Quickview visualization

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
