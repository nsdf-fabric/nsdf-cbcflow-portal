import os
import datetime
import psycopg2
import psycopg2.extras

DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "cbcflow")
DB_USER = os.environ.get("DB_USER", "cbcflow")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "cbcflow")

ROOT_TABLE = "registry_superevent"

# Shared "reference" entities pointed to from many unrelated places (a LinkedFile
# can be a PEResult's config file *and* a CosmologyRun's run file; a Contributor
# can be an analyst on dozens of unrelated analyses). Expanding backward from
# these would pull in unrelated rows, so they're only ever embedded forward
# (i.e. when something else points *at* them), never expanded themselves.
LEAF_TABLES = {"registry_linkedfile", "registry_contributor"}

_fk_graph_cache = None


def GetConnection():
	return psycopg2.connect(
		host=DB_HOST, port=DB_PORT, dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD
	)


# //////////////////////////////////////////////////
def GetEvents():
	"""Returns all superevents (current state only, no history), newest first."""
	with GetConnection() as conn:
		with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
			cur.execute(f"""
				SELECT sname, schema_version, created_at, updated_at
				FROM {ROOT_TABLE}
				ORDER BY created_at DESC
			""")
			return [dict(row) for row in cur.fetchall()]


# //////////////////////////////////////////////////
# FK graph introspection (cached for the process lifetime: schema doesn't change at runtime)
# //////////////////////////////////////////////////

def _load_fk_graph(cur):
	global _fk_graph_cache
	if _fk_graph_cache is not None:
		return _fk_graph_cache

	cur.execute("""
		SELECT tc.table_name, kcu.column_name, ccu.table_name AS target_table
		FROM information_schema.table_constraints tc
		JOIN information_schema.key_column_usage kcu
			ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
		JOIN information_schema.constraint_column_usage ccu
			ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
		WHERE tc.constraint_type = 'FOREIGN KEY'
			AND tc.table_schema = 'public'
			AND tc.table_name LIKE 'registry_%%'
	""")

	forward = {}   # (table, column) -> target_table
	backward = {}  # target_table -> [(table, column), ...]
	for row in cur.fetchall():
		table, column, target_table = row["table_name"], row["column_name"], row["target_table"]
		forward[(table, column)] = target_table
		backward.setdefault(target_table, []).append((table, column))

	_fk_graph_cache = (forward, backward)
	return _fk_graph_cache


def _is_m2m_through(row, table, forward_fk):
	"""A pure Django M2M through-table: exactly 2 non-id columns, both of them FKs."""
	non_id_cols = [c for c in row if c != "id"]
	if len(non_id_cols) != 2:
		return False
	return all((table, c) in forward_fk for c in non_id_cols)


def _to_jsonable(value):
	if isinstance(value, (datetime.date, datetime.datetime)):
		return str(value)
	return value


# //////////////////////////////////////////////////
def _fetch_one(cur, table, row_id):
	cur.execute(f"SELECT * FROM {table} WHERE id=%s", (row_id,))
	row = cur.fetchone()
	return dict(row) if row else None


def _fetch_many(cur, table, col, value):
	cur.execute(f"SELECT * FROM {table} WHERE {col}=%s ORDER BY id", (value,))
	return [dict(row) for row in cur.fetchall()]


# //////////////////////////////////////////////////
def _walk(cur, table, row, visited, forward_fk, backward_fk):
	visited = visited | {table}
	out = {}

	fk_cols = {c for c in row if c.endswith("_id") and (table, c) in forward_fk}

	# scalar fields
	for col, val in row.items():
		if col == "id" or col in fk_cols:
			continue
		if col == "notes":
			out["notes"] = [line for line in (val or "").split("\n") if line.strip()]
		else:
			out[col] = _to_jsonable(val)

	# forward FKs: embed the single row this row points to
	for col in fk_cols:
		target_id = row[col]
		target_table = forward_fk[(table, col)]
		if target_id is None or target_table in visited:
			continue
		target_row = _fetch_one(cur, target_table, target_id)
		if target_row:
			out[col[:-3]] = _walk(cur, target_table, target_row, visited, forward_fk, backward_fk)

	# backward FKs: tables that point at this row (children this row "owns")
	if table not in LEAF_TABLES:
		table_suffix = table[len("registry_"):]
		for child_table, child_col in backward_fk.get(table, []):
			if child_table in visited:
				continue

			children = _fetch_many(cur, child_table, child_col, row["id"])
			if not children:
				continue

			if _is_m2m_through(children[0], child_table, forward_fk):
				child_suffix = child_table[len("registry_"):]
				# Only follow the M2M edge from the "owning" side: Django names
				# through-tables registry_<owner>_<fieldname>, so the owner's
				# suffix must prefix the through-table's suffix.
				if not child_suffix.startswith(table_suffix + "_"):
					continue
				field_name = child_suffix[len(table_suffix) + 1:]
				other_col = next(c for c in children[0] if c != "id" and c != child_col)
				other_table = forward_fk[(child_table, other_col)]

				items = []
				for child_row in children:
					other_id = child_row[other_col]
					if other_id is None:
						continue
					other_row = _fetch_one(cur, other_table, other_id)
					if other_row:
						items.append(_walk(cur, other_table, other_row, visited | {child_table}, forward_fk, backward_fk))
				if items:
					out[field_name] = items
			else:
				key = child_table[len("registry_"):]
				out[key] = [_walk(cur, child_table, c, visited, forward_fk, backward_fk) for c in children]

	return out


# //////////////////////////////////////////////////
def GetEvent(sname):
	"""Builds the full nested superevent document on the fly by walking the FK graph."""
	with GetConnection() as conn:
		with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
			forward_fk, backward_fk = _load_fk_graph(cur)

			cur.execute(f"SELECT * FROM {ROOT_TABLE} WHERE sname=%s", (sname,))
			row = cur.fetchone()
			if not row:
				return None
			row = dict(row)

			event = _walk(cur, ROOT_TABLE, row, set(), forward_fk, backward_fk)
			return {
				"Sname": row["sname"],
				"created_at": str(row["created_at"]),
				"updated_at": str(row["updated_at"]),
				"event": event,
			}
