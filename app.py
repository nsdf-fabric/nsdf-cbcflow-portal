
import os,json
import db

USERNAME=os.environ["APP_USERNAME"]
PASSWORD=os.environ["APP_PASSWORD"]
SECRET_KEY=os.environ["APP_SECRET_KEY"]


# //////////////////////////////////////////////////
import flask
from flask import Flask, Response

app = flask.Flask(__name__)
flask.json.provider.DefaultJSONProvider.sort_keys = False

app.config['SECRET_KEY'] = SECRET_KEY
app.config['JSON_SORT_KEYS'] = False
app.json.sort_keys = False


# //////////////////////////////////////////////////
# https://blog.teclado.com/protecting-endpoints-in-flask-apps-by-requiring-login/

import functools
from flask import Flask, session, redirect, url_for, request, abort

@app.route("/login", methods=('GET', 'POST'))
def login():
	if request.method == 'POST':
		username = request.form.get('username')
		password = request.form.get('password')    
		if username==USERNAME and password == PASSWORD:
			session['username'] = username
			return redirect('/')
		else:
				return abort(401)
	else:
		return flask.render_template('login.html')

def login_required(func):
	@functools.wraps(func)
	def secure_function(*args, **kwargs):
			if "username" not in session:
				return redirect(url_for("login"))
			return func(*args, **kwargs)
	return secure_function

@app.route('/logout')
@login_required
def logout():
	if "username" in session:
		del session['username'] 
	return flask.render_template('logout.html')

# //////////////////////////////////////////////////
@app.route('/')
@login_required
def home_page():
		return flask.render_template('index.html', events=db.GetEvents()[0:100],)

# //////////////////////////////////////////////////
@app.route('/static/{filename}')
@login_required
def favicon(filename:str):
	return flask.send_from_directory(os.path.join(app.root_path,"static"), filename)

# //////////////////////////////////////////////////
@app.route('/json/<Sname>')
@login_required
def GetJSonTest(Sname:str):
	row=db.GetEvent(Sname)
	return flask.jsonify(row["event"] if row else None)

# //////////////////////////////////////////////////
@app.route('/event')
@login_required
def GetEventsPage():
	events=[it["sname"] for it in db.GetEvents()]
	return flask.render_template('events.html', events=events)

# //////////////////////////////////////////////////
# HTML tree view: a collapsible <details>/<summary> rendering of the nested
# event dict, with indentation showing depth. Two ergonomic unwrap rules keep
# it from being noisy, since db.py's generic walker always wraps relationships
# in lists/dicts even when there's conceptually just one value:
#   - a single-item list renders as if it were just that item (no "(1)" wrapper)
#   - a single-field dict (e.g. a Contributor {"name": "X"}) renders inline as
#     its one value, instead of an extra expandable level
import html as _html

def IsUrl(value:str)->bool:
	from urllib.parse import urlparse
	try:
		return urlparse(value.strip()).scheme in ("http","https")
	except Exception:
		return False

def RenderFinal(value)->str:
	text=str(value).strip()
	if IsUrl(text):
		return f"<a href='{_html.escape(text)}'>link</a>"
	return _html.escape(text)

def _PrettyKey(key:str)->str:
	if not key or key.startswith("#"):
		return key
	return key.replace("_"," ").strip().title()

EXPAND_LEVELS=1  # how many wrapper levels from the root default to expanded

def _ScalarCell(value)->str:
	"""Renders a table cell for a plain scalar, or a multi-item scalar list joined inline."""
	if isinstance(value, list):
		items=[RenderFinal(it) for it in value if str(it).strip()]
		return "; ".join(items) if items else ""
	if value is None:
		return ""
	text=str(value).strip()
	return RenderFinal(value) if text else ""

def _Unwrap(value):
	"""Strips the noise db.py's generic walker always adds - single-item lists
	and single-field dicts (e.g. a Contributor {"name": "X"}) - down to whatever
	real value/structure is underneath, so callers don't render a wrapper level
	for something that isn't really a nested structure."""
	while True:
		if isinstance(value, list) and len(value)==1:
			value=value[0]
			continue
		if isinstance(value, dict) and len(value)==1:
			value=next(iter(value.values()))
			continue
		return value

def _IsFlatDict(d)->bool:
	"""True if every field of d is itself a plain scalar (after unwrapping), or
	an empty/vacuous container - i.e. d has no real nested structure, so a row
	of a transposed table can show it."""
	def is_flat_value(v):
		v=_Unwrap(v)
		return not isinstance(v,(dict,list)) or len(v)==0
	return isinstance(d,dict) and all(is_flat_value(v) for v in d.values())

def _RenderTransposed(key:str, items:list, level:int)->str:
	"""Compact table for a list of same-shaped flat dicts: one row per field,
	one column per item - e.g. 4 GraceDB pipeline events side by side, instead
	of 4 separate expandable cards each repeating the same ~20 field names."""
	ordered_keys=[]
	for it in items:
		for k in it.keys():
			if k not in ordered_keys:
				ordered_keys.append(k)

	rows=[]
	for k in ordered_keys:
		cells="".join(f"<td>{_ScalarCell(_Unwrap(it.get(k)))}</td>" for it in items)
		rows.append(f"<tr><td class='key'>{_html.escape(_PrettyKey(k))}</td>{cells}</tr>")

	header="<th></th>"+"".join(f"<th>#{i}</th>" for i in range(1,len(items)+1))
	table_html=f"<table class='kv transposed'><tr>{header}</tr>{''.join(rows)}</table>"
	open_attr="open" if level<=EXPAND_LEVELS else ""
	return f"<details {open_attr}><summary>{_html.escape(_PrettyKey(key))} <span class='count-badge'>{len(items)}</span></summary><div class='indent'>{table_html}</div></details>"

def RenderNode(key:str, value, level:int=0)->str:
	value=_Unwrap(value)

	if isinstance(value, list):
		if len(value)==0:
			return ""
		value=[_Unwrap(it) for it in value]
		if all(not isinstance(it,(dict,list)) for it in value):
			cell=_ScalarCell(value)
			return f"<div class='field'><b>{_html.escape(_PrettyKey(key))}:</b> {cell}</div>" if cell else ""
		if all(_IsFlatDict(it) for it in value):
			return _RenderTransposed(key, value, level)
		parts=[RenderNode(f"#{i}", it, level+1) for i,it in enumerate(value,1)]
		parts=[p for p in parts if p]
		if not parts:
			return ""
		inner="".join(parts)
		open_attr="open" if level<=EXPAND_LEVELS else ""
		return f"<details {open_attr}><summary>{_html.escape(_PrettyKey(key))} <span class='count-badge'>{len(value)}</span></summary><div class='indent'>{inner}</div></details>"

	if isinstance(value, dict):
		scalar_rows=[]
		nested_parts=[]
		for k,v in value.items():
			v=_Unwrap(v)
			if isinstance(v,(dict,list)):
				sub=RenderNode(k, v, level+1)
				if sub:
					nested_parts.append(sub)
			else:
				cell=_ScalarCell(v)
				if cell:
					scalar_rows.append((k,cell))

		table_html=""
		if scalar_rows:
			rows="".join(f"<tr><td class='key'>{_html.escape(_PrettyKey(k))}</td><td>{cell}</td></tr>" for k,cell in scalar_rows)
			table_html=f"<table class='kv'>{rows}</table>"

		inner=table_html+"".join(nested_parts)
		if not inner:
			return ""
		if not key:
			return f"<div class='indent'>{inner}</div>"
		open_attr="open" if level<=EXPAND_LEVELS else ""
		return f"<details {open_attr}><summary>{_html.escape(_PrettyKey(key))}</summary><div class='indent'>{inner}</div></details>"

	cell=_ScalarCell(value)
	return f"<div class='field'><b>{_html.escape(_PrettyKey(key))}:</b> {cell}</div>" if cell else ""

# //////////////////////////////////////////////////
@app.route('/event/<Sname>')
@login_required
def GetEventPage(Sname):
	row=db.GetEvent(Sname)
	if row is None:
		abort(404)
	html_view=RenderNode("", row["event"])
	return flask.render_template('event.html', Sname=Sname, html_view=html_view, created_at=row["created_at"], updated_at=row["updated_at"])



