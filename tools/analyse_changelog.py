#!/usr/bin/env python3
"""Analyse floor796-kiosk changelog.json empirically. Stdlib-only.

Output: prints structured summary + writes docs/dataset-analysis.md
"""

import json, re, random, math
from collections import Counter, defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "vendor" / "changelog.json"
if not DATA.exists():
    DATA = Path("vendor/changelog.json")

with open(DATA) as f:
    objs = json.load(f)

N = len(objs)
OUTDIR = Path(__file__).resolve().parent.parent / "docs"
OUTDIR.mkdir(parents=True, exist_ok=True)

# =====================================================================
# 1. OBJECT COUNT & KEY SCHEMA
# =====================================================================
key_sets = sorted({frozenset(o.keys()) for o in objs})
KS = []
for ks in key_sets:
    KS.append((len([o for o in objs if frozenset(o.keys()) == ks]), sorted(ks)))

no_l = [o['id'] for o in objs if 'l' not in o]
no_t = [o['id'] for o in objs if 't' not in o]
no_m = [o['id'] for o in objs if 'm' not in o]
no_a = [o['id'] for o in objs if 'a' not in o]

# =====================================================================
# 2. P-GRAMMAR ANALYSIS
# =====================================================================
# Grammar: {b|t}{digit}{l|r}{digit},{x},{y}
# No 4-tuple – the "row" mentioned in the task spec is actually a layer number
SEGS_RE = re.compile(r'^([bt])(\d)([lr])(\d+),(\d+),(\d+)$')

# Collect ALL unique segment strings
all_unique_segs = set()
seg_type_counter = Counter()   # "b/l", "b/r", "t/l", "t/r"
all_coords = []                # (prefix, digit, lr, layer_idx, x, y)

for o in objs:
    p = o.get('p', '')
    if not p:
        continue
    parts = p.split(';')
    for seg in parts:
        seg = seg.strip()
        if seg == 'z' or not seg:
            continue
        all_unique_segs.add(seg)
        m = SEGS_RE.fullmatch(seg)
        if m:
            prefix, d, lr, idx, x, y = m.group(1), int(m.group(2)), m.group(3), int(m.group(4)), int(m.group(5)), int(m.group(6))
            seg_type_counter[f"{prefix}/{lr}"] += 1
            all_coords.append((prefix, d, lr, idx, x, y))

malformed_segs = []
for s in all_unique_segs:
    if not SEGS_RE.fullmatch(s):
        malformed_segs.append(s)

# Parse per-object: count segments, collect (layer_key) hits
layer_hits = Counter()  # (prefix, digit, lr, idx) → how many coords target it
obj_seg_counts = []
p_strings_set = set()

for o in objs:
    p = o.get('p', '')
    p_strings_set.add(p)
    parts = [s.strip() for s in p.split(';') if s.strip() and s.strip() != 'z']
    obj_seg_counts.append(len(parts))
    for seg in parts:
        m = SEGS_RE.fullmatch(seg)
        if m:
            key = (m.group(1), int(m.group(2)), m.group(3), int(m.group(4)))
            layer_hits[key] += 1

# Normalised p-shape = count + type mix
def norm_p_shape(p_str):
    parts = [s.strip() for s in p_str.split(';') if s.strip() and s.strip() != 'z']
    types = Counter()
    for seg in parts:
        m = SEGS_RE.fullmatch(seg)
        if m:
            types[m.group(1)+m.group(3)] += 1
        else:
            types['???'] += 1
    return str(sorted(types.items()))

shape_counter = Counter(norm_p_shape(p) for p in p_strings_set)

# Numeric ranges
prefixes = [c[0] for c in all_coords]
digits = [c[1] for c in all_coords]
lrs = [c[2] for c in all_coords]
layer_idxs = [c[3] for c in all_coords]
xs = [c[4] for c in all_coords]
ys = [c[5] for c in all_coords]

sc_counter = Counter(obj_seg_counts)

# =====================================================================
# 3. LINK DISTRIBUTION
# =====================================================================
YT_RE = re.compile(r'(youtube\.com|youtu\.be)/', re.I)
WIKI_RE = re.compile(r'(wikipedia\.org|wiki)', re.I)
IMGUR_RE = re.compile(r'(imgur\.com)', re.I)
IMAGE_EXT = re.compile(r'\.(jpe?g|png|gif|webp|bmp|svg|avif)\b', re.I)
FLOOR_PREFIX = re.compile(r'https://floor796\.com/', re.I)

link_types = Counter()
no_link_ids = []
for o in objs:
    l = o.get('l', None)
    if l is None or (isinstance(l, str) and l.strip() == ''):
        no_link_ids.append(o['id'])
        link_types['none'] += 1
        continue
    if isinstance(l, list):
        lstr = ';'.join(str(v) for v in l)
    else:
        lstr = str(l)
    if YT_RE.search(lstr):
        link_types['youtube'] += 1
    elif WIKI_RE.search(lstr):
        link_types['wikipedia'] += 1
    elif IMGUR_RE.search(lstr):
        link_types['imgur'] += 1
    elif FLOOR_PREFIX.match(lstr):
        link_types['floor796_direct'] += 1
    elif IMAGE_EXT.search(lstr):
        link_types['direct_image'] += 1
    elif lstr.startswith('data:image/'):
        link_types['base64_image'] += 1
    else:
        link_types['other'] += 1

# =====================================================================
# 4. TITLE ESCAPING ISSUES
# =====================================================================
special_chars = {}
title_lens = []
for o in objs:
    t = o.get('t', '')
    title_lens.append(len(t))
    issues = []
    if '<' in t or '>' in t:
        issues.append('HTML-angle-brackets')
    if '&' in t and not re.search(r'&(amp|lt|gt|quot|#\d+);', t):
        issues.append('bare-ampersand')
    if '"' in t:
        issues.append('double-quote')
    if "'" in t:
        issues.append('single-quote')
    if '\n' in t or '\r' in t or '\t' in t:
        issues.append('whitespace-newline/tab')
    if any(ord(c) > 127 for c in t):
        issues.append('non-ascii-unicode')
    if len(t) > 120:
        issues.append(f'too-long ({len(t)} chars)')
    if issues:
        special_chars[o['id']] = (t, issues)

# =====================================================================
# 5. SAMPLES
# =====================================================================
random.seed(42)
samples = random.sample(objs, min(10, N))

# =====================================================================
# WRITE REPORT
# =====================================================================
report = []
r = report.append

r(f"# Dataset Analysis: changelog.json\n")
r(f"**Source:** `vendor/changelog.json` from [arionl/floor796-kiosk](https://github.com/arionl/floor796-kiosk)\n")
r(f"**Generated by:** `tools/analyse_changelog.py`\n")

r(f"---\n")
r(f"## 1. Object Count & Schema\n")
r(f"- **Total objects:** `{N}`\n")
r(f"- Each object always contains keys: `a`, `d`, `id`, `l`, `m`, `p`, `t`\n")
r(f"- Key combinations found:\n")
for count, keys in sorted(KS, key=lambda x: -x[0]):
    r(f"  - All {count} objects have exactly {{{', '.join(keys)}}}\n")

r(f"- Objects missing specific keys:\n")
r(f"  - `l` (link): {len(no_l)}\n")
r(f"  - `t` (title): {len(no_t)}\n")
r(f"  - `m` (meta): {len(no_m)}\n")
r(f"  - `a` (author): {len(no_a)}\n")

r(f"\n## 2. Field Details\n")
r(f"### `d` (date)\n")
dates = [o['d'] for o in objs]
unique_dates = sorted(set(dates))
r(f"- Total unique dates: {len(unique_dates)}")
r(f"\n- Date range: {min(unique_dates)} → {max(unique_dates)}\n")
r(f"- Top 10 dates by frequency:\n")
for dt, cnt in Counter(dates).most_common(10):
    r(f"  - `{dt}`: {cnt} objects\n")

r(f"### `m` (boolean meta flag)\n")
m_vals = [o['m'] for o in objs]
r(f"- `m=1`: {sum(m_vals)} objects ({100*sum(m_vals)/N:.1f}%)\n")
r(f"- `m=0`: {N - sum(m_vals)} objects ({100*(N-sum(m_vals))/N:.1f}%)\n")

r(f"### `a` (author field)\n")
a_vals = [o.get('a', '') for o in objs]
a_nonempty = sum(1 for a in a_vals if a)
r(f"- Non-empty: {a_nonempty}/{N} ({100*a_nonempty/N:.1f}%)\n")
if a_nonempty:
    r(f"- Authors seen: {sorted(set(a_vals))}\n")

r(f"\n## 3. P-Grammar (Position Strings)\n")
r(f"### Grammar Structure\n")
r("The `p` field is a semicolon-delimited list of pixel-position points.")
r("")
r("**Format:** `{letter}{digit}{LR}{idx},{x},{y}`")
r("- `letter` = `b` (block) or `t` (tile/room)")
r("- `digit` = layer/block index (0–6 for tiles, 1–3 for blocks)")
r("- `LR` = `l` (layer reference) or `r` (room reference)")
r("- `idx` = numeric identifier for that layer/room")
r("- `x`,`y` = absolute pixel coordinates within the scene")
r("")
r("The string is NOT `b{block}r{row},{x},{y}` as some docs suggest;")
r("it uses a two-letter prefix scheme: `bl{idx}`, `br{idx}`, `tl{idx}`, `tr{idx}`, etc.")

r(f"### Segment Type Distribution\n")
for stype, cnt in seg_type_counter.most_common():
    r(f"- `{stype}`: {cnt} segments\n")

r(f"\n### Unique Segments: {len(all_unique_segs)}\n")
r(f"Malformed segments (do not match grammar): {len(malformed_segs)}\n")
if malformed_segs:
    r(f"**MALFORMED ENTRY EXAMPLES:**\n")
    for s in malformed_segs[:15]:
        r(f"  - `{s}`\n")
    if len(malformed_segs) > 15:
        r(f"  ... and {len(malformed_segs)-15} more\n")

r(f"\n### Per-Object Segment Counts\n")
total_segments = sum(obj_seg_counts)
r(f"- Total segment occurrences across all objects: {total_segments}\n")
r(f"- Objects with ≥1 segment: {sum(1 for c in obj_seg_counts if c > 0)}\n")
r(f"- Objects with 0 segments (empty p): {sum(1 for c in obj_seg_counts if c == 0)}\n")
r(f"\nSegment count histogram:\n")
r(f"| Segments | Objects | % |\n")
r(f"|----------+---------+----|\n")
for k in sorted(sc_counter):
    pct = 100 * sc_counter[k] / N
    r(f"| {k:>6} | {sc_counter[k]:>7} | {pct:.1f}% |\n")

r(f"\nMean segments/object: {total_segments/N:.1f}, Median: {sorted(obj_seg_counts)[N//2]}\n")

r(f"### Unique `p` Shapes (by segment-type composition): {len(shape_counter)}\n")
r(f"| Shape (type breakdown) | Objects | Examples |\n")
r(f"|------------------------+---------+----------|\n")
for shape, cnt in shape_counter.most_common(15):
    example = ""
    for p in p_strings_set:
        if norm_p_shape(p) == shape:
            example = repr(p[:80])
            break
    r(f"| {shape:<40} | {cnt:>7} | {example} |\n")

r(f"\n### Numeric Ranges (from parsed segments)\n")
r(f"| Field | Min | Max | Range |\n")
r(f"|-------+-----+-----+-------|\n")
r(f"| prefix digit (b/t index) | {min(digits):>2} | {max(digits):>2} | {max(digits)-min(digits)+1} values |\n")
r(f"| layer index (`idx`) | {min(layer_idxs):>4} | {max(layer_idxs):>4} | {max(layer_idxs)-min(layer_idxs)+1} values |\n")
r(f"| x (pixel) | {min(xs):>4} | {max(xs):>4} | |\n")
r(f"| y (pixel) | {min(ys):>4} | {max(ys):>4} | |\n")

r(f"\n### Top 20 Most-Referenced Layers by Coord Hit Count\n")
r(f"| Prefix+Digit+LR+Idx | Hits | Description |\n")
r(f"|---------------------+------+-------------|\n")
for key, cnt in layer_hits.most_common(20):
    desc = f"{key[0]}{key[1]}-{key[2]}={key[3]}"
    r(f"| {desc} | {cnt:>4} | layer/room ref |\n")

r(f"\n## 4. Link Distribution\n")
r(f"| Type | Count | % |\n")
r(f"|------+-------+----|\n")
for lt, cnt in sorted(link_types.items(), key=lambda x: -x[1]):
    r(f"| {lt:<25} | {cnt:>5} | {100*cnt/N:.1f}% |\n")
r(f"\n**Objects with no link at all:** {len(no_link_ids)}\n")
r(f"**Example IDs with no link:** {no_link_ids[:10]}\n")

# Sample floor796 direct URLs
floor_urls = [l for o in objs for l in ([o['l']] if isinstance(o.get('l'), str) else o.get('l', []))
              if isinstance(l, str) and FLOOR_PREFIX.match(l)]
sample_floor = list(dict.fromkeys(floor_urls))[:5]
r(f"\nSample `floor796.com` direct image URLs:\n")
for u in sample_floor:
    r(f"  - `{u}`\n")

r(f"\n## 5. Title Escaping Issues\n")
issue_types = Counter()
for tid, (title, issues) in special_chars.items():
    for iss in issues:
        issue_types[iss] += 1
r(f"| Issue | Count |\n")
r(f"|-------+------|\n")
for iss, cnt in issue_types.most_common():
    r(f"| {iss:<35} | {cnt:>5} |\n")

if special_chars:
    r(f"\n**Title length stats:** mean={sum(title_lens)/len(title_lens):.1f}, "
      f"min={min(title_lens)}, max={max(title_lens)}, median={sorted(title_lens)[N//2]}\n")
    r(f"\nProblematic title samples:\n")
    shown = 0
    for tid, (title, issues) in list(special_chars.items())[:10]:
        r(f"  - id={tid}: `{title}` — {issues}\n")
        shown += 1

r(f"\n## 6. Random Sample Objects (10)\n")
for i, o in enumerate(samples):
    r(f"### Object {i+1} (id={o['id']})\n")
    r(f"```json\n{json.dumps(o, ensure_ascii=False, indent=2)}\n```\n")

# =====================================================================
# SAVE REPORT
# =====================================================================
report_path = OUTDIR / "dataset-analysis.md"
with open(report_path, 'w') as f:
    f.write('\n'.join(report))

print(f"Report written to: {report_path}")

# =====================================================================
# CONSOLE SUMMARY (for quick reading)
# =====================================================================
print(f"\n{'='*60}")
print(f"SUMMARY")
print(f"{'='*60}")
print(f"Real object count           : {N}")
print(f"Unique p shapes             : {len(shape_counter)}")
print(f"Unique segment strings      : {len(all_unique_segs)}")
print(f"Malformed segments          : {len(malformed_segs)}")
print(f"Digit range (b/t prefix)    : {min(digits)}–{max(digits)}")
print(f"Layer index range           : {min(layer_idxs)}–{max(layer_idxs)}")
print(f"X range                     : {min(xs)}–{max(xs)}")
print(f"Y range                     : {min(ys)}–{max(ys)}")
print(f"Link distribution:")
for lt, cnt in sorted(link_types.items(), key=lambda x: -x[1]):
    print(f"  {lt:<25}: {cnt}")
print(f"No-link objects             : {len(no_link_ids)}")
print(f"Top-3 most referenced layers:")
for key, cnt in layer_hits.most_common(3):
    print(f"  {key[0]}{key[1]}-{key[2]}={key[3]}: {cnt} coord hits")
print(f"Title-issue objects         : {len(special_chars)}")
print(f"Files written:")
print(f"  {report_path}")
print(f"  {Path(__file__)}")
print(f"{'='*60}")
