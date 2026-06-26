# Instructions

Links:
- https://github.com/jkanner/streamlit-dataview
- https://gw-quickview.streamlit.app/
- https://zenodo.org/records/8177023/preview/GWTC3p0PEDataReleaseExample.ipynb?include_deleted=0
- https://lscsoft.docs.ligo.org/pesummary/stable/what_is_pesummary.html

To get the data (several GBs):

```bash
cd pe_viewer
python3 -m pip install zenodo_get
zenodo_get 8177023
```

To run:

```bash
cd pe_viewer
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt

# takes a lot to preview the panel dashboard
python3 -m jupyter lab .

python3 -m panel serve example.ipynb
```