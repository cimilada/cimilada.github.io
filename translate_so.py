"""Regenerate the page's Somali text with Google Translate.

The page keeps English as the source and Somali alongside it in template_v2.html:
  * the SO dictionary of fixed labels         'English':'Somali'
  * say(english, somali) calls for sentences built from data
  * SO_RX pattern rules, the Somali banner, and the day and month names
This script translates every English source with Google Translate (the public
translate.googleapis.com endpoint, en -> so) and rewrites the Somali side in place.
Variables, HTML tags and proper names (Deyr, GloFAS, SEAS5, ...) are swapped for
[[n]] placeholders before translation and restored afterwards; if Google drops a
placeholder the existing Somali text is kept and the string is reported.

Translations are cached in i18n/so_cache.json, so re-running only asks Google for
new or changed strings. Run:  python3 translate_so.py
"""
import json
import os
import re
import time
import urllib.parse
import urllib.request

T = "template_v2.html"
CACHE = "i18n/so_cache.json"
# names and units that must come through unchanged (longest first)
PROTECT = ["CHIRPS3-GEFS", "CHIRPS v3", "Indian Ocean Dipole", "Open-Meteo", "Copernicus", "El Niño", "La Niña",
           "Niño3.4", "GloFAS", "CHIRPS", "SEAS5", "ECMWF", "SWALIM", "FRRIMS", "SoDMA", "GDACS", "NOAA", "GEFS",
           "AIFS", "CAMS", "IOD", "UTC", "CAP", "WMO", "FAO", "GFS", "µg/m³", "m³/s", "°C",
           "Jilaal", "Deyr", "Hagaa", "Gu"]

cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
stats = {"asked": 0, "cached": 0, "kept": 0}


def google(text):
    if text in cache:
        stats["cached"] += 1
        return cache[text]
    u = ("https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=so&dt=t&q="
         + urllib.parse.quote(text))
    for attempt in range(4):
        try:
            r = json.loads(urllib.request.urlopen(
                urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())
            out = "".join(seg[0] for seg in r[0] if seg[0])
            break
        except Exception:
            time.sleep(3 * (attempt + 1))
    else:
        raise RuntimeError("Google Translate unreachable")
    cache[text] = out
    stats["asked"] += 1
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    json.dump(cache, open(CACHE, "w"), ensure_ascii=False, indent=0, sort_keys=True)
    time.sleep(0.25)
    return out


def protect(text, slots):
    """Replace HTML tags and protected names with [[n]] placeholders."""
    def put(v):
        slots.append(v)
        return f"[[{len(slots) - 1}]]"
    text = re.sub(r"<[^>]+>", lambda m: put(m.group(0)), text)
    for word in PROTECT:
        text = re.sub(r"(?<![\w\[])" + re.escape(word) + r"(?![\w\]])", lambda m: put(m.group(0)), text)
    return text


def restore(text, slots, esc=None):
    """Put placeholders back. Cleanup and escaping touch only Google's text, never restored code."""
    text = re.sub(r"\[{1,2}\s*(\d+)\s*\]{1,2}", r"[[\1]]", text)   # Google sometimes drops a bracket
    text = re.sub(r"\s+at\s+(\[\[\d+\]\])", r", \1", text)   # Google leaves English "at" before a place name
    text = re.sub(r"\s+([,.;:)])", r"\1", text)
    if esc:
        text = esc(text)
    for i, v in enumerate(slots):
        if text.count(f"[[{i}]]") != 1:
            return None
        text = text.replace(f"[[{i}]]", v.replace("Hagaa", "Xagaa") if not v.startswith("${") else v)
    return text


def shape(src, out):
    """Give the Somali text the English source's outer whitespace and initial capital."""
    if out is None:
        return None
    lead = re.match(r"\s*", src).group(0)
    trail = re.search(r"\s*$", src).group(0)
    out = out.strip()
    s0, o0 = src.strip()[:1], out[:1]
    if s0.isalpha() and s0.isupper() and o0.isalpha() and o0.islower():
        out = o0.upper() + out[1:]
    return lead + out + trail


def translate_plain(text):
    slots = []
    q = protect(text, slots)
    if not re.search(r"[A-Za-z]{3,}", re.sub(r"\[\[\d+\]\]", "", q)):
        return text
    out = google(q)
    return shape(text, restore(out, slots))


# ------------------------------------------------------------ JS scanning
def scan_literal(s, i):
    """s[i] is a quote; return the index just after the closing quote."""
    q = s[i]
    j = i + 1
    while j < len(s):
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if q == "`" and s.startswith("${", j):
            j = scan_balanced(s, j + 2, "}")
            continue
        if c == q:
            return j + 1
        j += 1
    raise ValueError("unterminated literal at %d" % i)


def scan_balanced(s, j, close):
    """From just inside an opening bracket, return the index after its matching close."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    stack = [close]
    while j < len(s):
        c = s[j]
        if c in "'\"`":
            j = scan_literal(s, j)
            continue
        if c in pairs:
            stack.append(pairs[c])
        elif c == stack[-1]:
            stack.pop()
            if not stack:
                return j + 1
        j += 1
    raise ValueError("unbalanced")


def scan_arg(s, j):
    """Scan one call argument from j; return (end index, char that ended it: ',' or ')')."""
    pairs = {"(": ")", "[": "]", "{": "}"}
    while j < len(s):
        c = s[j]
        if c in "'\"`":
            j = scan_literal(s, j)
            continue
        if c in pairs:
            j = scan_balanced(s, j + 1, pairs[c])
            continue
        if c in ",)":
            return j, c
        j += 1
    raise ValueError("unterminated argument")


def template_parts(lit):
    """Split a template literal body into ('text', str) and ('expr', str) parts."""
    body, parts, j, buf = lit[1:-1], [], 0, ""
    while j < len(body):
        if body[j] == "\\":
            buf += body[j:j + 2]
            j += 2
            continue
        if body.startswith("${", j):
            end = scan_balanced(body, j + 2, "}")
            parts.append(("text", buf))
            buf = ""
            parts.append(("expr", body[j + 2:end - 1]))
            j = end
            continue
        buf += body[j]
        j += 1
    parts.append(("text", buf))
    return parts


def keep_ws(body, out):
    """Template literal: restore the English body's outer whitespace and initial capital."""
    lead = re.match(r"\s*", body).group(0)
    trail = re.search(r"\s*$", body).group(0)
    out = out.strip()
    s0 = re.sub(r"^(\$\{[^}]*\}|<[^>]+>|\s)+", "", body)[:1]
    m = re.match(r"^((?:\$\{[^}]*\}|<[^>]+>|\s)*)(.)", out)
    if m and s0.isalpha() and s0.isupper() and m.group(2).isalpha() and m.group(2).islower():
        out = m.group(1) + m.group(2).upper() + out[m.end():]
    return lead + out + trail


PLURAL = re.compile(r"^\s*[\w.\[\]]+\s*(?:>\s*1\s*\?\s*'s'\s*:\s*''|===\s*1\s*\?\s*''\s*:\s*'s')\s*$")


def translate_literal(lit):
    """Translate one JS string literal; None if a placeholder was lost."""
    if lit[0] in "'\"":
        text = lit[1:-1].replace("\\'", "'").replace('\\"', '"')
        out = translate_plain(text)
        if out is None:
            return None
        q = lit[0]
        return q + out.replace("\\", "\\\\").replace(q, "\\" + q) + q
    parts = template_parts(lit)
    slots, q = [], ""
    for kind, v in parts:
        if kind == "expr":
            if PLURAL.match(v):          # English plural suffix: Somali does not take it
                continue
            slots.append("${" + v + "}")
            q += f"[[{len(slots) - 1}]]"
        else:
            q += v
    q = protect(q, slots)
    if not re.search(r"[A-Za-z]{3,}", re.sub(r"\[\[\d+\]\]", "", q)):
        return lit
    out = restore(google(q), slots, esc=lambda t: t.replace("\\", "\\\\").replace("`", "\\`").replace("${", "$\\{"))
    if out is None:
        return None
    return "`" + keep_ws(lit[1:-1], out) + "`"


def translate_expr(src):
    """Copy an expression, translating every prose literal at any depth outside nested say() calls."""
    out, j = "", 0
    while j < len(src):
        c = src[j]
        if src.startswith("say(", j) and (j == 0 or not re.match(r"[\w.$]", src[j - 1])):
            end = scan_balanced(src, j + 4, ")")
            out += src[j:end]
            j = end
            continue
        if c in "'\"`":
            end = scan_literal(src, j)
            lit = src[j:end]
            tr = translate_literal(lit)
            if tr is None:
                raise LookupError(lit[:60])
            out += tr
            j = end
            continue
        out += c
        j += 1
    return out


# ------------------------------------------------------------ rewrite the template
s = open(T).read()
script_start = s.rindex("<script>")

# 1. say(english, somali): rebuild the Somali argument from the English one (last call first)
calls = [m.start() for m in re.finditer(r"(?<![\w.$])say\(", s) if m.start() > script_start]
calls = [c for c in calls if not s.startswith("say = ", c) and not s[c - 6:c] == "const "]
for c in reversed(calls):
    a0 = c + 4
    a1, ch = scan_arg(s, a0)
    if ch != ",":
        continue                                  # the definition or a one-argument call
    b0 = a1 + 1
    b1, ch = scan_arg(s, b0)
    en_src, so_src = s[a0:a1], s[b0:b1]
    lead = re.match(r"\s*", so_src).group(0)
    try:
        new_so = translate_expr(en_src.strip())
    except LookupError as e:
        stats["kept"] += 1
        print("kept hand translation (placeholder lost):", str(e))
        continue
    s = s[:b0] + lead + new_so + s[b1:]

# 2. SO dictionary: retranslate every key
i = s.index("const SO = {")
j = scan_balanced(s, s.index("{", i) + 1, "}")
block = s[i:j]


def dict_entry(m):
    key_lit, val_lit = m.group(1), m.group(2)
    key = key_lit[1:-1].replace("\\'", "'")
    out = translate_plain(key)
    if out is None:
        stats["kept"] += 1
        return m.group(0)
    return f"{key_lit}:'" + out.replace("\\", "\\\\").replace("'", "\\'") + "'"


block = re.sub(r"(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')\s*:\s*('(?:[^'\\]|\\.)*')", dict_entry, block)
s = s[:i] + block + s[j:]

# 3. SO_RX: pattern rules, translated from English templates with [[n]] groups
RX = [
    (r"/^(Show|Hide) CAP 1\.2 alerts \((\d+)\)$/", None),
    (r"/^Delayed (\d+) d$/", "Delayed [[1]] days"),
    (r"/^Silent (\d+) d$/", "Silent for [[1]] days"),
    (r"/^max ([\d.,]+) m$/", "max [[1]] m"),
    (r"/^Point forecast, (.+)$/", "Point forecast, [[1]]"),
    (r"/^(Gu|Deyr|Jilaal|Hagaa) rainfall at this site, 1981–2026$/", "[[1]] rainfall at this site, 1981–2026"),
    (r"/^(Gu|Deyr|Jilaal|Hagaa) (\d{4}) accumulation against other years$/", "Total rain in [[1]] [[2]] compared with other years"),
    (r"/^Daily, (.+)$/", "Daily, [[1]]"),
    (r"/^m³\/s peak · (.+)$/", "peak m³/s · [[1]]"),
    (r"/^(\d+)% of the model's 2023 peak · now ([\d,]+) m³\/s$/", "[[1]]% of the model's 2023 flood peak · now [[2]] m³/s"),
    (r"/^([−\d.,-]+) m below moderate risk \(([\d.,]+) m\) · long-term mean ([\d.,]+) m$/", "[[1]] m below moderate risk ([[2]] m) · long-term average [[3]] m"),
    (r"/^([−\d.,-]+) m below moderate risk \(([\d.,]+) m\)$/", "[[1]] m below moderate risk ([[2]] m)"),
    (r"/^Rain (\d{4})$/", "Rain [[1]]"),
    (r"/^El Niño year \(Niño3\.4 ≥ \+0\.5 in Sep–Nov\)$/", "El Niño year (Niño3.4 ≥ +0.5 in Sep–Nov)"),
    (r"/^La Niña year \(≤ −0\.5\)$/", "La Niña year (≤ −0.5)"),
]


def rx_template(en):
    slots = []
    q = re.sub(r"\[\[(\d+)\]\]", lambda m: (slots.append("$" + m.group(1)), f"[[{len(slots) - 1}]]")[1], en)
    q = protect(q, slots)
    out = restore(google(q), slots)
    return out


show = translate_plain("Show CAP 1.2 alerts")
hide = translate_plain("Hide CAP 1.2 alerts")
lines = ["  [/^(Green|Yellow|Orange|Red) · (No warning|Be aware|Be prepared|Take action)$/, (m,a,b)=>`${SO[a]} · ${SO[b]}`],",
         f"  [/^(Show|Hide) CAP 1\\.2 alerts \\((\\d+)\\)$/, (m,a,n)=>`${{a==='Show'?{json.dumps(show)}:{json.dumps(hide)}}} (${{n}})`],"]
for rx, en in RX[1:]:
    out = rx_template(en)
    if out is None:
        stats["kept"] += 1
        print("pattern kept in English:", en)
        out = en.replace("[[", "$").replace("]]", "")
    lines.append(f"  [{rx}, {json.dumps(out, ensure_ascii=False)}],")
i = s.index("const SO_RX = [")
j = s.index("\n];", i) + 2          # regex literals contain quotes, so find the closing line instead
s = s[:i] + "const SO_RX = [\n" + "\n".join(lines) + "\n]" + s[j:]

# 4. day and month names
days = [translate_plain(d) for d in ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]]
months = [translate_plain(m + " 2026").replace("2026", "").strip() for m in
          ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
           "November", "December"]]
months = ["Disembar" if m == "December" else m for m in months]   # Google leaves December in English
ab = lambda w: w.strip()[:3].capitalize()
s = re.sub(r"const MON_EN = \[[^\]]*\], MON_SO = \[[^\]]*\];",
           "const MON_EN = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'], MON_SO = ["
           + ",".join(f"'{ab(m)}'" for m in months) + "];", s)
s = re.sub(r"const DOW_EN = \[[^\]]*\], DOW_SO = \[[^\]]*\];",
           "const DOW_EN = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'], DOW_SO = ["
           + ",".join(f"'{ab(d)}'" for d in days) + "];", s)

# 5. the Somali banner
note_en = ("Somali (beta), translated with Google Translate. Detailed technical notes are still in English. "
           "If you see a mistake, please contact us.")
note = translate_plain(note_en)
s = re.sub(r'(<p class="so-note" id="so-note" hidden>)[^<]*(</p>)', lambda m: m.group(1) + note + m.group(2), s)

open(T, "w").write(s)
os.makedirs(os.path.dirname(CACHE), exist_ok=True)
json.dump(cache, open(CACHE, "w"), ensure_ascii=False, indent=0, sort_keys=True)
print(f"Google requests {stats['asked']}, from cache {stats['cached']}, kept hand translation {stats['kept']}")
print("days:", days)
print("months:", months)
