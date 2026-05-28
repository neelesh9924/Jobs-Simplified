"""
Render a structured resume dict into a LaTeX document matching the
single-page Overleaf template (article, geometry 0.5in, tabularx).

The .tex is built in Python rather than a Django template to avoid
brace/`{% %}` conflicts with LaTeX syntax and to control escaping precisely.
"""

import re

_ESCAPE_MAP = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
    "<": r"\textless{}",
    ">": r"\textgreater{}",
}
_ESCAPE_RE = re.compile("|".join(re.escape(k) for k in _ESCAPE_MAP))


def esc(text) -> str:
    """Escape LaTeX special chars. '--' stays '--' (renders as en-dash)."""
    if text is None:
        return ""
    return _ESCAPE_RE.sub(lambda m: _ESCAPE_MAP[m.group()], str(text))


def _url(href: str, label: str) -> str:
    # Inside \href the URL only needs # and % backslash-escaped.
    safe = str(href).replace("#", r"\#").replace("%", r"\%")
    return rf"\href{{{safe}}}{{{esc(label)}}}"


def _section(title: str) -> str:
    return (
        "\\vspace{3pt}\n\\hrule\n\\vspace{4pt}\n\n"
        f"\\textbf{{{esc(title)}}} \\\\\n"
    )


def _itemize(bullets) -> str:
    if not bullets:
        return ""
    lines = "\n".join(rf"  \item {esc(b)}" for b in bullets)
    return f"\\begin{{itemize}}\n{lines}\n\\end{{itemize}}\n"


PREAMBLE = r"""\documentclass[a4paper,10pt]{article}
\usepackage[margin=0.50in]{geometry}
\usepackage{enumitem}
\usepackage{hyperref}
\usepackage{tabularx}
\pagenumbering{gobble}
\setlength{\parindent}{0pt}
\setlength{\parskip}{2pt}
\hypersetup{hidelinks}
\sloppy
\hyphenpenalty=10000
\exhyphenpenalty=10000
\emergencystretch=1.5em
\setlist[itemize]{noitemsep, topsep=2pt, leftmargin=1.2em}
\begin{document}
"""


def render_latex(resume: dict) -> str:
    r = resume or {}
    parts = [PREAMBLE]

    # ---- Header ----
    contact = r.get("contact", {}) or {}
    bits = []
    if contact.get("email"):
        bits.append(_url(f"mailto:{contact['email']}", contact["email"]))
    if contact.get("phone"):
        bits.append(esc(contact["phone"]))
    if contact.get("github"):
        bits.append(_url(contact["github"], "GitHub"))
    if contact.get("linkedin"):
        bits.append(_url(contact["linkedin"], "LinkedIn"))
    contact_line = r" \;|\; ".join(bits)

    header = "\\begin{center}\n"
    header += f"{{\\Large \\textbf{{{esc(r.get('name', ''))}}}}} \\\\[2pt]\n"
    if r.get("title"):
        header += f"{esc(r['title'])} \\\\[2pt]\n"
    if contact_line:
        header += f"{contact_line}\n"
    header += "\\end{center}\n"
    parts.append(header)

    # ---- Summary ----
    if r.get("summary"):
        parts.append(_section("SUMMARY"))
        parts.append(esc(r["summary"]) + "\n")

    # ---- Skills ----
    groups = r.get("skill_groups") or []
    if groups:
        parts.append(_section("TECHNICAL SKILLS"))
        rows = "\n".join(
            rf"\textbf{{{esc(g.get('label',''))}}} & {esc(g.get('items',''))} \\"
            for g in groups
        )
        parts.append(
            "\\begin{tabularx}{\\textwidth}{@{}p{0.27\\textwidth} X@{}}\n"
            f"{rows}\n"
            "\\end{tabularx}\n"
        )

    # ---- Experience ----
    experience = r.get("experience") or []
    if experience:
        parts.append(_section("EXPERIENCE"))
        for comp in experience:
            line = rf"\textbf{{{esc(comp.get('company',''))}}}"
            if comp.get("location"):
                line += rf" \hfill {esc(comp['location'])}"
            line += " \\\\\n"
            parts.append(line)
            for role in comp.get("roles", []):
                title, dates = role.get("title"), role.get("dates")
                if title and dates:
                    parts.append(rf"\textit{{{esc(title)}}} \hfill {esc(dates)}" + "\n")
                elif title:
                    parts.append(rf"\textit{{{esc(title)}}}" + "\n")
                elif dates:
                    parts.append(rf"\textit{{{esc(dates)}}}" + "\n")
                parts.append(_itemize(role.get("bullets", [])))

    # ---- Products ----
    products = r.get("products") or {}
    if products.get("frontend_ownership") or products.get("complex_domains"):
        parts.append(_section("PRODUCTS"))
        if products.get("frontend_ownership"):
            parts.append(rf"\textbf{{Frontend Ownership:}} {esc(products['frontend_ownership'])} \\" + "\n")
        if products.get("complex_domains"):
            parts.append(rf"\textbf{{Complex Domains:}} {esc(products['complex_domains'])}" + "\n")

    # ---- Projects ----
    projects = r.get("projects") or []
    if projects:
        parts.append(_section("PROJECTS"))
        for p in projects:
            parts.append(rf"\textbf{{{esc(p.get('name',''))}}}" + "\n")
            parts.append(_itemize(p.get("bullets", [])))

    # ---- Education ----
    education = r.get("education") or []
    if education:
        parts.append(_section("EDUCATION"))
        rows = "\n".join(
            rf"\textbf{{{esc(e.get('degree',''))}}} & {esc(e.get('dates',''))} \\"
            + (f"\n{esc(e.get('institution',''))} & \\\\" if e.get("institution") else "")
            for e in education
        )
        parts.append(
            "\\begin{tabularx}{\\textwidth}{@{}X r@{}}\n"
            f"{rows}\n"
            "\\end{tabularx}\n"
        )

    parts.append("\\end{document}\n")
    # Join with "" — each part already ends in a newline. Joining with "\n"
    # would inject a blank line (paragraph break) between every part and
    # overflow the one-page layout.
    return "".join(parts)
