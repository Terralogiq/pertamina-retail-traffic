"""place_review_labels: taxonomy, row validation and the MERGE statement. Stdlib only; no BigQuery here.

Shared by reviews_job (--mode label, Gemini rows) and scripts/load_review_labels.py (manual rows). It lives in
reviews_job/ because the job image is built from that directory alone and cannot import scripts/; the loader
loads this file by path. Taxonomy and sentiment rules: docs/plans/complaints-analysis.md.
"""

TABLE = "place_review_labels"
KEYS = ("review_key", "method")
SENTIMENTS = ("neg", "mixed", "pos")
TAXONOMY = (
    "antrian", "pelayanan_petugas", "bbm_kosong", "kualitas_bbm", "takaran", "pembayaran",
    "harga", "kebersihan", "toilet", "fasilitas", "keamanan_lalu_lintas", "lainnya",
)

# (column, type). "X[]" = REPEATED. Staging columns and target columns share names and order.
STAGE = [
    ("review_key", "STRING"), ("site_id", "STRING"), ("labels", "STRING[]"), ("sentiment", "STRING"),
    ("praise_only", "BOOL"), ("gist", "STRING"), ("method", "STRING"), ("model_version", "STRING"),
    ("labeled_at", "TIMESTAMP"),
]


def check_unique(rows, keys):
    seen = set()
    for r in rows:
        k = tuple(r[c] for c in keys)
        if k in seen:
            raise ValueError(f"duplicate key {k}: a MERGE source must have one row per key")
        seen.add(k)


def check_label(item):
    """Raise ValueError when a label entry is not usable; the message never includes the gist."""
    key = item.get("review_key")
    if not isinstance(key, str) or not key:
        raise ValueError("entry without review_key")
    labels = item.get("labels")
    if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
        raise ValueError(f"{key}: labels must be a list of strings")
    bad = [x for x in labels if x not in TAXONOMY]
    if bad:
        raise ValueError(f"{key}: labels outside the taxonomy: {bad}")
    if item.get("sentiment") not in SENTIMENTS:
        raise ValueError(f"{key}: sentiment must be one of {SENTIMENTS}")
    if not isinstance(item.get("praise_only"), bool):
        raise ValueError(f"{key}: praise_only must be a boolean")
    if item["praise_only"] != (item["sentiment"] == "pos"):
        raise ValueError(f"{key}: praise_only must be true exactly when sentiment is pos")
    if not isinstance(item.get("gist"), str):
        raise ValueError(f"{key}: gist must be a string")


def merge_sql(target, source):
    """MERGE `source` (staging) into place_review_labels on (review_key, method); matched rows are overwritten."""
    cols = [s[0] for s in STAGE]
    non_key = [c for c in cols if c not in KEYS]
    on = " AND ".join(f"T.{k} = S.{k}" for k in KEYS)
    return (
        f"MERGE `{target}` T\nUSING `{source}` S\nON {on}\n"
        f"WHEN MATCHED THEN UPDATE SET {', '.join(f'{c} = S.{c}' for c in non_key)}\n"
        f"WHEN NOT MATCHED THEN INSERT ({', '.join(cols)}) VALUES ({', '.join(f'S.{c}' for c in cols)})"
    )
