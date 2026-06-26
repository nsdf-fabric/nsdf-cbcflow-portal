# Instructions

Quickview visualization:
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