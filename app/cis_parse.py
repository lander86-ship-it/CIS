"""Parse cis-bench exports into the normalised :class:`policy.Benchmark` model.

Two input shapes are supported, most-reliable first:

* **XCCDF** (``cis-bench export <id> --format xccdf``): a NIST-standard XML with
  ``<Group>`` = section and ``<Rule>`` = control. Titles, rationale, remediation
  (``<fixtext>``) and check/audit text are read from well-defined elements.
* **JSON** (``cis-bench export <id> --format json``): schema-tolerant. We look
  for a list of rule/recommendation objects and map common field names.

Both parsers are defensive: unknown shapes degrade to as much as can be found
rather than raising, so the policy generator always has something to render.
"""

from __future__ import annotations

import html
import json
import re

from lxml import etree

from .policy import Benchmark, Control, Section

# XCCDF appears in several namespace versions; match by local-name instead.
_LEVEL_RE = re.compile(r"level\s*([12])|\bL([12])\b", re.I)

# Text sanitizers: some exports (e.g. STIG-styled XCCDF) embed XML fragments in
# titles, and CIS control text is authored in Markdown (code fences, backticks,
# bold). Strip all of that so the Word document reads cleanly.
_TAG_RE = re.compile(r"<[^>]+>")
_FENCE_RE = re.compile(r"```[^\n`]*")          # ``` and optional language tag
_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")       # **bold** -> bold
_EMPH_RE = re.compile(r"(?<![\w`])_([^_`\n]+)_(?![\w])")  # _italic_ -> italic
_VID_RE = re.compile(r"^[A-Za-z]{0,3}-?\d+$")   # V-12345 / 12345 style ids


def _lname(el) -> str:
    return etree.QName(el).localname


def _find_all(el, name):
    return [d for d in el.iter() if _lname(d) == name]


def _first_text(el, name) -> str:
    for d in el.iter():
        if _lname(d) == name:
            return _clean(_all_text(d))
    return ""


def _all_text(el) -> str:
    return " ".join(t.strip() for t in el.itertext() if t and t.strip())


def _clean(s: str) -> str:
    """Strip embedded XML tags and Markdown noise; collapse whitespace."""
    if not s:
        return ""
    s = html.unescape(s)
    s = _TAG_RE.sub(" ", s)        # drop <GroupDescription> etc.
    s = _FENCE_RE.sub(" ", s)      # drop ``` code-fence markers
    s = _BOLD_RE.sub(r"\1", s)     # **bold** -> bold
    s = _EMPH_RE.sub(r"\1", s)     # _italic_ -> italic
    s = s.replace("`", " ")        # drop inline backticks
    return re.sub(r"\s+", " ", s).strip()


def _meaningful(title: str) -> bool:
    """True if a section title is descriptive (not empty, a tag, or an id)."""
    t = _clean(title)
    if len(re.sub(r"[^A-Za-z]", "", t)) < 3:  # needs real words
        return False
    if _VID_RE.match(t.replace(" ", "")):
        return False
    return True


def _level_from(*texts) -> str:
    for t in texts:
        if not t:
            continue
        m = _LEVEL_RE.search(t)
        if m:
            return m.group(1) or m.group(2)
    return ""


# --- XCCDF -----------------------------------------------------------------


def parse_xccdf(data: bytes) -> Benchmark:
    root = etree.fromstring(data)
    bench_el = root if _lname(root) == "Benchmark" else None
    if bench_el is None:
        for d in root.iter():
            if _lname(d) == "Benchmark":
                bench_el = d
                break
    if bench_el is None:
        raise ValueError("No <Benchmark> element found in XCCDF.")

    title = _first_text(bench_el, "title") or "CIS Benchmark"
    version = _first_text(bench_el, "version")
    bench_id = bench_el.get("id", "") or ""

    sections: list[Section] = []

    def rule_to_control(rule) -> Control:
        num = _rule_number(rule)
        rtitle = _first_text(rule, "title")
        rationale = _first_text(rule, "rationale") or _first_text(rule, "description")
        remediation = _first_text(rule, "fixtext") or _first_text(rule, "fix")
        # audit/check text: XCCDF <check-content> or descriptive check text
        audit = _first_text(rule, "check-content") or ""
        impact = _first_text(rule, "warning")
        level = _level_from(rtitle, _rule_metadata(rule))
        return Control(number=num, title=rtitle or num or "Control",
                       level=level, rationale=rationale, audit=audit,
                       remediation=remediation, impact=impact)

    # Collect (section_title, control) in document order. Group titles that are
    # not descriptive (STIG junk like "<GroupDescription></GroupDescription>",
    # bare V-ids) are ignored — such rules inherit the nearest meaningful
    # ancestor title, or fall into an untitled section (rendered with no H2).
    ordered: list[tuple[str, Control]] = []

    def walk(group, inherited: str):
        gtitle = _first_text(group, "title")
        current = _clean(gtitle) if _meaningful(gtitle) else inherited
        for child in group:
            if _lname(child) == "Rule":
                ordered.append((current, rule_to_control(child)))
            elif _lname(child) == "Group":
                walk(child, current)

    top_groups = [c for c in bench_el if _lname(c) == "Group"]
    for g in top_groups:
        walk(g, "")
    for r in [c for c in bench_el if _lname(c) == "Rule"]:  # rules w/o a group
        ordered.append(("", rule_to_control(r)))

    # Merge consecutive controls that share a section title, preserving order.
    # Untitled sections (STIG junk stripped) render with no heading.
    for sec_title, ctrl in ordered:
        if not sections or sections[-1].title != sec_title:
            sections.append(Section(number="", title=sec_title))
        sections[-1].controls.append(ctrl)

    return Benchmark(id=_short_id(bench_id), title=title, version=version,
                     platform=_platform_from_title(title), sections=sections)


def _rule_number(rule) -> str:
    for attr in ("id",):
        rid = rule.get(attr, "")
        m = re.search(r"(\d+(?:\.\d+)+)", rid)
        if m:
            return m.group(1)
    # CIS often prefixes the number in the title: "1.1.1 Ensure ..."
    t = _first_text(rule, "title")
    m = re.match(r"\s*(\d+(?:\.\d+)*)", t)
    return m.group(1) if m else ""


def _group_number(group) -> str:
    gid = group.get("id", "")
    m = re.search(r"(\d+(?:\.\d+)*)", gid)
    if m:
        return m.group(1)
    t = _first_text(group, "title")
    m = re.match(r"\s*(\d+(?:\.\d+)*)", t)
    return m.group(1) if m else ""


def _rule_metadata(rule) -> str:
    bits = []
    for d in rule.iter():
        ln = _lname(d)
        if ln in ("metadata", "reference", "ident") and d.text:
            bits.append(d.text)
    return " ".join(bits)


# --- JSON (schema-tolerant) ------------------------------------------------

_TITLE_KEYS = ("title", "name", "recommendation", "rule_title")
_NUM_KEYS = ("number", "id", "rule_id", "recommendation_number", "index")
_RATIONALE_KEYS = ("rationale", "description", "rationale_statement")
_AUDIT_KEYS = ("audit", "audit_procedure", "check", "assessment")
_REMEDIATION_KEYS = ("remediation", "remediation_procedure", "fix", "fixtext")
_LEVEL_KEYS = ("level", "profile", "assessment_level")
_SECTION_KEYS = ("section", "group", "category", "chapter")


def _get(d: dict, keys, default=""):
    for k in keys:
        for actual in d:
            if actual.lower() == k:
                v = d[actual]
                if isinstance(v, (str, int, float)):
                    return str(v)
    return default


def _has_control_children(d: dict) -> bool:
    """True if this node holds a list of child control-like objects."""
    for v in d.values():
        if isinstance(v, list):
            for item in v:
                if isinstance(item, dict) and (
                        {k.lower() for k in item} & set(_TITLE_KEYS)):
                    return True
    return False


def _looks_like_control(d: dict) -> bool:
    lk = {k.lower() for k in d}
    if not (lk & set(_TITLE_KEYS)):
        return False
    # A benchmark/section that *contains* controls is a container, not a control.
    if _has_control_children(d):
        return False
    return bool(lk & (set(_NUM_KEYS) | set(_RATIONALE_KEYS)
                      | set(_REMEDIATION_KEYS) | set(_AUDIT_KEYS)
                      | set(_LEVEL_KEYS)))


def parse_json(data: bytes) -> Benchmark:
    obj = json.loads(data)
    title = ""
    version = ""
    bench_id = ""
    if isinstance(obj, dict):
        title = _get(obj, ("title", "name")) or ""
        version = _get(obj, ("version",))
        bench_id = _get(obj, ("id", "benchmark_id", "workbench_id"))

    controls_raw: list[dict] = []

    def collect(node):
        if isinstance(node, dict):
            if _looks_like_control(node):
                controls_raw.append(node)
            for v in node.values():
                collect(v)
        elif isinstance(node, list):
            for v in node:
                collect(v)

    collect(obj)

    # Group by section number prefix or explicit section field.
    sections: dict[str, Section] = {}
    order: list[str] = []
    for d in controls_raw:
        num = _clean(_get(d, _NUM_KEYS))
        ctitle = _clean(_get(d, _TITLE_KEYS)) or num or "Control"
        if not num:
            m = re.match(r"\s*(\d+(?:\.\d+)*)", ctitle)
            num = m.group(1) if m else ""
        sec_key = _clean(_get(d, _SECTION_KEYS)) or (num.split(".")[0] if num else "1")
        if sec_key not in sections:
            sections[sec_key] = Section(number=sec_key, title=_clean(_get(d, _SECTION_KEYS)) or f"Section {sec_key}")
            order.append(sec_key)
        sections[sec_key].controls.append(Control(
            number=num, title=ctitle,
            level=_clean(_get(d, _LEVEL_KEYS)),
            rationale=_clean(_get(d, _RATIONALE_KEYS)),
            audit=_clean(_get(d, _AUDIT_KEYS)),
            remediation=_clean(_get(d, _REMEDIATION_KEYS)),
        ))

    return Benchmark(id=_short_id(bench_id), title=title or "CIS Benchmark",
                     version=version, platform=_platform_from_title(title),
                     sections=[sections[k] for k in order])


# --- Helpers ---------------------------------------------------------------


def _short_id(raw: str) -> str:
    m = re.search(r"(\d{3,})", raw or "")
    return m.group(1) if m else ""


def _platform_from_title(title: str) -> str:
    # "CIS <Platform> Benchmark" -> "<Platform>"
    t = re.sub(r"^CIS\s+", "", title or "", flags=re.I)
    t = re.sub(r"\s+Benchmark.*$", "", t, flags=re.I)
    return _clean(t)


def parse_benchmark(data: bytes, fmt: str) -> Benchmark:
    fmt = (fmt or "").lower()
    if fmt in ("xccdf", "xml"):
        return parse_xccdf(data)
    if fmt == "json":
        return parse_json(data)
    # sniff
    head = data.lstrip()[:1]
    if head == b"<":
        return parse_xccdf(data)
    return parse_json(data)
