
import os
import base64
from io import BytesIO
import re
import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterator, List, Optional, Tuple

import requests
import streamlit as st
import textwrap

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


# ============================================================
# CONFIG
# ============================================================

APP_TITLE = "MediAgent AI"
APP_SUBTITLE = "Multi-Agent Healthcare Assistant"
DB_PATH = os.getenv("HEALTHCARE_DB_PATH", "healthcare.db")

# Cloud LLM (Groq) is the default because it is much faster for this demo.
# Ollama remains as an optional local fallback.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "45"))

PAGES = [
    "Top Docs Home",
    "Dashboard",
    "AI Assistant",
    "Find a Doctor",
    "Appointments",
    "Medical Reports",
    "Medication Info",
    "Symptom Triage",
    "Patient Education",
    "Support",
    "Follow-up",
]

PAGE_ICONS = {
    "Top Docs Home": "⌂",
    "Dashboard": "◈",
    "AI Assistant": "✦",
    "Find a Doctor": "⌕",
    "Appointments": "◷",
    "Medical Reports": "▤",
    "Medication Info": "Rx",
    "Symptom Triage": "♥",
    "Patient Education": "i",
    "Support": "◇",
    "Follow-up": "↻",
}



def _asset_data_uri(stem: str) -> str:
    """Load an image from assets/ (or beside this script), tolerating common extensions."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    for folder in (os.path.join(base_dir, "assets"), base_dir):
        for ext in (".webp", ".png", ".jpg", ".jpeg"):
            candidates.append(os.path.join(folder, stem + ext))
    for path in candidates:
        if os.path.isfile(path):
            try:
                ext = os.path.splitext(path)[1].lower()
                mime = {".webp": "image/webp", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}[ext]
                with open(path, "rb") as fh:
                    encoded = base64.b64encode(fh.read()).decode("ascii")
                return f"data:{mime};base64,{encoded}"
            except OSError:
                continue
    # A neutral inline SVG avoids broken-image icons if an optional asset is missing.
    placeholder = '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="420" viewBox="0 0 320 420"><rect width="320" height="420" rx="18" fill="#eef2ef"/><circle cx="160" cy="135" r="55" fill="#c8d5cf"/><path d="M55 390c8-100 55-150 105-150s97 50 105 150" fill="#c8d5cf"/><text x="160" y="405" text-anchor="middle" font-family="Arial,sans-serif" font-size="13" fill="#49655d">Image unavailable</text></svg>'
    return "data:image/svg+xml;base64," + base64.b64encode(placeholder.encode("utf-8")).decode("ascii")


__TOPDOCS_LOGO_SRC = _asset_data_uri("topdocs_logo")
__DOC1_SRC = _asset_data_uri("doctor_1")
__DOC2_SRC = _asset_data_uri("doctor_2")
__DOC3_SRC = _asset_data_uri("doctor_3")

DEMO_DISCLAIMER = (
    "Demo / academic system. Doctor data, availability, and responses are illustrative. "
    "This application does not diagnose conditions or prescribe treatment."
)


# ============================================================
# STREAMLIT CONFIG / STYLE
# ============================================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="✦",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
:root{--ink:#173b34;--muted:#64756f;--line:#dedbd1;--bg:#f8f6f0;--panel:rgba(255,255,255,.96);--accent:#1d594b;--accent-soft:#edf4f0;--success:#16865d;--success-soft:#eaf7f0;--warning:#a8782c;--warning-soft:#fff7e7;--shadow:0 12px 34px rgba(34,54,48,.07);--shadow-lg:0 18px 50px rgba(34,54,48,.11)}
html,body,[class*="css"]{font-family:"Inter",system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.stApp{background:radial-gradient(circle at 12% 0%,rgba(109,150,136,.10),transparent 28%),radial-gradient(circle at 90% 8%,rgba(190,149,80,.07),transparent 25%),var(--bg)}
.block-container{max-width:1500px;padding:1.4rem 2.1rem 3rem}
[data-testid="stSidebar"]{background:linear-gradient(180deg,#fff 0%,#f8fbff 100%);border-right:1px solid var(--line)}
[data-testid="stSidebar"] .block-container{padding:1.25rem .95rem 1.2rem}
.brand-wrap{display:flex;align-items:center;gap:11px;padding:5px 7px 18px}
.brand-mark{width:42px;height:42px;border-radius:14px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:21px;font-weight:800;background:linear-gradient(135deg,#173b34,#6d9688);box-shadow:0 8px 22px rgba(23,59,52,.20)}
.brand-name{font-size:20px;font-weight:800;color:var(--ink);letter-spacing:-.03em;line-height:1}
.brand-sub{font-size:10px;color:var(--muted);margin-top:4px}
.sidebar-section{margin:12px 7px 7px;font-size:10px;font-weight:800;letter-spacing:.12em;text-transform:uppercase;color:#90a0b7}
[data-testid="stSidebar"] [data-testid="stRadio"]>label{display:none}
[data-testid="stSidebar"] [data-testid="stRadio"]>div{gap:4px}
[data-testid="stSidebar"] [data-testid="stRadio"] label{padding:10px 12px!important;border-radius:12px!important;border:1px solid transparent!important;margin:0!important;transition:all .15s ease}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover{background:#f2f6ff!important;border-color:#e2ebff!important}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked){background:linear-gradient(90deg,#edf4f0,#f8faf8)!important;border-color:#d5e2da!important;box-shadow:inset 3px 0 0 var(--accent)}
.sidebar-status{margin-top:12px;padding:12px 13px;border:1px solid var(--line);background:#fff;border-radius:14px;box-shadow:0 5px 18px rgba(31,50,81,.04)}
.sidebar-status-row{display:flex;align-items:center;justify-content:space-between;gap:8px}
.status-dot{width:8px;height:8px;border-radius:50%;background:#17a66b;box-shadow:0 0 0 5px rgba(23,166,107,.11)}
.status-dot.off{background:#d88a13;box-shadow:0 0 0 5px rgba(216,138,19,.10)}
.status-title{font-size:12px;font-weight:700;color:var(--ink)}
.status-text{font-size:10px;color:var(--muted);margin-top:5px;line-height:1.45}
.page-topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}
.eyebrow{font-size:10px;font-weight:800;letter-spacing:.13em;text-transform:uppercase;color:#8193aa}
.top-status{display:inline-flex;align-items:center;gap:7px;padding:7px 10px;border:1px solid #dce7f5;border-radius:999px;background:rgba(255,255,255,.78);color:#52657e;font-size:11px;font-weight:700}
.hero{position:relative;overflow:hidden;background:radial-gradient(circle at 88% 20%,rgba(83,143,255,.18),transparent 26%),linear-gradient(135deg,rgba(255,255,255,.96),rgba(241,246,255,.93));border:1px solid #dde7f5;border-radius:24px;padding:27px 28px;margin-bottom:18px;box-shadow:var(--shadow)}
.hero:after{content:"";position:absolute;width:150px;height:150px;right:-48px;bottom:-65px;border-radius:50%;border:1px solid rgba(30,104,255,.10)}
.hero-title{font-size:31px;line-height:1.1;font-weight:800;color:var(--ink);letter-spacing:-.035em;margin:0}
.hero-subtitle{color:#6b7c91;font-size:13px;max-width:870px;margin-top:8px;line-height:1.55}
.card,.metric-card{background:var(--panel);border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow)}
.card{padding:19px;margin-bottom:14px}
.card:hover{box-shadow:var(--shadow-lg);transform:translateY(-1px);transition:all .18s ease}
.card h3{color:var(--ink);margin:0 0 6px;font-size:16px;letter-spacing:-.01em}
.card p{color:var(--muted);margin:0;line-height:1.55;font-size:12px}
.card-kicker{font-size:10px;color:#8193aa;font-weight:800;text-transform:uppercase;letter-spacing:.11em;margin-bottom:8px}
.card-icon{width:35px;height:35px;display:flex;align-items:center;justify-content:center;border-radius:11px;background:var(--accent-soft);color:#2362dc;font-weight:800;margin-bottom:11px}
.metric-card{padding:17px 18px;min-height:105px;position:relative;overflow:hidden}
.metric-card:after{content:"";position:absolute;width:70px;height:70px;right:-22px;top:-22px;border-radius:50%;background:#f4f8ff}
.metric-accent{width:26px;height:3px;border-radius:99px;background:linear-gradient(90deg,#1d594b,#be9550);margin-bottom:11px}
.metric-number{font-size:29px;line-height:1;font-weight:800;color:var(--ink);letter-spacing:-.04em}
.metric-label{margin-top:8px;font-size:11px;color:var(--muted);font-weight:600}
.agent-badge,.safety-pass,.safety-revise{display:inline-flex;align-items:center;gap:5px;padding:6px 10px;border-radius:999px;font-size:11px;font-weight:800;margin:0 6px 8px 0}
.agent-badge{background:var(--accent-soft);color:#2459c4;border:1px solid #dce8ff}.agent-badge:before{content:"✦"}
.safety-pass{background:var(--success-soft);color:#137b4e;border:1px solid #d5f0e3}.safety-pass:before{content:"✓"}
.safety-revise{background:var(--warning-soft);color:#8a6100;border:1px solid #f2e3b5}.safety-revise:before{content:"!"}
.route-card{background:linear-gradient(90deg,#f6faff,#fbfdff);border:1px solid #dbe8fb;border-radius:16px;padding:14px 16px;margin:6px 0 15px;color:#52657e;font-size:12px;line-height:1.5}
.route-title{color:var(--ink);font-weight:800;font-size:12px;margin-bottom:3px}
.section-title{color:var(--ink);font-size:18px;font-weight:800;margin:20px 0 10px;letter-spacing:-.02em}
.small,.muted{color:var(--muted);font-size:11px}
.stTextInput input,.stTextArea textarea,.stSelectbox [data-baseweb="select"],.stDateInput input{border-radius:12px!important;border-color:#dce5f0!important;background:#fff!important;box-shadow:0 1px 1px rgba(31,50,81,.02)!important}
.stTextInput input:focus,.stTextArea textarea:focus,.stDateInput input:focus{border-color:#729688!important;box-shadow:0 0 0 3px rgba(114,150,136,.18)!important}
button[kind="primary"],.stFormSubmitButton button{border-radius:12px!important;font-weight:800!important;min-height:42px!important;box-shadow:0 7px 17px rgba(23,59,52,.14)}
button[kind="secondary"],[data-testid="stBaseButton-secondary"]{border-radius:12px!important;font-weight:700!important;min-height:42px!important}
[data-testid="stSegmentedControl"]{background:#eef3f9;padding:4px;border-radius:13px}
[data-testid="stSegmentedControl"] button{border-radius:10px!important;font-weight:700!important}
[data-testid="stChatMessage"]{border:1px solid #e5ebf3;border-radius:18px;padding:2px 5px;box-shadow:0 5px 20px rgba(31,50,81,.04);background:rgba(255,255,255,.78)}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p{line-height:1.6}
[data-testid="stChatInput"] textarea{border-radius:15px!important;border-color:#d8e4f2!important}
[data-testid="stDataFrame"]{border:1px solid var(--line);border-radius:16px;overflow:hidden;box-shadow:var(--shadow)}
[data-testid="stAlert"]{border-radius:14px!important;border:1px solid #dfe8f5!important}
/* Workspace polish: stable spacing, legible controls, and consistent cards */
[data-testid="stMainBlockContainer"]{width:100%;}
[data-testid="stVerticalBlock"]{gap:1rem;}
[data-testid="stMetric"]{background:#fff;border:1px solid var(--line);padding:16px 18px;border-radius:16px;box-shadow:var(--shadow)}
[data-testid="stMetricLabel"]{color:var(--muted)!important;font-weight:600}
[data-testid="stMetricValue"]{color:var(--ink)!important;font-weight:800}
.stTextInput input,.stTextArea textarea,.stNumberInput input,.stDateInput input{color:var(--ink)!important;-webkit-text-fill-color:var(--ink)!important;caret-color:var(--accent)!important}
.stTextInput input::placeholder,.stTextArea textarea::placeholder{color:#81918a!important;-webkit-text-fill-color:#81918a!important;opacity:1!important}
[data-testid="stSelectbox"] [data-baseweb="select"] *{color:var(--ink)!important}
[data-testid="stRadio"] label,[data-testid="stCheckbox"] label{color:var(--ink)!important}
[data-testid="stDataFrame"]{max-width:100%}
[data-testid="stForm"]{background:rgba(255,255,255,.72);border:1px solid var(--line);border-radius:18px;padding:18px}
button[kind="primary"],[data-testid="stFormSubmitButton"] button{background:#173b34!important;color:#fff!important;border:1px solid #173b34!important}
button[kind="primary"]:hover,[data-testid="stFormSubmitButton"] button:hover{background:#24584b!important;border-color:#24584b!important}
button[kind="secondary"],[data-testid="stBaseButton-secondary"]{background:#fff!important;color:#173b34!important;border:1px solid #d8dfd8!important}
button:focus-visible{outline:3px solid rgba(190,149,80,.55)!important;outline-offset:2px!important}
[data-testid="stChatInput"] textarea{min-height:48px!important;font-size:15px!important;line-height:1.5!important;padding:12px 14px!important}
[data-testid="stChatInput"] button{background:#173b34!important;border-radius:11px!important;border:0!important}
[data-testid="stChatInput"] button svg{color:#fff!important;fill:#fff!important}
[data-testid="stChatMessage"]{padding:12px 14px!important}
[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p{overflow-wrap:anywhere}
[data-testid="stExpander"]{border:1px solid var(--line)!important;border-radius:14px!important;background:rgba(255,255,255,.65)}
hr{border:0;border-top:1px solid var(--line);margin:16px 0 18px}
footer{visibility:hidden}
@media (max-width:900px){.block-container{padding:1rem 1rem 2rem}.hero-title{font-size:25px}.page-topbar{gap:12px}.top-status{display:none}[data-testid="stForm"]{padding:12px}}
</style>
""",
    unsafe_allow_html=True,
)

# Ensure readable text on the light Top Docs theme across all pages.
st.markdown(
    """<style>

/* Readability fix: force dark text on the cream Top Docs canvas */
.stApp,
.stApp [data-testid="stAppViewContainer"],
.stApp [data-testid="stMain"],
.stApp [data-testid="stMainBlockContainer"] {
    color: #173b34 !important;
}
.stApp [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMarkdownContainer"] p,
.stApp [data-testid="stMarkdownContainer"] li,
.stApp [data-testid="stMarkdownContainer"] span,
.stApp [data-testid="stMarkdownContainer"] h1,
.stApp [data-testid="stMarkdownContainer"] h2,
.stApp [data-testid="stMarkdownContainer"] h3,
.stApp [data-testid="stMarkdownContainer"] h4,
.stApp [data-testid="stMarkdownContainer"] h5,
.stApp [data-testid="stMarkdownContainer"] h6,
.stApp [data-testid="stChatMessage"] p,
.stApp [data-testid="stChatMessage"] span,
.stApp label,
.stApp [data-testid="stCaptionContainer"] {
    color: #173b34 !important;
}
.stApp [data-testid="stChatInput"] textarea,
.stApp [data-testid="stChatInput"] textarea:focus {
    color: #173b34 !important;
    -webkit-text-fill-color: #173b34 !important;
    caret-color: #173b34 !important;
}
.stApp [data-testid="stChatInput"] textarea::placeholder {
    color: #64756f !important;
    -webkit-text-fill-color: #64756f !important;
    opacity: 1 !important;
}

</style>""",
    unsafe_allow_html=True,
)

# Chat composer contrast and focus-state fix.
st.markdown(
    """<style>

/* Chat composer: keep the bottom bar light and typed text readable */
[data-testid="stBottom"],
[data-testid="stBottom"] > div,
[data-testid="stChatInput"],
[data-testid="stChatInput"] > div {
    background: #f7f6ef !important;
    background-color: #f7f6ef !important;
}
[data-testid="stChatInput"] {
    border: 1px solid #d8dfd8 !important;
    border-radius: 14px !important;
    box-shadow: 0 2px 10px rgba(23, 59, 52, 0.06) !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: #729688 !important;
    outline: none !important;
    box-shadow: 0 0 0 3px rgba(114, 150, 136, 0.18) !important;
}
[data-testid="stChatInput"] textarea,
[data-testid="stChatInput"] textarea:focus {
    background: #ffffff !important;
    background-color: #ffffff !important;
    color: #173b34 !important;
    -webkit-text-fill-color: #173b34 !important;
    caret-color: #173b34 !important;
    border: 0 !important;
    outline: none !important;
    box-shadow: none !important;
}
[data-testid="stChatInput"] textarea::placeholder {
    color: #71817a !important;
    -webkit-text-fill-color: #71817a !important;
    opacity: 1 !important;
}
[data-testid="stChatInput"] button {
    color: #ffffff !important;
}

</style>""",
    unsafe_allow_html=True,
)

# ============================================================
# TOP DOCS EXPERIENCE OVERRIDES
# ============================================================

# When the user is on the landing experience, present MediAgent as a native Top Docs feature.
if st.session_state.get("nav", "Top Docs Home") == "Top Docs Home":
    st.markdown("""
    <style>
    :root{--td-ink:#173b34;--td-sage:#6d9688;--td-gold:#be9550;--td-paper:#f8f6f0;--td-line:#dedbd1} 
    .stApp{background:var(--td-paper)!important}
    .block-container{max-width:1450px!important;padding:0 0 4.5rem!important}
    [data-testid="stSidebar"]{display:none!important}
    header[data-testid="stHeader"]{background:transparent!important}
    .td-wrap{max-width:1180px;margin:0 auto;padding:0 24px}
    .td-nav{height:86px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--td-line)}
    .td-brand{display:flex;align-items:center;gap:12px;color:var(--td-ink);font-weight:800;font-size:22px;letter-spacing:-.04em}
    .td-logo{width:54px;height:54px;background:#fff;border-radius:8px;display:flex;align-items:center;justify-content:center;border:1px solid #ece8df;box-shadow:0 6px 20px rgba(40,50,45,.04);overflow:hidden}
    .td-logo img{width:100%;height:100%;object-fit:contain}
    .td-menu{display:flex;align-items:center;gap:38px;color:var(--td-ink);font-size:13px;font-weight:600}
    .td-menu a{color:inherit;text-decoration:none;white-space:nowrap}.td-menu a:hover{color:var(--td-gold)}
    .td-nav-cta{display:inline-flex;align-items:center;justify-content:center;padding:13px 24px;border-radius:28px;background:var(--td-gold);color:#17332c!important;text-decoration:none;font-weight:800;font-size:13px}
    .td-hero{display:grid;grid-template-columns:46% 54%;gap:54px;align-items:center;padding:76px 0 70px}
    .td-eyebrow{font-size:12px;letter-spacing:.13em;text-transform:uppercase;color:#568277;font-weight:800;margin-bottom:24px}
    .td-title{font-size:70px;line-height:1.02;letter-spacing:-.055em;font-weight:800;color:#173b34!important;margin:0}
    .td-title em{font-style:normal;color:#729688!important;font-weight:500}
    .td-main-cta,.td-nav-cta,.td-fab{text-decoration:none!important}
    .td-showcase{min-width:0;width:100%}
    .td-card{border-radius:18px;overflow:hidden}
    .td-doctor{border-radius:12px}
    .td-doctor img{display:block}
    .td-nav-cta{white-space:nowrap}
    @media(max-width:1200px){.td-hero{grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:34px}.td-title{font-size:clamp(44px,5vw,64px)}}

    .td-copy{font-size:16px;line-height:1.7;color:#49655d;max-width:500px;margin-top:26px}
    .td-main-cta{display:inline-flex;align-items:center;gap:28px;padding:17px 25px;border-radius:40px;background:var(--td-ink);color:white!important;text-decoration:none;font-size:14px;font-weight:800;margin-top:26px;box-shadow:0 14px 28px rgba(23,59,52,.13)}
    .td-main-cta .arrow{font-size:20px;line-height:1}
    .td-bullets{border-top:1px solid var(--td-line);margin-top:28px;padding-top:18px;display:flex;gap:24px;flex-wrap:wrap;color:#516c64;font-size:11px;line-height:1.45}
    .td-bullet{display:flex;gap:9px;align-items:flex-start;max-width:230px}
    .td-bullet i{width:6px;height:6px;border-radius:50%;background:var(--td-gold);display:inline-block;margin-top:5px;flex:0 0 auto}
    .td-showcase{position:relative;padding:14px 0 0 0}
    .td-ghost{position:absolute;inset:16px 16px -14px 0;border:1px solid #d5dfda;background:#eef4f1;transform:rotate(-2.1deg);z-index:0}
    .td-card{position:relative;z-index:2;background:#fff;border:1px solid #dbdbd4;padding:30px 25px 22px;box-shadow:0 24px 60px rgba(34,54,48,.08)}
    .td-card-top{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--td-line);padding-bottom:18px;margin-bottom:22px}
    .td-card-title{font-size:18px;font-weight:800;color:var(--td-ink)}
    .td-card-small{font-size:10px;color:#6b7f77;font-weight:800;letter-spacing:.04em}
    .td-doctors{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
    .td-doctor{height:248px;background:#eef0ef;overflow:hidden}
    .td-doctor img{width:100%;height:100%;object-fit:cover;object-position:center 22%}
    .td-row{display:flex;justify-content:space-between;gap:20px;padding:15px 0;border-bottom:1px solid var(--td-line);font-size:11px;color:#48605a}
    .td-row strong{color:#1d352f;text-align:right}
    .td-disclaimer{font-size:10px;line-height:1.5;color:#73827d;margin-top:14px}
    .td-tag{position:absolute;right:0;top:-4px;background:var(--td-gold);color:#1c312c;padding:10px 15px;font-size:10px;font-weight:900;letter-spacing:.04em}
    .td-institutes{background:#fff;border-top:1px solid #ece8df;border-bottom:1px solid #ece8df;padding:55px 0 42px}
    .td-institutes-title{text-align:center;font-size:12px;letter-spacing:.13em;text-transform:uppercase;color:#173b34;font-weight:900}
    .td-logos{display:flex;justify-content:space-between;align-items:flex-start;gap:28px;margin-top:32px}
    .td-inst{text-align:center;flex:1;color:#173b34;font-size:12px;font-weight:800}
    .td-inst-mark{height:70px;display:flex;align-items:center;justify-content:center;margin-bottom:12px;font-size:20px;color:#657c74}
    .td-footer-note{text-align:center;font-size:10px;color:#76847e;margin-top:22px}
    .td-fab{position:fixed;right:28px;bottom:28px;z-index:9999;display:flex;align-items:center;gap:10px;text-decoration:none}
    .td-fab-label{background:#173b34;color:white;padding:10px 14px;border-radius:22px;font-size:11px;font-weight:800;box-shadow:0 10px 30px rgba(23,59,52,.18);opacity:0;transform:translateX(8px);transition:.18s ease}
    .td-fab:hover .td-fab-label{opacity:1;transform:translateX(0)}
    .td-fab-btn{width:62px;height:62px;border-radius:50%;background:#173b34;color:#fff;display:flex;align-items:center;justify-content:center;box-shadow:0 16px 38px rgba(23,59,52,.23);border:4px solid #f8f6f0;font-size:25px}
    .td-fab-pulse{position:absolute;right:4px;top:2px;width:10px;height:10px;border-radius:50%;background:#62b78f;border:2px solid #f8f6f0}
    .td-assistant-note{position:fixed;right:28px;bottom:100px;z-index:9998;background:rgba(255,255,255,.96);border:1px solid #dedbd1;border-radius:14px;padding:10px 13px;font-size:11px;color:#35534a;box-shadow:0 12px 35px rgba(34,54,48,.10)}
    @media(max-width:1000px){.td-hero{grid-template-columns:1fr;gap:44px;padding-top:48px}.td-title{font-size:58px}.td-menu{gap:18px}.td-menu a:nth-child(-n+2){display:none}.td-showcase{max-width:760px}.td-logos{flex-wrap:wrap}.td-inst{min-width:25%}}
    /* Landing page layout corrections: prevent column overflow and photo distortion */
    .td-hero{grid-template-columns:minmax(0,.92fr) minmax(0,1.08fr);gap:clamp(24px,4vw,56px)}
    .td-showcase,.td-card,.td-doctors,.td-doctor{min-width:0;box-sizing:border-box}
    .td-card{position:relative;background:#fff;border:1px solid #dedbd1;padding:30px 32px;box-shadow:0 22px 55px rgba(31,55,47,.09)}
    .td-doctors{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;overflow:hidden}
    .td-doctor{height:220px;overflow:hidden;background:#edf1ee;border-radius:12px}
    .td-doctor img{width:100%;height:100%;object-fit:cover;object-position:center top}
    .td-nav{gap:18px}.td-menu{gap:clamp(14px,2.5vw,34px)}
    .td-nav-cta,.td-main-cta{transition:transform .18s ease,box-shadow .18s ease,background .18s ease}
    .td-nav-cta:hover,.td-main-cta:hover{transform:translateY(-2px);box-shadow:0 14px 30px rgba(23,59,52,.18)}
    .td-assistant-note{pointer-events:none}
    @media(max-width:1000px){.td-hero{grid-template-columns:minmax(0,1fr);gap:38px;padding:48px 0 50px}.td-title{font-size:clamp(46px,7vw,62px)}.td-showcase{max-width:760px;width:100%;margin:0 auto}.td-menu{gap:16px}.td-menu a:nth-child(-n+2){display:none}.td-logos{flex-wrap:wrap}.td-inst{min-width:25%}}
    @media(max-width:700px){.td-wrap{padding:0 16px}.td-nav{height:auto;min-height:72px;flex-wrap:wrap;padding:12px 0;gap:12px}.td-brand{font-size:18px}.td-logo{width:44px;height:44px}.td-menu{order:3;width:100%;justify-content:space-between;font-size:12px;gap:8px}.td-menu a:nth-child(n){display:inline}.td-nav-cta{padding:10px 14px;font-size:11px}.td-title{font-size:clamp(42px,12vw,54px)}.td-eyebrow{font-size:10px;line-height:1.6;margin-bottom:18px}.td-copy{font-size:14px;margin-top:20px}.td-main-cta{padding:15px 20px;gap:20px}.td-bullets{gap:12px}.td-card{padding:22px 16px}.td-card-top{gap:10px}.td-card-title{font-size:16px}.td-doctors{gap:8px}.td-doctor{height:150px;border-radius:9px}.td-row{gap:12px;font-size:11px}.td-disclaimer{font-size:10px;line-height:1.5}.td-fab{right:16px;bottom:18px}.td-fab-label,.td-assistant-note{display:none}.td-fab-btn{width:54px;height:54px}}
    @media(max-width:390px){.td-nav-cta{padding:9px 11px}.td-brand{gap:8px}.td-logo{width:38px;height:38px}.td-doctor{height:120px}.td-card{padding:18px 12px}.td-menu{font-size:11px}}
    </style>
    """, unsafe_allow_html=True)


# ============================================================
# DATABASE
# ============================================================

@contextmanager
def db_connect() -> Iterator[sqlite3.Connection]:
    """Open a short-lived SQLite connection and always close it."""
    conn = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with db_connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient TEXT NOT NULL,
                doctor TEXT NOT NULL,
                appointment_date TEXT NOT NULL,
                reason TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Booked',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient TEXT NOT NULL,
                issue TEXT NOT NULL,
                priority TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Open',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                report_text TEXT NOT NULL,
                summary TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS interactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task TEXT NOT NULL,
                agent TEXT NOT NULL,
                user_input TEXT NOT NULL,
                response TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


init_db()


def insert_interaction(task: str, agent: str, user_input: str, response: str) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO interactions(task, agent, user_input, response, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                task,
                agent,
                user_input[:5000],
                response[:10000],
                datetime.now().isoformat(timespec="seconds"),
            ),
        )
        conn.commit()


def get_scalar(query: str) -> int:
    with db_connect() as conn:
        row = conn.execute(query).fetchone()
        return int(row[0] or 0)


def fetch_rows(query: str, params: Tuple[Any, ...] = ()) -> List[sqlite3.Row]:
    with db_connect() as conn:
        return list(conn.execute(query, params).fetchall())


# ============================================================
# DEMO DIRECTORY
# ============================================================

DOCTORS = [
    {"name": "Dr. Ananya Sharma", "specialty": "Gynaecology", "mode": "In-person / Video", "city": "Nagpur"},
    {"name": "Dr. Rahul Mehta", "specialty": "Gastroenterology", "mode": "In-person / Video", "city": "Nagpur"},
    {"name": "Dr. Priya Verma", "specialty": "Cardiology", "mode": "In-person", "city": "Nagpur"},
    {"name": "Dr. Arjun Patel", "specialty": "Neurology", "mode": "Video", "city": "Nagpur"},
    {"name": "Dr. Neha Joshi", "specialty": "General Medicine", "mode": "In-person / Video", "city": "Nagpur"},
]


def specialties() -> List[str]:
    return sorted({d["specialty"] for d in DOCTORS})


# ============================================================
# LLM SERVICE
# ============================================================

@st.cache_data(ttl=30, show_spinner=False)
def llm_status() -> Tuple[bool, str]:
    if LLM_PROVIDER == "groq":
        if not GROQ_API_KEY:
            return False, "Groq selected · API key missing"
        try:
            r = requests.get(
                f"{GROQ_BASE_URL}/models",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                timeout=4,
            )
            r.raise_for_status()
            return True, f"Groq connected · {GROQ_MODEL}"
        except Exception:
            return False, "Groq unavailable / invalid API key"

    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=4)
        r.raise_for_status()
        data = r.json()
        models = [m.get("name", "") for m in data.get("models", [])]
        if any(
            OLLAMA_MODEL == m or OLLAMA_MODEL.split(":")[0] == m.split(":")[0]
            for m in models
        ):
            return True, f"Ollama connected · {OLLAMA_MODEL}"
        return True, f"Ollama connected · model not listed ({OLLAMA_MODEL})"
    except Exception:
        return False, "Ollama unavailable"


def llm_chat(
    system_prompt: str,
    user_prompt: str,
    fallback: str,
    temperature: float = 0.2,
    timeout: int = LLM_TIMEOUT,
) -> str:
    """
    Provider abstraction:
      - Groq by default (fast cloud inference)
      - Ollama when LLM_PROVIDER=ollama
    The rest of the multi-agent system stays unchanged.
    """

    try:
        if LLM_PROVIDER == "groq":
            if not GROQ_API_KEY:
                return (
                    fallback
                    + "\n\n_Groq is selected but GROQ_API_KEY is not configured. "
                      "Set the key and restart Streamlit._"
                )

            payload = {
                "model": GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt.strip()},
                    {"role": "user", "content": user_prompt.strip()},
                ],
                "temperature": temperature,
                "max_tokens": 700,
            }

            response = requests.post(
                f"{GROQ_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout,
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip() if content else fallback

        # Ollama local fallback / alternative
        payload = {
            "model": OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt.strip()},
                {"role": "user", "content": user_prompt.strip()},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }

        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
        data = response.json()
        content = data.get("message", {}).get("content", "")
        return content.strip() if content else fallback

    except requests.exceptions.ConnectionError:
        provider = "Groq" if LLM_PROVIDER == "groq" else "Ollama"
        return f"{fallback}\n\n_{provider} connection failed. The fallback response is shown._"
    except requests.exceptions.Timeout:
        return fallback + "\n\n_AI service timed out. The fallback response is shown._"
    except requests.exceptions.RequestException as exc:
        # Never expose API keys; only show a compact error class/message.
        return fallback + f"\n\n_AI service request failed: {type(exc).__name__}._"


# ============================================================
# AGENT RESULT
# ============================================================

@dataclass
class AgentResult:
    task: str
    agent: str
    response: str
    page: str
    data: Dict[str, Any] = field(default_factory=dict)
    safety_status: str = "PASS"
    safety_notes: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "agent": self.agent,
            "response": self.response,
            "page": self.page,
            "data": self.data,
            "safety_status": self.safety_status,
            "safety_notes": self.safety_notes,
        }


class BaseAgent:
    name = "Base Agent"

    def run(self, *args, **kwargs) -> AgentResult:
        raise NotImplementedError


# ============================================================
# SAFETY REVIEWER
# ============================================================

class ClinicalSafetyReviewerAgent(BaseAgent):
    name = "Clinical Safety Reviewer Agent"

    BAD_PATTERNS = [
        (re.compile(r"\bguarantee(?:d)?\b", re.I), "Guaranteed-outcome language"),
        (re.compile(r"\byou (definitely|certainly) have\b", re.I), "Definitive diagnosis language"),
        (re.compile(r"\bdiagnosis is\b", re.I), "Definitive diagnosis language"),
        (re.compile(r"\btake\s+\d+(?:\.\d+)?\s*(mg|ml|mcg|g)\b", re.I), "Specific dosing instruction"),
        (re.compile(r"\bstop taking\b", re.I), "Medication stop instruction"),
        (re.compile(r"\bdouble your dose\b", re.I), "Unsafe dosing instruction"),
    ]

    @classmethod
    def review(cls, text: str) -> Tuple[str, List[str]]:
        issues = []
        for pattern, label in cls.BAD_PATTERNS:
            if pattern.search(text or ""):
                issues.append(label)
        return ("NEEDS_REVISION" if issues else "PASS"), issues

    @classmethod
    def sanitize(cls, text: str) -> Tuple[str, str, List[str]]:
        status, issues = cls.review(text)
        if status == "NEEDS_REVISION":
            safe_message = (
                "I can't provide that specific medical instruction or definitive diagnosis. "
                "Please consult a qualified healthcare professional for personalized guidance. "
                "If you may be experiencing a medical emergency, contact local emergency services now."
            )
            return safe_message, status, issues
        return text, "PASS", []


# ============================================================
# 10 TASK AGENTS
# ============================================================

class EmergencyTriageAgent(BaseAgent):
    name = "Emergency Triage Agent"

    EMERGENCY_TERMS = [
        "chest pain",
        "difficulty breathing",
        "can't breathe",
        "cannot breathe",
        "unconscious",
        "severe bleeding",
        "stroke",
        "seizure",
        "fainted",
        "overdose",
        "suicidal",
        "severe allergic reaction",
    ]

    def run(self, query: str) -> AgentResult:
        response = (
            "This message may describe a medical emergency. "
            "Do not rely on the chatbot for diagnosis or treatment. "
            "Contact your local emergency service or go to the nearest emergency department now. "
            "If possible, have someone stay with you and follow instructions from emergency professionals."
        )
        return AgentResult(
            task="Emergency / urgent escalation",
            agent=self.name,
            response=response,
            page="AI Assistant",
            data={"urgency": "Emergency"},
        )

    @classmethod
    def is_emergency(cls, query: str) -> bool:
        q = query.lower()
        return any(term in q for term in cls.EMERGENCY_TERMS)


class PatientAssistantAgent(BaseAgent):
    name = "Patient Assistant Agent"

    def run(self, query: str) -> AgentResult:
        system = """
You are a general healthcare information assistant in an academic multi-agent demo.
Provide clear, concise, general information.
Do not diagnose a person, prescribe medicine, give individualized dosage instructions,
promise outcomes, or replace a licensed healthcare professional.
For emergency symptoms, direct the user to urgent medical care.
Use plain language and structure the answer with headings when helpful.
"""
        fallback = (
            "I can provide general healthcare information, explain common concepts, "
            "and help you choose the right task in this application. "
            "For personal diagnosis or treatment decisions, consult a qualified clinician."
        )
        response = llm_chat(system, query, fallback)
        response, status, issues = ClinicalSafetyReviewerAgent.sanitize(response)
        return AgentResult(
            task="General patient assistance",
            agent=self.name,
            response=response,
            page="AI Assistant",
            safety_status=status,
            safety_notes=issues,
        )


class SymptomTriageAgent(BaseAgent):
    name = "Symptom Triage Agent"

    SAME_DAY_TERMS = [
        "high fever",
        "persistent vomiting",
        "severe pain",
        "worsening pain",
        "dehydration",
        "blood in stool",
        "blood in vomit",
        "confusion",
        "fainting",
    ]

    def run(self, symptoms: str, duration: str = "") -> AgentResult:
        if EmergencyTriageAgent.is_emergency(symptoms):
            return EmergencyTriageAgent().run(symptoms)

        q = symptoms.lower()
        urgency = "Routine review"
        if any(term in q for term in self.SAME_DAY_TERMS):
            urgency = "Consider same-day clinical evaluation"

        system = """
You are a cautious symptom-triage information agent.
You are not a diagnostician. Explain that symptoms can have many causes.
Give general red-flag guidance, suggest the type of clinician that may be relevant,
and recommend seeking professional care when symptoms are persistent, severe, or worsening.
Never prescribe or give dosage instructions.
"""
        user = f"Symptoms: {symptoms}\nDuration: {duration or 'Not provided'}"
        fallback = (
            "Symptoms alone cannot establish a diagnosis. Consider a clinical evaluation, "
            "especially if symptoms are severe, persistent, or worsening."
        )
        response = llm_chat(system, user, fallback)
        response, status, issues = ClinicalSafetyReviewerAgent.sanitize(response)

        return AgentResult(
            task="Symptom triage and urgency guidance",
            agent=self.name,
            response=response,
            page="Symptom Triage",
            data={"urgency": urgency},
            safety_status=status,
            safety_notes=issues,
        )


class DoctorRecommendationAgent(BaseAgent):
    name = "Doctor Recommendation Agent"

    SYMPTOM_SPECIALTY = {
        "stomach": "Gastroenterology",
        "abdomen": "Gastroenterology",
        "gastric": "Gastroenterology",
        "acidity": "Gastroenterology",
        "period": "Gynaecology",
        "pregnan": "Gynaecology",
        "pcos": "Gynaecology",
        "heart": "Cardiology",
        "palpitation": "Cardiology",
        "headache": "Neurology",
        "migraine": "Neurology",
        "nerve": "Neurology",
    }

    def infer_specialty(self, query: str) -> Optional[str]:
        q = query.lower()
        for specialty in specialties():
            if specialty.lower() in q:
                return specialty
        for keyword, specialty in self.SYMPTOM_SPECIALTY.items():
            if keyword in q:
                return specialty
        return None

    def recommend(self, specialty: str) -> List[Dict[str, str]]:
        return [d for d in DOCTORS if d["specialty"].lower() == specialty.lower()]

    def run(self, query: str, specialty: Optional[str] = None) -> AgentResult:
        chosen = specialty or self.infer_specialty(query)
        if chosen:
            doctors = self.recommend(chosen)
            response = (
                f"### Suggested specialty: {chosen}\n\n"
                "The directory below is **demo data** for the academic project.\n\n"
                + "\n".join(
                    f"- **{d['name']}** · {d['specialty']} · {d['mode']} · {d['city']}"
                    for d in doctors
                )
            )
            return AgentResult(
                task="Doctor discovery and recommendation",
                agent=self.name,
                response=response,
                page="Find a Doctor",
                data={"specialty": chosen, "doctors": doctors},
            )

        return AgentResult(
            task="Doctor discovery and recommendation",
            agent=self.name,
            response=(
                "I can recommend from the demo directory once a specialty or symptom is specified. "
                "Try cardiology, neurology, gastroenterology, gynaecology, or general medicine."
            ),
            page="Find a Doctor",
            data={"specialty": "", "doctors": []},
        )


class AppointmentAgent(BaseAgent):
    name = "Appointment Agent"

    def book(self, patient: str, doctor: str, appointment_date: date, reason: str) -> int:
        with db_connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO appointments(patient, doctor, appointment_date, reason, status, created_at)
                VALUES (?, ?, ?, ?, 'Booked', ?)
                """,
                (
                    patient,
                    doctor,
                    appointment_date.isoformat(),
                    reason,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def reschedule(self, appointment_id: int, new_date: date) -> bool:
        with db_connect() as conn:
            cur = conn.execute(
                """
                UPDATE appointments
                SET appointment_date = ?, status = 'Rescheduled'
                WHERE id = ? AND status NOT IN ('Cancelled')
                """,
                (new_date.isoformat(), appointment_id),
            )
            conn.commit()
            return cur.rowcount > 0

    def cancel(self, appointment_id: int) -> bool:
        with db_connect() as conn:
            cur = conn.execute(
                "UPDATE appointments SET status='Cancelled' WHERE id=?",
                (appointment_id,),
            )
            conn.commit()
            return cur.rowcount > 0

    def run(self, query: str) -> AgentResult:
        return AgentResult(
            task="Appointment management",
            agent=self.name,
            response=(
                "The Supervisor routed this request to Appointment Agent. "
                "Use the Appointment Management panel to book, reschedule, or cancel an appointment."
            ),
            page="Appointments",
        )


class MedicalReportAgent(BaseAgent):
    name = "Medical Report Analysis Agent"

    def run(self, report_text: str, title: str = "Medical Report") -> AgentResult:
        if not report_text.strip():
            return AgentResult(
                task="Medical report summarization",
                agent=self.name,
                response="Paste report text or upload a report file to continue.",
                page="Medical Reports",
            )

        clipped = report_text[:12000]
        system = """
You are a medical-report summarization assistant in an academic demo.
Summarize the provided report without diagnosing the patient or prescribing treatment.
Separate objective information from interpretation.
Highlight abnormal/high/low/positive/negative terms exactly as written when possible.
End with questions or discussion points the patient can take to a qualified clinician.
Do not provide medication doses or personalized treatment instructions.
"""
        user = f"Report title: {title}\n\nReport text:\n{clipped}"
        fallback = (
            "The report was received. A clinician should interpret the results in the "
            "context of symptoms, history, examination, and reference ranges."
        )
        response = llm_chat(system, user, fallback)
        response, status, issues = ClinicalSafetyReviewerAgent.sanitize(response)

        with db_connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO reports(title, report_text, summary, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    title[:200],
                    report_text[:20000],
                    response[:15000],
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
            report_id = int(cur.lastrowid)

        return AgentResult(
            task="Medical report summarization",
            agent=self.name,
            response=response,
            page="Medical Reports",
            data={"report_id": report_id, "title": title},
            safety_status=status,
            safety_notes=issues,
        )


class MedicationInfoAgent(BaseAgent):
    name = "Medication Safety Information Agent"

    def run(self, medication: str, question: str) -> AgentResult:
        system = """
You provide general medication information for an academic healthcare assistant.
Explain what a medication is commonly used for, common precautions, and why a clinician/pharmacist
should be consulted for personal use.
Do not prescribe, recommend a dose, tell the user to start/stop a medication, or make a diagnosis.
When a user asks for dosing, respond that individualized dosing must come from a qualified professional.
"""
        user = f"Medication: {medication}\nQuestion: {question}"
        fallback = (
            "I can provide general information about a medication, but personal dosing, "
            "starting, stopping, or changing treatment should be discussed with a qualified clinician or pharmacist."
        )
        response = llm_chat(system, user, fallback)
        response, status, issues = ClinicalSafetyReviewerAgent.sanitize(response)

        return AgentResult(
            task="Medication information and safety",
            agent=self.name,
            response=response,
            page="Medication Info",
            data={"medication": medication},
            safety_status=status,
            safety_notes=issues,
        )


class PatientEducationAgent(BaseAgent):
    name = "Patient Education Agent"

    def run(self, topic: str, question: str = "") -> AgentResult:
        system = """
You are a patient-education assistant.
Explain healthcare topics in simple, accurate language for a general audience.
Define important terms, explain common causes/risk factors at a high level, and describe
when someone should discuss the topic with a healthcare professional.
Do not diagnose, prescribe, or give individualized treatment.
"""
        user = f"Topic: {topic}\nQuestion: {question or 'Give a simple patient-friendly explanation.'}"
        fallback = (
            "This topic can be explained at a general level, but personal medical decisions "
            "should be discussed with a qualified healthcare professional."
        )
        response = llm_chat(system, user, fallback)
        response, status, issues = ClinicalSafetyReviewerAgent.sanitize(response)
        return AgentResult(
            task="Patient education",
            agent=self.name,
            response=response,
            page="Patient Education",
            data={"topic": topic},
            safety_status=status,
            safety_notes=issues,
        )


class CustomerSupportAgent(BaseAgent):
    name = "Customer Support Agent"

    def priority(self, issue: str) -> str:
        q = issue.lower()
        high = ["payment failed", "payment issue", "refund", "unable to book", "account locked"]
        medium = ["delay", "problem", "issue", "complaint"]
        if any(x in q for x in high):
            return "High"
        if any(x in q for x in medium):
            return "Medium"
        return "Low"

    def create_ticket(self, patient: str, issue: str) -> Tuple[int, str]:
        priority = self.priority(issue)
        with db_connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO tickets(patient, issue, priority, status, created_at)
                VALUES (?, ?, ?, 'Open', ?)
                """,
                (
                    patient,
                    issue,
                    priority,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
            return int(cur.lastrowid), priority

    def run(self, query: str) -> AgentResult:
        return AgentResult(
            task="Customer support and ticketing",
            agent=self.name,
            response=(
                "The Supervisor routed this request to Customer Support Agent. "
                "Use the Support panel to create and track a ticket."
            ),
            page="Support",
        )


class FollowUpAgent(BaseAgent):
    name = "Follow-up & Care Guidance Agent"

    def run(self, concern: str) -> AgentResult:
        system = """
You are a follow-up guidance assistant.
Generate a practical list of general follow-up questions and observations a patient can discuss
with a healthcare professional after an appointment or test.
Do not change medication, prescribe treatment, diagnose, or provide dosage instructions.
"""
        fallback = (
            "Useful follow-up topics can include symptom changes, test-result questions, "
            "expected next steps, warning signs, and when to schedule the next professional review."
        )
        response = llm_chat(system, concern, fallback)
        response, status, issues = ClinicalSafetyReviewerAgent.sanitize(response)
        return AgentResult(
            task="Follow-up and care guidance",
            agent=self.name,
            response=response,
            page="Follow-up",
            data={"concern": concern},
            safety_status=status,
            safety_notes=issues,
        )


# ============================================================
# SUPERVISOR AGENT
# ============================================================

class SupervisorAgent(BaseAgent):
    name = "Supervisor / Orchestrator Agent"

    def __init__(self):
        self.patient = PatientAssistantAgent()
        self.emergency = EmergencyTriageAgent()
        self.symptom = SymptomTriageAgent()
        self.doctor = DoctorRecommendationAgent()
        self.appointment = AppointmentAgent()
        self.report = MedicalReportAgent()
        self.medication = MedicationInfoAgent()
        self.education = PatientEducationAgent()
        self.support = CustomerSupportAgent()
        self.followup = FollowUpAgent()

    @staticmethod
    def route_task(query: str) -> str:
        q = query.lower()

        if EmergencyTriageAgent.is_emergency(q):
            return "emergency"

        if any(x in q for x in [
            "medical report", "lab report", "blood report", "test report",
            "test result", "scan report", "pathology report",
        ]):
            return "report"

        if any(x in q for x in [
            "follow up", "follow-up", "next step", "after my appointment",
            "after visit", "what should i ask", "what should i monitor",
        ]):
            return "followup"

        if any(x in q for x in [
            "book appointment", "schedule appointment", "reschedule",
            "cancel appointment", "appointment",
        ]):
            return "appointment"

        if any(x in q for x in [
            "find a doctor", "doctor", "specialist", "cardiologist",
            "neurologist", "gastroenterologist", "gynaecologist",
        ]):
            return "doctor"

        if any(x in q for x in [
            "medicine", "medication", "tablet", "drug", "dose", "dosage",
            "side effect", "interaction",
        ]):
            return "medication"

        if any(x in q for x in [
            "support", "complaint", "refund", "payment", "ticket",
            "account", "website issue",
        ]):
            return "support"

        if any(x in q for x in [
            "symptom", "symptoms", "pain", "fever", "cough", "headache",
            "vomiting", "diarrhea", "dizziness", "rash",
        ]):
            return "symptom"

        if any(x in q for x in [
            "explain", "what is", "meaning of", "learn about",
            "education", "information about", "difference between",
        ]):
            return "education"


        return "patient"

    def run(self, query: str) -> AgentResult:
        route = self.route_task(query)

        if route == "emergency":
            result = self.emergency.run(query)
        elif route == "report":
            result = self.report.run("")
        elif route == "appointment":
            result = self.appointment.run(query)
        elif route == "doctor":
            result = self.doctor.run(query)
        elif route == "medication":
            medication = "Not specified"
            result = self.medication.run(medication, query)
        elif route == "support":
            result = self.support.run(query)
        elif route == "symptom":
            result = self.symptom.run(query)
        elif route == "education":
            result = self.education.run(query)
        elif route == "followup":
            result = self.followup.run(query)
        else:
            result = self.patient.run(query)

        insert_interaction(result.task, result.agent, query, result.response)
        return result


SUPERVISOR = SupervisorAgent()


# ============================================================
# UI HELPERS


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="hero">
            <div class="hero-title">{title}</div>
            <div class="hero-subtitle">{subtitle}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: Any) -> None:
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-accent"></div>
            <div class="metric-number">{value}</div>
            <div class="metric-label">{label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_result(result: Dict[str, Any]) -> None:
    st.markdown(f'<span class="agent-badge">{result.get("agent", "Agent")}</span>', unsafe_allow_html=True)
    safety_status = result.get("safety_status", "PASS")
    if safety_status == "PASS":
        st.markdown('<span class="safety-pass">Safety review: PASS</span>', unsafe_allow_html=True)
    else:
        st.markdown('<span class="safety-revise">Safety review: NEEDS REVISION / guarded</span>', unsafe_allow_html=True)
    st.markdown("")
    if result.get("data", {}).get("urgency"):
        st.info(f"Urgency guidance: **{result['data']['urgency']}**")
    if result.get("data", {}).get("specialty"):
        st.success(f"Suggested specialty: **{result['data']['specialty']}**")
    st.markdown(result.get("response", ""))
    if result.get("safety_notes"):
        with st.expander("Safety reviewer notes"):
            for note in result["safety_notes"]:
                st.write("• " + note)


def show_last_route(page: str) -> None:
    result = st.session_state.get("routed_result")
    if not result or result.get("page") != page:
        return
    st.markdown(
        """
        <div class="route-card">
            <div class="route-title">Supervisor handoff completed</div>
            The request was automatically routed to the relevant specialist agent.
        </div>
        """,
        unsafe_allow_html=True,
    )
    render_result(result)
    if st.button("Dismiss routed response", key="dismiss_routed"):
        st.session_state.pop("routed_result", None)
        st.rerun()


def go_to(page: str) -> None:
    st.session_state["nav_target"] = page
    st.rerun()


# ============================================================
# SESSION STATE / AUTO NAVIGATION
# ============================================================

if "nav" not in st.session_state:
    st.session_state["nav"] = "Top Docs Home"

if "nav_target" in st.session_state:
    target = st.session_state.pop("nav_target")
    if target in PAGES:
        st.session_state["nav"] = target

# Reset existing Streamlit sessions to the new Top Docs landing page once.
# This avoids a previously saved "Dashboard" selection bypassing the homepage.
_NAV_VERSION = "topdocs-home-v2"
if st.session_state.get("_nav_version") != _NAV_VERSION:
    st.session_state["nav"] = "Top Docs Home"
    st.session_state["_nav_version"] = _NAV_VERSION

# Open the assistant directly from the floating Top Docs widget.
try:
    assistant_requested = st.query_params.get("assistant") == "1"
except Exception:
    assistant_requested = False
if assistant_requested:
    st.session_state["nav"] = "AI Assistant"
    try:
        del st.query_params["assistant"]
    except Exception:
        pass

nav = st.session_state.get("nav", "Top Docs Home")

if "chat_messages" not in st.session_state:
    st.session_state["chat_messages"] = [
        {
            "role": "assistant",
            "content": (
                "Hi! I am the MediAgent Supervisor. Tell me what you need and I will route "
                "the request to the appropriate specialist agent."
            ),
        }
    ]


# ============================================================
# SIDEBAR

if st.session_state.get("nav") != "Top Docs Home":
    with st.sidebar:
        st.markdown(
            """
            <div class="brand-wrap">
                <div class="brand-mark">✦</div>
                <div>
                    <div class="brand-name">MediAgent AI</div>
                    <div class="brand-sub">Top Docs Assistant</div>
                </div>
            </div>
            <div class="sidebar-section">Workspace</div>
            """,
            unsafe_allow_html=True,
        )

        nav = st.radio(
            "Navigation",
            PAGES[1:],
            key="nav",
            format_func=lambda p: f"{PAGE_ICONS.get(p, '•')}  {p}",
            label_visibility="collapsed",
        )

        ok, provider_text = llm_status()
        dot_class = "" if ok else "off"
        provider_label = "AI Service Online" if ok else "AI Service Check"
        st.markdown(
            f"""
            <div class="sidebar-status">
                <div class="sidebar-status-row">
                    <div style="display:flex;align-items:center;gap:9px;">
                        <span class="status-dot {dot_class}"></span>
                        <span class="status-title">{provider_label}</span>
                    </div>
                </div>
                <div class="status-text">{provider_text}</div>
                <div class="status-text" style="margin-top:8px;">10 specialist tasks · Supervisor · Safety Reviewer</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f'<div style="margin:11px 6px 0;color:#8999ad;font-size:10px;line-height:1.45;">{DEMO_DISCLAIMER}</div>',
            unsafe_allow_html=True,
        )


# ============================================================
# GLOBAL HEADER / LANDING EXPERIENCE

if nav == "Top Docs Home":
    st.html(
        textwrap.dedent("""
        <div class="td-wrap">
          <div class="td-nav">
            <div class="td-brand">
              <div class="td-logo"><img src="__LOGO_SRC__" alt="Top Docs"></div>
              <span>Top Docs</span>
            </div>
            <nav class="td-menu" aria-label="Main navigation">
              <a href="#how-it-works">How it works</a><a href="#specialties">Specialties</a><a href="#our-doctors">Our doctors</a><a href="#questions">Questions</a>
            </nav>
            <a class="td-nav-cta" href="?assistant=1">Find my specialist</a>
          </div>

          <div class="td-hero" id="how-it-works">
            <div>
              <div class="td-eyebrow">Online specialist consultations and second opinions</div>
              <h1 class="td-title">India's top<br>doctors,<br><em>now within<br>reach.</em></h1>
              <div class="td-copy">Get a specialist consultation from doctors trained at leading medical institutes.</div>
              <a class="td-main-cta" href="?assistant=1">Find my specialist <span class="arrow">→</span></a>
              <div class="td-bullets">
                <div class="td-bullet"><i></i><span>Transparent fee before checkout</span></div>
                <div class="td-bullet"><i></i><span>Consultation timing coordinated on WhatsApp</span></div>
                <div class="td-bullet"><i></i><span>Updates on WhatsApp</span></div>
              </div>
            </div>

            <div class="td-showcase">
              <div class="td-ghost"></div>
              <div class="td-card">
                <div class="td-tag">WHAT YOU GET</div>
                <div class="td-card-top"><div class="td-card-title">Your online consultation</div><div class="td-card-small">BEFORE YOU PAY</div></div>
                <div class="td-doctors" id="our-doctors">
                  <div class="td-doctor"><img src="__DOC1_SRC__" alt="Doctor"></div>
                  <div class="td-doctor"><img src="__DOC2_SRC__" alt="Doctor"></div>
                  <div class="td-doctor"><img src="__DOC3_SRC__" alt="Doctor"></div>
                </div>
                <div class="td-row"><span>Request</span><strong>Reviewed by the care team</strong></div>
                <div class="td-row"><span>Consultation</span><strong>Timing coordinated on WhatsApp</strong></div>
                <div class="td-row"><span>Next steps</span><strong>Shared on WhatsApp</strong></div>
                <div class="td-disclaimer">Institute names show where a doctor trained. They do not mean the institute employs or endorses the doctor or Top Docs.</div>
              </div>
            </div>
          </div>
        </div>

        <section class="td-institutes" id="specialties">
          <div class="td-wrap">
            <div class="td-institutes-title">Doctors trained at leading medical institutes</div>
            <div class="td-logos">
              <div class="td-inst"><div class="td-inst-mark">◉</div>AIIMS</div>
              <div class="td-inst"><div class="td-inst-mark">◍</div>PGIMER</div>
              <div class="td-inst"><div class="td-inst-mark">◆</div>Tata Memorial</div>
              <div class="td-inst"><div class="td-inst-mark">◌</div>JIPMER</div>
              <div class="td-inst"><div class="td-inst-mark">◎</div>CMC Vellore</div>
            </div>
            <div class="td-footer-note" id="questions">Institute names describe where doctors trained. They do not mean the institutes employ, partner with or endorse Top Docs.</div>
          </div>
        </section>

        <div class="td-assistant-note">Your Top Docs AI assistant</div>
        <a id="assistant" class="td-fab" href="?assistant=1" aria-label="Open MediAgent AI assistant">
          <span class="td-fab-label">Ask MediAgent</span>
          <span class="td-fab-btn">✦</span>
          <span class="td-fab-pulse"></span>
        </a>
        """).replace("__LOGO_SRC__", __TOPDOCS_LOGO_SRC)
            .replace("__DOC1_SRC__", __DOC1_SRC)
            .replace("__DOC2_SRC__", __DOC2_SRC)
            .replace("__DOC3_SRC__", __DOC3_SRC),
    )
else:
    st.markdown(
        f"""
        <div class="page-topbar">
            <div class="eyebrow">Top Docs · {APP_SUBTITLE}</div>
            <div class="top-status">
                <span style="width:7px;height:7px;border-radius:50%;background:#1aa36a;display:inline-block;"></span>
                AI workspace · {datetime.now().strftime("%d %b %Y · %I:%M %p")}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# DASHBOARD

if nav != "Top Docs Home":
    c_back, c_space = st.columns([1, 5])
    with c_back:
        if st.button("← Top Docs", key="back_to_topdocs"):
            st.session_state["nav_target"] = "Top Docs Home"
            st.rerun()

if nav == "Dashboard":
    hero(
        "Healthcare AI Command Center",
        "A unified workspace for intelligent patient support, specialist routing, clinical-document assistance, appointments, and service operations.",
    )

    cols = st.columns(4, gap="medium")
    with cols[0]: metric_card("Appointments", get_scalar("SELECT COUNT(*) FROM appointments"))
    with cols[1]: metric_card("Open Tickets", get_scalar("SELECT COUNT(*) FROM tickets WHERE status='Open'"))
    with cols[2]: metric_card("Saved Reports", get_scalar("SELECT COUNT(*) FROM reports"))
    with cols[3]: metric_card("AI Interactions", get_scalar("SELECT COUNT(*) FROM interactions"))

    st.markdown("<div class='section-title'>How the system works</div>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3, gap="medium")
    architecture = [
        (c1, "01", "Supervisor Orchestrator", "Understands the request, classifies intent, and hands it to the right specialist agent.", "⌁"),
        (c2, "02", "Specialist Agents", "Ten task-focused agents handle triage, doctors, reports, medication info, support, and follow-up.", "✦"),
        (c3, "03", "Clinical Safety Reviewer", "Checks generated responses for risky diagnosis, dosing, guarantees, and unsafe instructions.", "✓"),
    ]
    for col, number, title, desc, icon in architecture:
        with col:
            st.markdown(
                f"""
                <div class="card">
                    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;">
                        <div>
                            <div class="card-kicker">Stage {number}</div>
                            <h3>{title}</h3>
                        </div>
                        <div class="card-icon">{icon}</div>
                    </div>
                    <p>{desc}</p>
                </div>
                """, unsafe_allow_html=True,
            )

    st.markdown("<div class='section-title'>Available capabilities</div>", unsafe_allow_html=True)
    tasks = [
        ("Emergency Triage", "Urgent escalation and emergency routing", "!"),
        ("General Patient Assistant", "General healthcare information", "✦"),
        ("Symptom Triage", "General urgency and specialist guidance", "♥"),
        ("Doctor Discovery", "Specialty matching and demo directory", "⌕"),
        ("Appointment Management", "Book, reschedule, and cancel", "◷"),
        ("Medical Report Analysis", "Summarization and discussion points", "▤"),
        ("Medication Information", "General medication safety information", "Rx"),
        ("Patient Education", "Plain-language healthcare explanations", "i"),
        ("Customer Support", "Issue classification and support tickets", "◇"),
        ("Follow-up Guidance", "Questions and observations for clinician follow-up", "↻"),
    ]
    for row_start in range(0, len(tasks), 2):
        left, right = st.columns(2, gap="medium")
        for col, idx in [(left, row_start), (right, row_start + 1)]:
            if idx >= len(tasks): continue
            name, desc, icon = tasks[idx]
            with col:
                st.markdown(
                    f"""
                    <div class="card">
                        <div style="display:flex;gap:13px;align-items:center;">
                            <div class="card-icon" style="margin:0;flex:0 0 auto;">{icon}</div>
                            <div>
                                <h3 style="margin-bottom:3px;">{idx+1:02d} · {name}</h3>
                                <p>{desc}</p>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True,
                )

    st.markdown(
        """
        <div class="route-card" style="margin-top:8px;">
            <div class="route-title">Quick demo path</div>
            Open <b>AI Assistant</b> and type a natural-language request such as <i>“I need a cardiologist”</i>, <i>“I want to book an appointment”</i>, or <i>“I have a headache”</i>.
        </div>
        """, unsafe_allow_html=True,
    )


# ============================================================
# AI ASSISTANT
# ============================================================

elif nav == "AI Assistant":
    hero(
        "AI Patient Assistant",
        "Ask once. The Supervisor identifies the task and hands it off automatically.",
    )

    show_last_route("AI Assistant")

    st.markdown("### Conversation")

    for msg in st.session_state["chat_messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_prompt = st.chat_input("Describe what you need help with…")

    if user_prompt and user_prompt.strip():
        user_prompt = user_prompt.strip()
        st.session_state["chat_messages"].append({"role": "user", "content": user_prompt})

        result = SUPERVISOR.run(user_prompt)

        st.session_state["chat_messages"].append(
            {
                "role": "assistant",
                "content": (
                    f"**Supervisor → {result.agent}**\n\n"
                    f"{result.response}"
                ),
            }
        )

        st.session_state["routed_result"] = result.as_dict()
        go_to(result.page)


# ============================================================
# FIND A DOCTOR
# ============================================================

elif nav == "Find a Doctor":
    hero(
        "Find a Doctor",
        "The Doctor Recommendation Agent maps a specialty or symptom to the demo directory.",
    )

    show_last_route("Find a Doctor")

    with st.form("doctor_form"):
        selected = st.selectbox("Specialty", ["Auto-detect"] + specialties())
        symptom_text = st.text_input(
            "Describe your concern (optional)",
            placeholder="e.g. frequent stomach pain, headache, irregular periods",
        )
        submitted = st.form_submit_button("Find matching doctors", type="primary")

    if submitted:
        query = symptom_text.strip()
        specialty = None if selected == "Auto-detect" else selected
        result = SUPERVISOR.doctor.run(query, specialty)
        st.session_state["doctor_result"] = result.as_dict()
        st.session_state["routed_result"] = result.as_dict()

    if "doctor_result" in st.session_state:
        render_result(st.session_state["doctor_result"])

    st.caption("Demo directory only. Replace sample doctors with an approved clinical directory before real-world deployment.")


# ============================================================
# APPOINTMENTS
# ============================================================

elif nav == "Appointments":
    hero(
        "Appointment Management",
        "Book, reschedule, and cancel appointments using the Appointment Agent.",
    )

    show_last_route("Appointments")

    action = st.segmented_control(
        "Action",
        ["Book", "Reschedule", "Cancel"],
        default="Book",
    )

    if action == "Book":
        with st.form("book_appointment"):
            patient = st.text_input("Patient name")
            doctor = st.selectbox("Doctor", [d["name"] for d in DOCTORS])
            appt_date = st.date_input("Appointment date", min_value=date.today())
            reason = st.text_area("Reason for appointment")
            submitted = st.form_submit_button("Create appointment", type="primary")

        if submitted:
            if not patient.strip() or not reason.strip():
                st.warning("Please fill in patient name and reason.")
            else:
                appointment_id = SUPERVISOR.appointment.book(
                    patient.strip(),
                    doctor,
                    appt_date,
                    reason.strip(),
                )
                response = f"Appointment **#{appointment_id}** created for **{patient.strip()}** with **{doctor}** on **{appt_date.isoformat()}**."
                st.success(response)
                insert_interaction("Appointment booking", SUPERVISOR.appointment.name, reason, response)

    elif action == "Reschedule":
        rows = fetch_rows(
            "SELECT id, patient, doctor, appointment_date, status FROM appointments WHERE status != 'Cancelled' ORDER BY id DESC"
        )
        if not rows:
            st.info("No active appointments to reschedule.")
        else:
            labels = {
                r["id"]: f"#{r['id']} · {r['patient']} · {r['doctor']} · {r['appointment_date']} · {r['status']}"
                for r in rows
            }
            appointment_id = st.selectbox(
                "Appointment",
                list(labels.keys()),
                format_func=lambda x: labels[x],
            )
            new_date = st.date_input("New date", min_value=date.today())
            if st.button("Reschedule appointment", type="primary"):
                ok = SUPERVISOR.appointment.reschedule(int(appointment_id), new_date)
                if ok:
                    st.success(f"Appointment #{appointment_id} rescheduled to {new_date.isoformat()}.")
                else:
                    st.error("Unable to reschedule this appointment.")

    else:
        rows = fetch_rows(
            "SELECT id, patient, doctor, appointment_date, status FROM appointments WHERE status != 'Cancelled' ORDER BY id DESC"
        )
        if not rows:
            st.info("No active appointments to cancel.")
        else:
            labels = {
                r["id"]: f"#{r['id']} · {r['patient']} · {r['doctor']} · {r['appointment_date']} · {r['status']}"
                for r in rows
            }
            appointment_id = st.selectbox(
                "Appointment",
                list(labels.keys()),
                format_func=lambda x: labels[x],
            )
            if st.button("Cancel appointment", type="primary"):
                ok = SUPERVISOR.appointment.cancel(int(appointment_id))
                if ok:
                    st.success(f"Appointment #{appointment_id} cancelled.")
                else:
                    st.error("Unable to cancel this appointment.")

    st.markdown("### Appointment Records")
    rows = fetch_rows(
        """
        SELECT id, patient, doctor, appointment_date, reason, status, created_at
        FROM appointments ORDER BY id DESC
        """
    )
    if rows:
        st.dataframe([dict(r) for r in rows], use_container_width=True, hide_index=True)
    else:
        st.info("No appointments yet.")


# ============================================================
# MEDICAL REPORTS
# ============================================================

elif nav == "Medical Reports":
    hero(
        "Medical Report Analyzer",
        "Upload or paste a report and let the Report Analysis Agent create a patient-friendly summary.",
    )

    show_last_route("Medical Reports")

    title = st.text_input("Report title", value="Medical Report")
    uploaded = st.file_uploader(
        "Upload a TXT or PDF report",
        type=["txt", "pdf"],
    )

    report_text = st.text_area(
        "Or paste report text here",
        height=250,
        placeholder="Paste the report content…",
    )

    if uploaded is not None:
        try:
            if uploaded.name.lower().endswith(".txt"):
                report_text = uploaded.getvalue().decode("utf-8", errors="ignore")
                st.caption(f"Loaded {uploaded.name}")
            elif uploaded.name.lower().endswith(".pdf"):
                if PdfReader is None:
                    st.error("PDF support requires pypdf. Run: pip install pypdf")
                else:
                    reader = PdfReader(BytesIO(uploaded.getvalue()))
                    report_text = "\n".join(
                        page.extract_text() or "" for page in reader.pages
                    )
                    st.caption(f"Extracted text from {uploaded.name}")
        except Exception as exc:
            st.error(f"Could not read the file: {exc}")

    if st.button("Analyze & summarize report", type="primary"):
        if not report_text.strip():
            st.warning("Upload a report or paste its text before analyzing.")
        else:
            result = SUPERVISOR.report.run(report_text, title.strip() or "Medical Report")
            st.session_state["report_result"] = result.as_dict()

    if "report_result" in st.session_state:
        render_result(st.session_state["report_result"])

    st.markdown("### Saved Reports")
    rows = fetch_rows(
        "SELECT id, title, created_at FROM reports ORDER BY id DESC LIMIT 10"
    )
    if rows:
        st.dataframe([dict(r) for r in rows], use_container_width=True, hide_index=True)
    else:
        st.info("No report analyses stored yet.")


# ============================================================
# MEDICATION INFO
# ============================================================

elif nav == "Medication Info":
    hero(
        "Medication Information",
        "General medication information with explicit safety boundaries—no prescribing or dosage decisions.",
    )

    show_last_route("Medication Info")

    with st.form("medication_form"):
        medication = st.text_input("Medication name", placeholder="e.g. paracetamol")
        question = st.text_area(
            "What do you want to know?",
            placeholder="What is it commonly used for? What precautions are important?",
        )
        submitted = st.form_submit_button("Ask medication agent", type="primary")

    if submitted:
        if not medication.strip() or not question.strip():
            st.warning("Enter both the medication name and your question.")
        else:
            result = SUPERVISOR.medication.run(medication.strip(), question.strip())
            st.session_state["med_result"] = result.as_dict()

    if "med_result" in st.session_state:
        render_result(st.session_state["med_result"])


# ============================================================
# SYMPTOM TRIAGE
# ============================================================

elif nav == "Symptom Triage":
    hero(
        "Symptom Triage",
        "General urgency guidance—not a diagnosis.",
    )

    show_last_route("Symptom Triage")

    with st.form("symptom_form"):
        symptoms = st.text_area(
            "What symptoms are you experiencing?",
            height=160,
            placeholder="Describe symptoms, severity, and anything that has changed.",
        )
        duration = st.text_input("Duration", placeholder="e.g. 2 days")
        submitted = st.form_submit_button("Run triage agent", type="primary")

    if submitted:
        if not symptoms.strip():
            st.warning("Please describe your symptoms.")
        else:
            result = SUPERVISOR.symptom.run(symptoms.strip(), duration.strip())
            st.session_state["symptom_result"] = result.as_dict()

            if result.page != "Symptom Triage":
                st.session_state["routed_result"] = result.as_dict()
                go_to(result.page)

    if "symptom_result" in st.session_state:
        render_result(st.session_state["symptom_result"])


# ============================================================
# PATIENT EDUCATION
# ============================================================

elif nav == "Patient Education":
    hero(
        "Patient Education",
        "Understand healthcare topics in plain language.",
    )

    show_last_route("Patient Education")

    with st.form("education_form"):
        topic = st.text_input("Topic", placeholder="e.g. blood pressure")
        question = st.text_area(
            "Question",
            placeholder="Explain it simply, or ask a specific question.",
        )
        submitted = st.form_submit_button("Explain topic", type="primary")

    if submitted:
        if not topic.strip():
            st.warning("Enter a topic.")
        else:
            result = SUPERVISOR.education.run(topic.strip(), question.strip())
            st.session_state["education_result"] = result.as_dict()

    if "education_result" in st.session_state:
        render_result(st.session_state["education_result"])


# ============================================================
# SUPPORT
# ============================================================

elif nav == "Support":
    hero(
        "Healthcare Support",
        "Create and track customer-support tickets.",
    )

    show_last_route("Support")

    with st.form("support_form"):
        patient = st.text_input("Your name")
        issue = st.text_area(
            "Describe your issue",
            placeholder="Payment, refund, account, appointment or website issue…",
        )
        submitted = st.form_submit_button("Create support ticket", type="primary")

    if submitted:
        if not patient.strip() or not issue.strip():
            st.warning("Please fill in all fields.")
        else:
            ticket_id, priority = SUPERVISOR.support.create_ticket(
                patient.strip(),
                issue.strip(),
            )
            response = (
                f"Ticket **#{ticket_id}** created successfully. "
                f"Priority: **{priority}**. Status: **Open**."
            )
            st.success(response)
            insert_interaction("Customer support", SUPERVISOR.support.name, issue, response)

    st.markdown("### Ticket Records")
    rows = fetch_rows(
        """
        SELECT id, patient, issue, priority, status, created_at
        FROM tickets ORDER BY id DESC
        """
    )
    if rows:
        st.dataframe([dict(r) for r in rows], use_container_width=True, hide_index=True)
    else:
        st.info("No support tickets yet.")


# ============================================================
# FOLLOW-UP
# ============================================================

elif nav == "Follow-up":
    hero(
        "Follow-up Guidance",
        "Generate questions and observations to discuss with a qualified healthcare professional.",
    )

    show_last_route("Follow-up")

    with st.form("followup_form"):
        concern = st.text_area(
            "What are you following up on?",
            height=180,
            placeholder="e.g. questions after my consultation, recent test result, ongoing symptom",
        )
        submitted = st.form_submit_button("Generate follow-up guidance", type="primary")

    if submitted:
        if not concern.strip():
            st.warning("Enter a follow-up concern.")
        else:
            result = SUPERVISOR.followup.run(concern.strip())
            st.session_state["followup_result"] = result.as_dict()

    if "followup_result" in st.session_state:
        render_result(st.session_state["followup_result"])


# ============================================================
# FOOTER
# ============================================================

st.divider()
st.caption(
    f"{APP_TITLE} · {DEMO_DISCLAIMER} · "
    f"LLM: {LLM_PROVIDER}/{GROQ_MODEL if LLM_PROVIDER == "groq" else OLLAMA_MODEL} · Database: {DB_PATH}"
)
