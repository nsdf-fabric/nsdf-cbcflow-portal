"""Renders a PNG diagram of the registry_* foreign-key graph that db.py walks.

Re-run this any time the cbcflow Postgres schema changes - nothing here is
hardcoded to specific table/model names, so it stays correct automatically:

    python3 build_fk_graph.py [output_basename]

Requires the same DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD env vars as
db.py (see its defaults). Needs the `dot` command (graphviz) on PATH to
produce the PNG; otherwise it just writes the .dot file, which you can
render elsewhere, e.g.:

    docker run --rm -v "$PWD":/app -w /app fgrehm/graphviz \\
        dot -Tpng fk_graph.dot -o fk_graph.png
"""

import collections
import shutil
import subprocess
import sys

import psycopg2.extras

import db

LEAF_TABLES = db.LEAF_TABLES  # never expand backward from these (see db.py)


def _fetch_fk_edges(cur):
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
	return [(r["table_name"], r["column_name"], r["target_table"]) for r in cur.fetchall()]


def _fetch_column_counts(cur):
	cur.execute("""
		SELECT table_name, count(*) AS n
		FROM information_schema.columns
		WHERE table_schema='public' AND table_name LIKE 'registry_%%'
		GROUP BY table_name
	""")
	return {r["table_name"]: r["n"] for r in cur.fetchall()}


def _is_m2m_through(table, cols, colcount):
	"""A pure Django M2M through-table: exactly 2 non-id columns, both FKs."""
	return colcount.get(table) == 3 and len(cols) == 2


def _short(name):
	return name[len("registry_"):] if name.startswith("registry_") else name


def build_edges(fk_edges, colcount):
	"""Classifies raw FK edges into plain forward edges and (collapsed) M2M edges,
	following the exact same rules db.py's _walk() uses to decide what to embed."""
	by_table = collections.defaultdict(list)
	for table, column, target in fk_edges:
		by_table[table].append((column, target))

	plain_edges = set()   # (table, target, label)
	m2m_edges = set()     # (owner_table, target_table, field_label)

	for table, cols in by_table.items():
		if _is_m2m_through(table, cols, colcount):
			table_suffix = _short(table)
			owner_target, other_target, field = None, None, None
			for col, tgt in cols:
				tgt_suffix = _short(tgt)
				if table_suffix.startswith(tgt_suffix + "_"):
					owner_target, field = tgt, table_suffix[len(tgt_suffix) + 1:]
				else:
					other_target = tgt
			if owner_target and other_target:
				m2m_edges.add((owner_target, other_target, field))
				continue
		for col, tgt in cols:
			label = col[:-3] if col.endswith("_id") else col
			plain_edges.add((table, tgt, label))

	return plain_edges, m2m_edges


def _signature(table, plain_edges, m2m_edges):
	"""Tables that play an identical structural role - same outgoing edges AND
	same incoming edges - collapse into one diagram node. This is what
	generically catches repeated patterns like the 18 near-identical
	TestingGR analysis tables, without hardcoding any table names.

	Incoming edges matter too: e.g. testinggrdata and catalogtrackingdata
	both have a single outgoing edge (-> superevent) and would wrongly merge
	if only outgoing edges were compared; what actually distinguishes them is
	who points *at* them (18 analysis tables vs. 2 status tables)."""
	out_fwd = tuple(sorted((label, tgt) for (src, tgt, label) in plain_edges if src == table))
	out_m2m = tuple(sorted((label, tgt) for (src, tgt, label) in m2m_edges if src == table))
	in_fwd = tuple(sorted((label, src) for (src, tgt, label) in plain_edges if tgt == table))
	in_m2m = tuple(sorted((label, src) for (src, tgt, label) in m2m_edges if tgt == table))
	return (out_fwd, out_m2m, in_fwd, in_m2m)


def collapse_structurally_identical(tables, plain_edges, m2m_edges):
	"""Groups tables sharing an identical signature into one meta-node each.
	Singletons (signature shared by only one table) are left as themselves."""
	groups = collections.defaultdict(list)
	for t in tables:
		groups[_signature(t, plain_edges, m2m_edges)].append(t)

	rename = {}
	for members in groups.values():
		if len(members) == 1:
			rename[members[0]] = _short(members[0])
		else:
			label = f"{_short(sorted(members)[0])}-like ({len(members)}x)"
			for t in members:
				rename[t] = label
	return rename


def build_dot(fk_edges, colcount):
	plain_edges, m2m_edges = build_edges(fk_edges, colcount)

	tables = set()
	for a, b, _ in plain_edges | m2m_edges:
		tables.add(a); tables.add(b)

	rename = collapse_structurally_identical(tables, plain_edges, m2m_edges)

	collapsed_plain = {(rename[a], rename[b], label) for a, b, label in plain_edges}
	collapsed_m2m = {(rename[a], rename[b], label) for a, b, label in m2m_edges}

	nodes = set()
	for a, b, _ in collapsed_plain | collapsed_m2m:
		nodes.add(a); nodes.add(b)

	lines = []
	lines.append("digraph FKGraph {")
	lines.append('  rankdir=LR;')
	lines.append('  graph [fontsize=11, nodesep=0.35, ranksep=0.9, splines=true, overlap=false, dpi=150, size="40,40"];')
	lines.append('  node [shape=box, style=filled, fontname="Helvetica", fontsize=11];')

	for n in sorted(nodes):
		if n in {_short(t) for t in LEAF_TABLES}:
			color = "#ffe0b3"
		elif n == _short(db.ROOT_TABLE):
			color = "#cfe8ff"
		elif "x)" in n:
			color = "#f3e5f5"
		else:
			color = "#e8f5e9"
		lines.append(f'  "{n}" [fillcolor="{color}"];')

	for a, b, label in sorted(collapsed_plain):
		lines.append(f'  "{a}" -> "{b}" [label="{label}", color="#666666", fontsize=9];')

	for a, b, label in sorted(collapsed_m2m):
		lines.append(f'  "{a}" -> "{b}" [label="{label}", color="#cc6600", style=dashed, fontsize=9];')

	lines.append("}")
	return "\n".join(lines)


def main():
	out_base = sys.argv[1] if len(sys.argv) > 1 else "fk_graph"

	with db.GetConnection() as conn:
		with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
			fk_edges = _fetch_fk_edges(cur)
			colcount = _fetch_column_counts(cur)

	dot_src = build_dot(fk_edges, colcount)
	dot_path = f"{out_base}.dot"
	with open(dot_path, "w") as f:
		f.write(dot_src)
	print(f"Wrote {dot_path}")

	if shutil.which("dot"):
		png_path = f"{out_base}.png"
		subprocess.run(["dot", "-Tpng", dot_path, "-o", png_path], check=True)
		print(f"Wrote {png_path}")
	else:
		print("graphviz 'dot' not found on PATH. Render the .dot file separately, e.g.:")
		print(f'  docker run --rm -v "$PWD":/app -w /app fgrehm/graphviz dot -Tpng {dot_path} -o {out_base}.png')


if __name__ == "__main__":
	main()
