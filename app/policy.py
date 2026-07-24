"""Generate a SABIC-styled cybersecurity policy (.docx) from a CIS benchmark.

The SABIC template (``app/templates/sabic_template.docx``) provides the house
style: cover page, logo header/footer, disclaimer, table of contents, version
history and review/approval scaffolding, and the named paragraph/table styles.

This module keeps 100% of that scaffolding and only:
  * rewrites the cover title + version,
  * refreshes the first Version History row,
  * replaces the body content region (Purpose … end) with a classic security
    standard: Purpose, Scope, Roles & Responsibilities, Security Requirements
    (the CIS controls, in full detail), Compliance & Exceptions, References,
  * flags the TOC field so Word rebuilds it on open.

lxml is used (not stdlib ElementTree) so the root namespace declarations
(w14/w15/mc/…) and prefixes are preserved — the output is the same package
with different body content: identical fonts, colours and branding.
"""

from __future__ import annotations

import copy
import io
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

TEMPLATE = Path(__file__).parent / "templates" / "sabic_template.docx"

# Bullet list instance already defined in the template's numbering.xml.
BULLET_NUM = 11
# Named styles from the template.
H1, H2, H3 = "Ttulo1", "Ttulo2", "Ttulo3"

# CT_Settings children that must appear AFTER <w:updateFields> in the schema.
_SETTINGS_AFTER = {
    "hdrShapeDefaults", "footnotePr", "endnotePr",
    "compat", "rsids", "mathPr", "attachedSchema", "themeFontLang",
    "clrSchemeMapping", "doNotIncludeSubdocsInStats",
    "doNotAutoCompressPictures", "forceUpgrade", "captions",
    "readModeInkLockDown", "smartTagType", "schemaLibrary", "shapeDefaults",
    "decimalSymbol", "listSeparator", "docId", "discardImageEditingData",
    "defaultImageDpi", "conflictMode", "chartTrackingRefBased",
    "persistentDocumentId",
}


def qn(tag: str) -> str:
    return f"{{{W}}}{tag}"


def _local(el) -> str:
    return etree.QName(el).localname


# --- Normalised data model -------------------------------------------------


@dataclass
class Control:
    number: str
    title: str
    level: str = ""
    rationale: str = ""
    audit: str = ""
    remediation: str = ""
    impact: str = ""


@dataclass
class Section:
    number: str
    title: str
    controls: list[Control] = field(default_factory=list)


@dataclass
class Benchmark:
    id: str
    title: str
    version: str = ""
    platform: str = ""
    sections: list[Section] = field(default_factory=list)

    @property
    def control_count(self) -> int:
        return sum(len(s.controls) for s in self.sections)


@dataclass
class PolicyMeta:
    title: str = ""
    version: str = "1.0"
    author: str = "Corporate Cybersecurity"
    date: str = ""  # dd/mm/yyyy — caller supplies it
    classification: str = "Internal"


# --- OOXML builders --------------------------------------------------------


def _run(text: str, bold: bool = False, italic: bool = False):
    r = etree.Element(qn("r"))
    rpr = etree.SubElement(r, qn("rPr"))
    if bold:
        etree.SubElement(rpr, qn("b"))
    if italic:
        etree.SubElement(rpr, qn("i"))
    etree.SubElement(rpr, qn("lang")).set(qn("val"), "en-US")
    t = etree.SubElement(r, qn("t"))
    t.set(XML_SPACE, "preserve")
    t.text = text
    return r


def _p(text=None, style=None, runs=None, num=None):
    p = etree.Element(qn("p"))
    ppr = etree.SubElement(p, qn("pPr"))
    if style:
        etree.SubElement(ppr, qn("pStyle")).set(qn("val"), style)
    if num is not None:
        npr = etree.SubElement(ppr, qn("numPr"))
        etree.SubElement(npr, qn("ilvl")).set(qn("val"), "0")
        etree.SubElement(npr, qn("numId")).set(qn("val"), str(num))
    if runs:
        for r in runs:
            p.append(r)
    elif text is not None:
        p.append(_run(text))
    return p


def _label_p(label: str, value: str):
    return _p(runs=[_run(f"{label}: ", bold=True), _run(value or "—")])


# --- Content generation ----------------------------------------------------


def _nlist(nar, key, default):
    if nar and isinstance(nar.get(key), list) and nar[key]:
        return [str(x) for x in nar[key]]
    return default


def _ntext(nar, key, default):
    if nar and isinstance(nar.get(key), str) and nar[key].strip():
        return nar[key].strip()
    return default


def _purpose(bench: Benchmark, meta: PolicyMeta, nar=None):
    plat = bench.platform or "the in-scope technology"
    out = [_p("Purpose", style=H1)]
    out.append(_p(_ntext(nar, "purpose_intro",
        f"The purpose of this standard is to establish the mandatory security "
        f"configuration and hardening requirements for {plat}, based on the "
        f"{bench.title}" + (f" (version {bench.version})" if bench.version else "")
        + ". It translates the referenced CIS Benchmark into enforceable "
        "internal requirements so that systems are configured, operated and "
        "maintained to a consistent, defensible security baseline.")))
    out.append(_p("This standard ensures that in-scope systems are:"))
    for line in _nlist(nar, "purpose_points", [
        "Configured in line with recognised industry hardening guidance (CIS Benchmarks)",
        "Protected against common misconfigurations and known attack vectors",
        "Consistently secured across regions, functions and business units",
        "Auditable against a defined and measurable set of controls",
    ]):
        out.append(_p(line, num=BULLET_NUM))
    out.append(_p("Additionally, this standard aims to:"))
    for line in _nlist(nar, "purpose_aims", [
        "Reduce the attack surface of information systems and digital assets",
        "Support regulatory, contractual and internal compliance obligations",
        "Provide a clear basis for configuration reviews and technical audits",
        "Enable risk-based exceptions where a control cannot be fully applied",
    ]):
        out.append(_p(line, num=BULLET_NUM))
    return out


def _scope(bench: Benchmark, nar=None):
    plat = bench.platform or "the relevant platform"
    out = [_p("Scope", style=H1)]
    out.append(_p(_ntext(nar, "scope_intro",
        f"This standard applies to all {plat} systems owned, operated or "
        "managed by SABIC, or by third parties on SABIC's behalf, that store, "
        "process or transmit SABIC information. It applies regardless of "
        "environment (production, non-production) or hosting model "
        "(on-premises, cloud or hybrid).")))
    out.append(_p("This standard applies to:"))
    for line in _nlist(nar, "scope_applies_to", [
        "All SABIC employees who administer or operate in-scope systems",
        "Contractors, third-party vendors and managed service providers",
        "Affiliates and subsidiaries operating in-scope systems",
        "Any party responsible for the configuration of SABIC IT/OT assets",
    ]):
        out.append(_p(line, num=BULLET_NUM))
    out.append(_p("This standard covers:"))
    for line in _nlist(nar, "scope_covers", [
        f"Secure configuration and hardening of {plat}",
        "The specific technical controls derived from the referenced CIS Benchmark",
        "Verification (audit) and remediation of each control",
        "The exception process where a control cannot be met",
    ]):
        out.append(_p(line, num=BULLET_NUM))
    out.append(_p(
        "The standard is applicable globally and must be followed in alignment "
        "with local regulatory requirements, where applicable."))
    return out


def _roles(roles_tbl_template, nar=None):
    out = [_p("Roles & Responsibilities", style=H1)]
    out.append(_p(
        "The following roles are responsible for the definition, "
        "implementation and assurance of this standard."))
    rows = [
        ("Corporate Cybersecurity – Governance",
         ["Define and maintain this security standard",
          "Approve exceptions and periodic reviews"]),
        ("System / Platform Owners",
         ["Ensure in-scope systems are configured to this standard",
          "Remediate gaps identified during audits"]),
        ("System Administrators / Engineers",
         ["Apply the technical controls during build and operation",
          "Maintain configuration over the system lifecycle"]),
        ("Identity & Access Management",
         ["Enforce access-related controls defined in this standard"]),
        ("Internal Audit / Assurance",
         ["Independently verify compliance with this standard"]),
        ("Third Parties / Vendors",
         ["Comply with this standard for any in-scope systems they manage"]),
    ]
    if nar and isinstance(nar.get("roles"), list) and nar["roles"]:
        parsed = []
        for r in nar["roles"]:
            if isinstance(r, dict) and r.get("role"):
                resp = r.get("responsibilities") or []
                resp = [str(x) for x in resp] if isinstance(resp, list) else [str(resp)]
                parsed.append((str(r["role"]), resp or ["Comply with this standard"]))
        if parsed:
            rows = parsed
    if roles_tbl_template is not None:
        out.append(_build_roles_table(roles_tbl_template, rows))
    else:
        for role, resp in rows:
            out.append(_p(runs=[_run(role, bold=True)]))
            for r in resp:
                out.append(_p(r, num=BULLET_NUM))
    return out


def _security_requirements(bench: Benchmark):
    titled = sum(1 for s in bench.sections if s.title.strip())
    out = [_p("Security Requirements", style=H1)]
    sec_phrase = (f" across {titled} section(s)" if titled else "")
    out.append(_p(
        f"This section defines the mandatory security controls for "
        f"{bench.platform or 'in-scope systems'}, derived from the {bench.title}"
        + (f" (version {bench.version})" if bench.version else "")
        + f". It contains {bench.control_count} control(s){sec_phrase}. Each "
        "control lists its assurance level, rationale, the audit procedure used "
        "to verify it, and the remediation required to meet it. All controls "
        "are mandatory unless a formal exception has been approved (see "
        "Compliance & Exceptions)."))
    for sec in bench.sections:
        heading = f"{sec.number} {sec.title}".strip()
        if heading:  # untitled sections (junk stripped) render with no heading
            out.append(_p(heading, style=H2))
        for c in sec.controls:
            lvl = f" (Level {c.level})" if c.level else ""
            out.append(_p(f"{c.number} {c.title}{lvl}".strip(), style=H3))
            if c.rationale:
                out.append(_label_p("Rationale", c.rationale))
            if c.impact:
                out.append(_label_p("Impact", c.impact))
            if c.audit:
                out.append(_label_p("Audit", c.audit))
            if c.remediation:
                out.append(_label_p("Remediation", c.remediation))
    return out


def _compliance(nar=None):
    out = [_p("Compliance & Exceptions", style=H1)]
    out.append(_p(_ntext(nar, "compliance_intro",
        "Compliance with this standard is mandatory for all in-scope systems. "
        "Compliance is verified through configuration reviews, automated "
        "scanning and periodic audits using the audit procedures defined for "
        "each control.")))
    out.append(_p(
        "Where a control cannot be technically or operationally met, a formal "
        "exception must be requested and risk-assessed before deployment. Each "
        "exception shall record:"))
    for line in _nlist(nar, "compliance_exception_fields", [
        "The specific control(s) that cannot be met",
        "The business or technical justification",
        "The compensating controls in place to mitigate the residual risk",
        "The approver and the review/expiry date of the exception",
    ]):
        out.append(_p(line, num=BULLET_NUM))
    out.append(_p(_ntext(nar, "compliance_enforcement",
        "Non-compliance without an approved exception may result in the system "
        "being remediated, isolated or removed from the environment, and may be "
        "subject to the organisation's disciplinary and contractual processes.")))
    return out


def _references(bench: Benchmark):
    out = [_p("References", style=H1)]
    for line in [
        f"{bench.title}" + (f", version {bench.version}" if bench.version else "")
        + (f" (CIS WorkBench ID {bench.id})" if bench.id else ""),
        "Center for Internet Security (CIS) Benchmarks — https://www.cisecurity.org/cis-benchmarks",
        "CIS WorkBench — https://workbench.cisecurity.org/",
        "SABIC Corporate Cybersecurity Standards",
    ]:
        out.append(_p(line, num=BULLET_NUM))
    return out


# --- Table cloning (Roles & Responsibilities) ------------------------------


def _set_cell(tc, lines: list[str], bullet: bool) -> None:
    """Replace a table cell's paragraphs, preserving its cell style."""
    paras = tc.findall(qn("p"))
    templ = copy.deepcopy(paras[0]) if paras else _p("")
    for r in templ.findall(qn("r")):
        templ.remove(r)
    for p in paras:
        tc.remove(p)
    for line in lines:
        np = copy.deepcopy(templ)
        np.append(_run(("• " + line) if bullet else line))
        tc.append(np)


def _build_roles_table(template_tbl, rows: list[tuple[str, list[str]]]):
    tbl = copy.deepcopy(template_tbl)
    trs = tbl.findall(qn("tr"))
    data_template = trs[1]
    for tr in trs[1:]:
        tbl.remove(tr)
    for role, resp in rows:
        tr = copy.deepcopy(data_template)
        cells = tr.findall(qn("tc"))
        _set_cell(cells[0], [role], bullet=False)
        _set_cell(cells[1], resp, bullet=len(resp) > 1)
        tbl.append(tr)
    return tbl


# --- Document assembly -----------------------------------------------------


def _text_of(p) -> str:
    return "".join(t.text or "" for t in p.iter(qn("t")))


def _pstyle(p):
    ppr = p.find(qn("pPr"))
    if ppr is None:
        return None
    ps = ppr.find(qn("pStyle"))
    return ps.get(qn("val")) if ps is not None else None


def _replace_run_text(p, new_text: str) -> None:
    runs = p.findall(qn("r"))
    if not runs:
        p.append(_run(new_text))
        return
    ts = runs[0].findall(qn("t"))
    if ts:
        ts[0].text = new_text
        for extra_t in ts[1:]:
            runs[0].remove(extra_t)
    else:
        runs[0].append(_run(new_text))
    for extra in runs[1:]:
        p.remove(extra)


def _find_roles_table(body):
    for el in body:
        if el.tag == qn("tbl"):
            head = _text_of(el).lower()
            if "role" in head[:40] and "responsib" in head[:80]:
                return el
    return None


def _fill_version_history(body, bench: Benchmark, meta: PolicyMeta) -> None:
    kids = list(body)
    for i, el in enumerate(kids):
        if el.tag == qn("p") and _text_of(el).strip().upper() == "VERSION HISTORY":
            for el2 in kids[i + 1:i + 3]:
                if el2.tag == qn("tbl"):
                    trs = el2.findall(qn("tr"))
                    if len(trs) >= 2:
                        cells = trs[1].findall(qn("tc"))
                        vals = [meta.version, meta.date or "", meta.author,
                                f"Initial version generated from {bench.title}"
                                + (f" v{bench.version}" if bench.version else "")]
                        for tc, v in zip(cells, vals):
                            _set_cell(tc, [v], bullet=False)
                        # Drop stale template rows so only this version shows.
                        for stale in trs[2:]:
                            el2.remove(stale)
                    return


def _enable_update_fields(settings_bytes: bytes) -> bytes:
    root = etree.fromstring(settings_bytes)
    if root.find(qn("updateFields")) is not None:
        return settings_bytes
    uf = etree.Element(qn("updateFields"))
    uf.set(qn("val"), "true")
    idx = len(root)
    for i, ch in enumerate(root):
        if _local(ch) in _SETTINGS_AFTER:
            idx = i
            break
    root.insert(idx, uf)
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                          standalone=True)


def build_policy(bench: Benchmark, meta: PolicyMeta,
                 narrative: dict | None = None,
                 template_path: Path | str = TEMPLATE) -> bytes:
    """Return the bytes of a SABIC-styled .docx for the given benchmark.

    ``narrative`` (optional) is an AI-drafted dict (see app/llm.py) used for the
    Purpose / Scope / Roles / Compliance prose; when None, static templates are
    used. The CIS controls are always rendered verbatim regardless.
    """
    template_path = Path(template_path)
    zin = zipfile.ZipFile(template_path, "r")
    root = etree.fromstring(zin.read("word/document.xml"))
    body = root.find(qn("body"))

    title = meta.title or f"{bench.title} — Security Hardening Standard"
    roles_tbl = _find_roles_table(body)

    # 1) Cover title + version.
    for el in body:
        if el.tag == qn("p"):
            txt = _text_of(el)
            if "Cybersecurity Standards Awareness" in txt:
                _replace_run_text(el, title)
            elif txt.strip().startswith("Version <"):
                _replace_run_text(el, f"Version {meta.version}")

    # 2) Version History first data row.
    _fill_version_history(body, bench, meta)

    # 3) Locate the body content region: H1 'Purpose' … final sectPr.
    kids = list(body)
    start = end = None
    for i, el in enumerate(kids):
        if start is None and el.tag == qn("p") and _pstyle(el) == H1 \
                and _text_of(el).strip().lower() == "purpose":
            start = i
        if el.tag == qn("sectPr"):
            end = i
    if start is None:
        raise RuntimeError("Could not locate 'Purpose' section in template.")
    if end is None or end <= start:
        end = len(kids)

    content = []
    content += _purpose(bench, meta, narrative)
    content += _scope(bench, narrative)
    content += _roles(roles_tbl, narrative)
    content += _security_requirements(bench)
    content += _compliance(narrative)
    content += _references(bench)

    # Anchor on the final sectPr (kept), insert content before it, then drop
    # the old region. Falls back to appending if no sectPr is present.
    anchor = kids[end] if end < len(kids) else None
    for node in kids[start:end]:
        body.remove(node)
    for node in content:
        if anchor is not None:
            anchor.addprevious(node)
        else:
            body.append(node)

    new_doc = etree.tostring(root, xml_declaration=True, encoding="UTF-8",
                             standalone=True)
    new_settings = _enable_update_fields(zin.read("word/settings.xml"))

    # Repackage: copy every member, swapping document.xml + settings.xml.
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "word/document.xml":
                zout.writestr(item, new_doc)
            elif item.filename == "word/settings.xml":
                zout.writestr(item, new_settings)
            else:
                zout.writestr(item, zin.read(item.filename))
    zin.close()
    return buf.getvalue()
