"""Custom CSS styles for the Risk Governance Agent UI."""

CUSTOM_CSS = """
<style>
/* ---- Global sidebar ---- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
}
section[data-testid="stSidebar"] * {
    color: #e0e0e0 !important;
}
/* Selectbox: white text, visible dropdown */
section[data-testid="stSidebar"] [data-testid="stSelectbox"] *,
section[data-testid="stSidebar"] [data-baseweb="select"] * {
    color: #ffffff !important;
    font-weight: 600 !important;
}
section[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: rgba(255,255,255,0.12) !important;
    border-color: rgba(255,255,255,0.3) !important;
}
/* Text inputs: dark text on white bg so values are always readable */
section[data-testid="stSidebar"] input[type="text"],
section[data-testid="stSidebar"] [data-testid="stTextInput"] input {
    color: #1a1a2e !important;
    background: #ffffff !important;
    border-color: rgba(255,255,255,0.4) !important;
    font-weight: 500 !important;
}
section[data-testid="stSidebar"] [data-testid="stTextInput"] input::placeholder {
    color: rgba(0,0,0,0.4) !important;
}
/* Labels in sidebar */
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] .stTextInput label {
    color: #ffffff !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
}
/* All buttons: visible */
section[data-testid="stSidebar"] button {
    color: #ffffff !important;
    border-color: rgba(255,255,255,0.25) !important;
}
section[data-testid="stSidebar"] button[kind="secondary"],
section[data-testid="stSidebar"] button[data-testid="stBaseButton-secondary"] {
    background: rgba(255,255,255,0.1) !important;
    color: #ffffff !important;
    border-color: rgba(255,255,255,0.3) !important;
    font-weight: 600 !important;
}
/* Shutdown button: red tint so it stands out */
section[data-testid="stSidebar"] button:last-of-type {
    background: rgba(255,75,75,0.15) !important;
    border-color: rgba(255,75,75,0.4) !important;
    color: #ff9999 !important;
}
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.1) !important;
}

/* ---- Stepper ---- */
.stepper {
    padding: 0.25rem 0;
}
.step {
    display: flex;
    align-items: flex-start;
    gap: 0.6rem;
    padding: 0.4rem 0.6rem;
    margin: 0.15rem 0;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.15s;
}
.step:hover {
    background: rgba(255,255,255,0.08);
}
.step.active {
    background: rgba(99,152,255,0.18);
    border-left: 3px solid #6398ff;
}
.step.locked {
    opacity: 0.45;
    cursor: not-allowed;
}
.step-icon {
    font-size: 1.1rem;
    min-width: 1.6rem;
    text-align: center;
    line-height: 1.5;
}
.step-text {
    flex: 1;
}
.step-title {
    font-size: 0.85rem;
    font-weight: 600;
}
.step-sub {
    font-size: 0.7rem;
    opacity: 0.65;
    margin-top: 1px;
}

/* ---- Progress bar ---- */
.progress-track {
    background: rgba(255,255,255,0.1);
    border-radius: 10px;
    height: 8px;
    margin: 0.5rem 0 1rem 0;
    overflow: hidden;
}
.progress-fill {
    height: 100%;
    border-radius: 10px;
    background: linear-gradient(90deg, #6398ff 0%, #50d890 100%);
    transition: width 0.4s ease;
}

/* ---- Severity badges ---- */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 12px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.03em;
}
.badge-high { background: #ff4b4b22; color: #ff4b4b; border: 1px solid #ff4b4b44; }
.badge-medium { background: #ffa72622; color: #ffa726; border: 1px solid #ffa72644; }
.badge-low { background: #66bb6a22; color: #66bb6a; border: 1px solid #66bb6a44; }

/* ---- Cards ---- */
.card {
    background: var(--background-color, #ffffff08);
    border: 1px solid rgba(128,128,128,0.2);
    border-radius: 12px;
    padding: 1.2rem;
    margin-bottom: 0.8rem;
}
.card-header {
    font-size: 1rem;
    font-weight: 600;
    margin-bottom: 0.5rem;
}

/* ---- Upload file cards ---- */
.file-chip {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: rgba(99,152,255,0.12);
    border: 1px solid rgba(99,152,255,0.25);
    border-radius: 20px;
    padding: 0.3rem 0.8rem;
    margin: 0.2rem;
    font-size: 0.8rem;
}

/* ---- Feedback section ---- */
.feedback-box {
    background: rgba(99,152,255,0.06);
    border: 1px solid rgba(99,152,255,0.15);
    border-radius: 12px;
    padding: 1.2rem;
    margin: 1rem 0;
}

/* ---- Phase header banner ---- */
.phase-banner {
    background: linear-gradient(135deg, rgba(99,152,255,0.08) 0%, rgba(80,216,144,0.08) 100%);
    border: 1px solid rgba(99,152,255,0.15);
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    margin-bottom: 1.5rem;
}
.phase-banner h2 {
    margin: 0 0 0.3rem 0;
    font-size: 1.4rem;
}
.phase-banner p {
    margin: 0;
    opacity: 0.7;
    font-size: 0.9rem;
}

/* ---- Governance tables: auto-growing row height ---- */
.gov-table-wrap {
    width: 100%;
    overflow-x: auto;
    margin: 0.5rem 0 1rem 0;
}
.gov-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
    line-height: 1.45;
}
.gov-table th {
    background: rgba(99,152,255,0.10);
    font-weight: 600;
    font-size: 0.78rem;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 0.55rem 0.7rem;
    border-bottom: 2px solid rgba(128,128,128,0.2);
    text-align: left;
    white-space: nowrap;
}
.gov-table td {
    padding: 0.5rem 0.7rem;
    border-bottom: 1px solid rgba(128,128,128,0.12);
    white-space: normal;
    word-wrap: break-word;
    overflow-wrap: break-word;
    vertical-align: top;
}
.gov-table tr:hover td {
    background: rgba(99,152,255,0.04);
}
.gov-table .col-id   { min-width: 60px; max-width: 100px; }
.gov-table .col-sm   { min-width: 80px; max-width: 140px; }
.gov-table .col-md   { min-width: 140px; max-width: 280px; }
.gov-table .col-lg   { min-width: 220px; }
.gov-table .col-xl   { min-width: 300px; }

/* ---- Verdict status cards ---- */
.verdict-ready { border-left: 4px solid #66bb6a; }
.verdict-partial { border-left: 4px solid #ffa726; }
.verdict-not-ready { border-left: 4px solid #ff4b4b; }

/* ---- Metric cards row ---- */
.metric-row {
    display: flex;
    gap: 0.8rem;
    margin: 0.8rem 0;
}
.metric-card {
    flex: 1;
    background: rgba(128,128,128,0.06);
    border: 1px solid rgba(128,128,128,0.15);
    border-radius: 10px;
    padding: 0.8rem 1rem;
    text-align: center;
}
.metric-value {
    font-size: 1.8rem;
    font-weight: 700;
    line-height: 1.2;
}
.metric-label {
    font-size: 0.75rem;
    opacity: 0.6;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* ---- History timeline ---- */
.timeline-entry {
    border-left: 2px solid rgba(99,152,255,0.3);
    padding-left: 1rem;
    margin-left: 0.5rem;
    margin-bottom: 0.6rem;
}
.timeline-dot {
    width: 8px;
    height: 8px;
    background: #6398ff;
    border-radius: 50%;
    display: inline-block;
    margin-left: -1.35rem;
    margin-right: 0.6rem;
}
</style>
"""


def inject_css():
    """Inject custom CSS into the Streamlit page."""
    import streamlit as st
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def severity_badge(severity: str) -> str:
    """Return HTML for a colored severity badge."""
    level = severity.lower() if severity else "low"
    css_class = f"badge-{level}" if level in ("high", "medium", "low") else "badge-low"
    return f'<span class="badge {css_class}">{severity}</span>'


def metric_card(value, label: str) -> str:
    """Return HTML for a styled metric card."""
    return f"""<div class="metric-card">
        <div class="metric-value">{value}</div>
        <div class="metric-label">{label}</div>
    </div>"""


def metric_row(metrics: list[tuple]) -> str:
    """Return HTML for a row of metric cards. metrics = [(value, label), ...]"""
    cards = "".join(metric_card(v, l) for v, l in metrics)
    return f'<div class="metric-row">{cards}</div>'


def phase_banner(title: str, description: str, icon: str = "") -> str:
    """Return HTML for a phase header banner."""
    return f"""<div class="phase-banner">
        <h2>{icon} {title}</h2>
        <p>{description}</p>
    </div>"""


def html_table(
    rows: list[dict],
    columns: list[tuple[str, str, str]],
) -> str:
    """Render rows as an HTML table with auto-growing row height.

    columns: list of (field_key, display_label, size_class).
        size_class is one of: 'col-id', 'col-sm', 'col-md', 'col-lg', 'col-xl'.
    """
    import html as html_mod

    if not rows:
        return '<p style="opacity:0.5;">No data.</p>'

    header = "".join(
        f'<th class="{sz}">{html_mod.escape(label)}</th>'
        for _, label, sz in columns
    )

    body_rows = []
    for row in rows:
        cells = []
        for key, _, sz in columns:
            val = row.get(key, "")
            if val is None:
                val = ""
            cells.append(f'<td class="{sz}">{html_mod.escape(str(val))}</td>')
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    return (
        '<div class="gov-table-wrap">'
        '<table class="gov-table">'
        f"<thead><tr>{header}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )
