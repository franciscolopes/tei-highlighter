# app.py (static CSV, single column + refined line numbers)
import html
import re
from xml.etree import ElementTree as ET
from streamlit.components.v1 import html as st_html


import pandas as pd
import streamlit as st

st.set_page_config(page_title="TEI Highlighter", layout="wide")

# -------------------- Config --------------------
CSV_PATH = "textoanotado.csv"  # change if needed

# -------------------- Constants --------------------

TEI_NS_URI = "http://www.tei-c.org/ns/1.0"

HIGHLIGHTABLE_TAGS = {
    "persName": "Person",
    "placeName": "Place",
    "orgName": "Org",
    "rs": "Group/Species",
    "term": "Term",
    "seg": "Rhetoric",
    "q": "Quote",
    "foreign": "Foreign",
}

DEFAULT_COLORS = {
    "persName": "#2563eb",
    "placeName": "#059669",
    "orgName": "#7c3aed",
    "rs": "#ea580c",
    "term": "#b91c1c",
    "seg": "#0ea5e9",
    "q": "#be185d",
    "foreign": "#4b5563",
}

# Regex to split @ana values like "#anáfora #paralelismo"
ANA_TOKEN_RE = re.compile(r"#\S+")

# -------------------- Utilities --------------------

def strip_ns(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag

def get_attr(el, name, default=None):
    for k, v in el.attrib.items():
        if k.endswith(name):
            return v
    return default

def ensure_tei_body(xml_text: str) -> str:
    txt = (xml_text or "").strip()
    if not txt:
        return f'<text xmlns="{TEI_NS_URI}" xml:lang="und"><body/></text>'

    try:
        root = ET.fromstring(txt)
        if strip_ns(root.tag) == "body":
            return ET.tostring(root, encoding="unicode")
        for node in root.iter():
            if strip_ns(node.tag) == "body":
                return txt
        if strip_ns(root.tag) == "text":
            body = ET.Element(f"{{{TEI_NS_URI}}}body")
            for child in list(root):
                body.append(child)
            root.clear()
            root.tag = f"{{{TEI_NS_URI}}}text"
            root.append(body)
            return ET.tostring(root, encoding="unicode")
    except Exception:
        pass
    return f'<text xmlns="{TEI_NS_URI}" xml:lang="und"><body>{txt}</body></text>'

def parse_xml(xml_text: str):
    normalized = ensure_tei_body(xml_text)
    return ET.fromstring(normalized)

def find_body(root):
    def find_with_ns(el, local):
        for child in el.iter():
            if strip_ns(child.tag) == local:
                return child
        return None
    if strip_ns(root.tag) == "body":
        return root
    if strip_ns(root.tag) in ("TEI", "tei", "text"):
        b = find_with_ns(root, "body")
        if b is not None:
            return b
    return find_with_ns(root, "body")

def split_ana(val: str):
    if not val:
        return []
    return ANA_TOKEN_RE.findall(val)

def human_label(tag: str):
    return HIGHLIGHTABLE_TAGS.get(tag, tag)

INDENT_AS_CODE_RE = re.compile(r'(^|\n)[ \t]{4,}')  # 4+ leading spaces at a line start

def escape_text(s: str) -> str:
    s = s or ""
    # Remove indentation that would make Markdown start an indented code block
    s = INDENT_AS_CODE_RE.sub(r'\1', s)
    return html.escape(s)

def has_tag(body_el, local_name: str) -> bool:
    return any(strip_ns(e.tag) == local_name for e in body_el.iter())

# -------------------- Rendering --------------------

def render_html(el, enabled_tags, color_map, show_tooltips=True,
                line_numbers=False, ln_mode=None, _ln=None):
    """
    Recursively render TEI body into HTML, wrapping highlightable tags in <span>.
    - Disabled tags → only escaped text content (no raw XML).
    - Line numbers:
        * ln_mode == "l": number <l> lines with a grid layout.
        * ln_mode == "lb": number first line at <p> start, then each <lb/>.
    """
    if _ln is None:
        _ln = {"n": 0}

    tag = strip_ns(el.tag)

    # Build inner HTML from children (escaped)
    inner = escape_text(el.text or "")
    for child in list(el):
        inner += render_html(child, enabled_tags, color_map, show_tooltips,
                             line_numbers, ln_mode, _ln)
        inner += escape_text(child.tail or "")

    # Blocks
    if tag == "div":
        return f'<div class="tei-div">{inner}</div>'

    if tag == "p":
        if line_numbers and ln_mode == "lb":
            # If the paragraph begins with a <lb/>, don't print a number here.
            # Let the *first* <lb/> produce line number 1 (no <br/>).
            starts_with_lb = (not (el.text or "").strip()) and len(el) > 0 and strip_ns(el[0].tag) == "lb"
            if starts_with_lb:
                _ln["need_leading_number"] = True   # tell the next <lb/> to print the first number w/o <br/>
                return f'<p class="tei-p">{inner}</p>'
            else:
                _ln["n"] += 1
                _ln["need_leading_number"] = False
                return f'<p class="tei-p"><span class="tei-lineno">{_ln["n"]}</span>{inner}</p>'
        return f'<p class="tei-p">{inner}</p>'

    if tag == "head":
        return f'<h4 class="tei-head">{inner}</h4>'

    # Line elements
    if tag == "l":
        if line_numbers and ln_mode == "l":
            _ln["n"] += 1
            ln_html = f'<span class="tei-lineno">{_ln["n"]}</span>'
            return f'<div class="tei-line">{ln_html}<span class="tei-line-content">{inner}</span></div>'
        else:
            return f'<div class="tei-line"><span class="tei-line-content">{inner}</span></div>'

    if tag == "lb":
        if line_numbers and ln_mode == "lb":
            if _ln.get("need_leading_number", False):
                # First visible line in this paragraph: no <br/>, just the number.
                _ln["n"] += 1
                _ln["need_leading_number"] = False
                return f'<span class="tei-lineno">{_ln["n"]}</span>'
            else:
                _ln["n"] += 1
                return f'<br/><span class="tei-lineno">{_ln["n"]}</span>'
        return "<br/>"

    # Highlightable?
    if tag in enabled_tags:
        color = color_map.get(tag, "#111827")
        style = (
            f"background: {color}1A; border: 1px solid {color}; color: inherit; "
            f"border-radius: 0.4rem; padding: 0 0.25rem;"
        )
        title = ""

        if tag == "seg":
            ana = get_attr(el, "ana", "")
            cats = split_ana(ana)
            if cats:
                if show_tooltips:
                    title = f' title="Rhetoric: {", ".join(cats)}"'
                badge = " ".join(escape_text(c) for c in cats)
                return (
                    f'<span class="tei tei-seg" style="{style}"{title}>'
                    f'<span class="tei-badge">{badge}</span> {inner}</span>'
                )
        elif tag == "persName":
            title = ' title="Person"' if show_tooltips else ""
        elif tag == "placeName":
            title = ' title="Place"' if show_tooltips else ""
        elif tag == "orgName":
            title = ' title="Organization"' if show_tooltips else ""
        elif tag == "rs":
            rstype = escape_text(get_attr(el, "type", "") or "")
            tdesc = f'Group/Species{f" ({rstype})" if rstype else ""}'
            title = f' title="{tdesc}"' if show_tooltips else ""
        elif tag == "term":
            ttype = escape_text(get_attr(el, "type", "") or "")
            tdesc = f'Term{f" ({ttype})" if ttype else ""}'
            title = f' title="{tdesc}"' if show_tooltips else ""
        elif tag == "q":
            title = ' title="Quote"' if show_tooltips else ""
        elif tag == "foreign":
            lang = escape_text(get_attr(el, "lang", "") or get_attr(el, "xml:lang", "") or "")
            tdesc = f'Foreign{f" [{lang}]" if lang else ""}'
            title = f' title="{tdesc}"' if show_tooltips else ""

        return f'<span class="tei tei-{tag}" style="{style}"{title}>{inner}</span>'

    # Disabled tag: output **only** the escaped textual content; never raw markup
    return inner

# -------------------- Extraction --------------------

def extract_entities_and_rhetoric(body_el):
    entities, rhetoric = [], []
    for el in body_el.iter():
        tag = strip_ns(el.tag)
        if tag in ("persName", "placeName", "orgName", "rs", "term", "q", "foreign"):
            txt = "".join(el.itertext()).strip()
            if not txt:
                continue
            if tag == "rs":
                extra = f"type={get_attr(el, 'type', '')}"
            elif tag == "term":
                extra = f"type={get_attr(el, 'type', '')}"
            elif tag == "foreign":
                extra = f"lang={get_attr(el, 'lang', get_attr(el, 'xml:lang', ''))}"
            else:
                extra = ""
            entities.append({"element": tag, "label": human_label(tag), "text": txt, "extra": extra})
        if tag == "seg":
            ana = get_attr(el, "ana", "")
            cats = split_ana(ana)
            if cats:
                txt = "".join(el.itertext()).strip()
                for c in cats:
                    rhetoric.append({"category": c, "text": txt})

    entities_df = pd.DataFrame(entities) if entities else pd.DataFrame(columns=["element","label","text","extra"])
    rhet_df = pd.DataFrame(rhetoric) if rhetoric else pd.DataFrame(columns=["category","text"])
    return entities_df, rhet_df

# -------------------- Data --------------------

@st.cache_data(show_spinner=False)
def load_df(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str).fillna("")
    lower = [c.lower() for c in df.columns]
    if len(set(lower)) != len(lower):
        raise ValueError("CSV has duplicate column names after lowercasing.")
    df.columns = lower

    required = {"excerto", "capitulo", "id", "xml"}
    if not required.issubset(set(df.columns)):
        raise ValueError(f"CSV must contain columns: {sorted(required)}. Found: {sorted(df.columns.tolist())}")

    for c in ["capitulo", "id", "excerto", "xml"]:
        df[c] = df[c].astype(str).str.strip()

    df = df.drop_duplicates(subset=["capitulo", "id"], keep="first")
    return df

try:
    df = load_df(CSV_PATH)
except Exception as e:
    st.error(f"Error loading CSV '{CSV_PATH}': {e}")
    st.stop()

# -------------------- UI --------------------

st.title("TEI XML Highlighter")

st.sidebar.header("Filters")

cap_options = pd.unique(df["capitulo"]).tolist()
if not cap_options:
    st.error("No capítulos found in the CSV.")
    st.stop()

cap_sel = st.sidebar.selectbox("Chapter", cap_options)

df_filtered = df[df["capitulo"] == cap_sel]

id_options = pd.unique(df_filtered["id"]).tolist()
if not id_options:
    st.warning("No IDs for the selected capítulo.")
    st.stop()

id_sel = st.sidebar.selectbox("Unity", id_options)

row_df = df_filtered[df_filtered["id"] == id_sel]
row = None if row_df.empty else row_df.iloc[0]

st.sidebar.header("Highlight Options")
enabled = {t: st.sidebar.checkbox(f"{human_label(t)}  <{t}>", value=True) for t in HIGHLIGHTABLE_TAGS}

st.sidebar.header("Style")
show_tooltips = st.sidebar.checkbox("Show tooltips", value=True)
show_line_numbers = st.sidebar.checkbox("Show line numbers", value=True)
color_map = {t: st.sidebar.color_picker(f"Color for <{t}>", DEFAULT_COLORS[t]) for t in HIGHLIGHTABLE_TAGS}

# -------------------- Single-column layout --------------------


if row is None:
    st.info("Select a capítulo and id to view a record.")
else:
    
    tab_original, tab_xml, tab_highlight = st.tabs(["Original (excerto)", "XML (raw)", "Highlighted"])

    with tab_original:
        st.caption("Original text from the `excerto` column.")
        st.write(row["excerto"])

    with tab_xml:
        st.caption("Raw annotated XML from the `xml` column.")
        st.code(row["xml"], language="xml")

    with tab_highlight:
        st.caption("Rendered XML with tag-based highlighting.")
        try:
            root = parse_xml(row["xml"])
            body_el = find_body(root)
            if body_el is None:
                raise ValueError("Couldn't find <body> element in the XML.")

            # detect numbering mode
            has_l = has_tag(body_el, "l")
            has_lb = has_tag(body_el, "lb")
            ln_mode = "l" if has_l else ("lb" if has_lb else None)

            html_out = render_html(
                body_el,
                {t for t, v in enabled.items() if v},
                color_map,
                show_tooltips,
                line_numbers=show_line_numbers,
                ln_mode=ln_mode,
                _ln={"n": 0} if show_line_numbers else None,
            )

            # CSS
            st_html(f"""
            <!doctype html>
            <meta charset="utf-8" />
            <style>
            .tei {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji"; }}
            .tei-div {{ margin-bottom: 0.5rem; }}
            .tei-p {{ margin: 0.5rem 0; line-height: 1.7; }}
            .tei-p:first-child {{ margin-top: 0; }}
            .tei-badge {{
                font-size: 0.70rem;
                padding: 0 0.3rem;
                margin-right: 0.35rem;
                border-radius: 0.35rem;
                border: 1px dashed rgba(0,0,0,0.25);
                background: rgba(0,0,0,0.04);
                white-space: nowrap;
            }}
            .tei-head {{ margin: 0.5rem 0; font-weight: 600; }}

            /* Line numbering */
            .tei-lineno {{
                user-select: none;
                opacity: 0.6;
                font-variant-numeric: tabular-nums;
                display: inline-block;
                margin-right: 0.5rem;
            }}
            .tei-line {{
                display: grid;
                grid-template-columns: 3rem 1fr;
                gap: 0.5rem;
                align-items: start;
            }}
            .tei-line .tei-lineno {{
                width: 2.5rem;
                text-align: right;
                margin-right: 0;
            }}
            .tei-line-content {{ display: inline; }}
            </style>

            <div class="tei">{html_out}</div>
            """, height=400, scrolling=True)
        except Exception as e:
            st.error(f"XML parsing error: {e}")

# -------------------- Extracted data (tabs in same column) --------------------

st.subheader("Extracted Categories")
if row is None:
    st.caption("Pick a record to see entities and rhetoric.")
else:
    try:
        root = parse_xml(row["xml"])
        body_el = find_body(root)
    except Exception:
        body_el = None

    if body_el is None:
        st.info("No parsable <body> found.")
    else:
        entities_df, rhet_df = extract_entities_and_rhetoric(body_el)

        tab1, tab2, tab3 = st.tabs(["Entities", "Rhetoric (by segment)", "Counts"])

        with tab1:
            st.caption("Pessoas, lugares, grupos, termos, citações e trechos estrangeiros")
            st.dataframe(entities_df, use_container_width=True)
            if not entities_df.empty:
                st.download_button(
                    "Download Entities (CSV)",
                    data=entities_df.to_csv(index=False),
                    file_name=f"entities_{row['capitulo']}_{row['id']}.csv",
                    mime="text/csv",
                )

        with tab2:
            st.caption("Categorias do @ana com o texto correspondente")
            st.dataframe(rhet_df, use_container_width=True)
            if not rhet_df.empty:
                st.download_button(
                    "Download Rhetoric (CSV)",
                    data=rhet_df.to_csv(index=False),
                    file_name=f"rhetoric_{row['capitulo']}_{row['id']}.csv",
                    mime="text/csv",
                )

        with tab3:
            ent_counts = entities_df["element"].value_counts() if not entities_df.empty else pd.Series([], dtype=int)
            rh_counts = rhet_df["category"].value_counts() if not rhet_df.empty else pd.Series([], dtype=int)

            counts_df = pd.DataFrame({
                "EntityTag": ent_counts.index.tolist(),
                "EntityCount": ent_counts.values.tolist()
            })
            rcounts_df = pd.DataFrame({
                "RhetoricalCategory": rh_counts.index.tolist(),
                "Count": rh_counts.values.tolist()
            })

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Entity counts**")
                st.dataframe(counts_df, use_container_width=True)
            with c2:
                st.markdown("**Rhetorical category counts**")
                st.dataframe(rcounts_df, use_container_width=True)

st.markdown("---")
#st.caption("Tip: `@ana` can contain multiple categories like `#anáfora #paralelismo`. This app splits and indexes each.")
