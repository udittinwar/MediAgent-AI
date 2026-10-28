
import os
from dotenv import load_dotenv

load_dotenv(override=True)
import base64
from io import BytesIO
import re
import json
import hashlib
import hmac
import secrets
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterator, List, Optional, Tuple

import psycopg
from psycopg.rows import dict_row
from psycopg.errors import UniqueViolation

import requests
import streamlit as st
import streamlit.components.v1 as components
import textwrap

try:
    import razorpay
except ImportError:
    razorpay = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


# ============================================================
# CONFIG
# ============================================================

APP_TITLE = "MediAgent AI"
APP_SUBTITLE = "Multi-Agent Healthcare Assistant"
DATABASE_URL = (
    os.getenv("DATABASE_URL", "").strip()
    or os.getenv("HEALTHCARE_DATABASE_URL", "").strip()
)

# Also support the DB_* variables used by the standalone database module.
if not DATABASE_URL:
    db_host = os.getenv("DB_HOST", "localhost")
    db_port = os.getenv("DB_PORT", "5432")
    db_name = os.getenv("DB_NAME", "mediagent")
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "")
    if db_password:
        from urllib.parse import quote_plus
        DATABASE_URL = (
            f"postgresql://{quote_plus(db_user)}:{quote_plus(db_password)}"
            f"@{db_host}:{db_port}/{db_name}"
        )

if not DATABASE_URL:
    raise RuntimeError(
        "PostgreSQL is not configured. Set DATABASE_URL or DB_PASSWORD "
        "before starting Streamlit."
    )

# Cloud LLM (Groq) is the default because it is much faster for this demo.
# Ollama remains as an optional local fallback.
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "groq").lower()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:1b")

LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "45"))

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "").strip()
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "").strip()

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
    "Admin Panel",
    "Patient Portal",
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
    "Admin Panel": "⚙",
    "Patient Portal": "♙",
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
    html{scroll-behavior:smooth;scroll-padding-top:24px}
    .td-wrap{max-width:1180px;margin:0 auto;padding:0 24px}
    .td-hero,.td-institutes,.td-specialties,.td-faq,.td-showcase{scroll-margin-top:24px}
    .td-specialties{padding:52px 0;background:#f2f5f0;border-top:1px solid var(--td-line);border-bottom:1px solid var(--td-line)}
    .td-specialty-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:12px;margin-top:24px}
    .td-specialty{display:block;background:#fff;border:1px solid var(--td-line);border-radius:14px;padding:18px 12px;text-align:center;color:var(--td-ink)!important;text-decoration:none!important;font-size:13px;font-weight:800;transition:transform .18s ease,box-shadow .18s ease}
    .td-specialty:hover{transform:translateY(-2px);box-shadow:0 10px 24px rgba(23,59,52,.09)}
    .td-faq{padding:48px 0 24px}
    .td-faq-item{padding:18px 0;border-bottom:1px solid var(--td-line);color:#49655d;font-size:13px;line-height:1.65}
    .td-faq-item strong{display:block;color:var(--td-ink);font-size:14px;margin-bottom:5px}
    @media(max-width:700px){.td-specialty-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
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
# DATABASE - POSTGRESQL
# ============================================================


@contextmanager
def db_connect() -> Iterator[psycopg.Connection]:
    """Use the shared PostgreSQL connection configured in db.py."""
    from db import get_connection

    with get_connection() as conn:
        yield conn


# ============================================================
# AUTHENTICATION / ROLE MANAGEMENT
# ============================================================

def hash_password(password: str, salt: Optional[bytes] = None) -> str:
    """PBKDF2 password hashing using the Python standard library."""
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 310_000)
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split("$", 1)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 310_000
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def ensure_auth_schema() -> None:
    """Add authentication fields without dropping or replacing existing project data."""
    with db_connect() as conn:
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash TEXT")
        conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'patient'")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_unique ON users (LOWER(email))")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS auth_login_audit (
                id BIGSERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                event TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )"""
        )

    # The first admin is configured explicitly in .env; no hard-coded default password.
    admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    admin_password = os.getenv("ADMIN_PASSWORD", "")
    admin_name = os.getenv("ADMIN_NAME", "MediAgent Administrator").strip()
    if admin_email and admin_password:
        with db_connect() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE LOWER(email) = LOWER(%s)", (admin_email,)
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE users SET role='admin', password_hash=%s WHERE id=%s",
                    (hash_password(admin_password), row["id"]),
                )
            else:
                conn.execute(
                    """INSERT INTO users(name, email, password_hash, role)
                       VALUES (%s, %s, %s, 'admin')""",
                    (admin_name, admin_email, hash_password(admin_password)),
                )


def current_user() -> Optional[Dict[str, Any]]:
    user = st.session_state.get("auth_user")
    return user if isinstance(user, dict) else None


def current_patient_id() -> Optional[int]:
    user = current_user()
    if not user or user.get("role") != "patient":
        return None
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id FROM patients WHERE user_id=%s LIMIT 1", (user["id"],)
        ).fetchone()
        if row:
            return int(row["id"])
        row = conn.execute(
            "INSERT INTO patients(user_id) VALUES (%s) RETURNING id", (user["id"],)
        ).fetchone()
        return int(row["id"])


def auth_screen(admin_only: bool = False) -> None:
    st.markdown(
        "<div style='max-width:720px;margin:35px auto 10px;text-align:center'>"
        "<div style='font-size:13px;letter-spacing:.12em;color:#6d9688;font-weight:800'>TOP DOCS</div>"
        "<h1 style='color:#173b34'>MediAgent AI</h1>"
        "<p style='color:#64756f'>Sign in to securely access your healthcare workspace.</p></div>",
        unsafe_allow_html=True,
    )
    if admin_only:
        st.info("Administrator access only. Patient registration is available from the public patient journey.")
        login_tab = st.container()
        register_tab = None
    else:
        login_tab, register_tab = st.tabs(["Quick patient access", "Create patient account"])
    with login_tab:
        with st.form("auth_login_form"):
            email = st.text_input("Email", key="login_email").strip().lower()
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
        if submitted:
            if not email or not password:
                st.warning("Email and password are required.")
            else:
                with db_connect() as conn:
                    row = conn.execute(
                        """SELECT id, name, email, password_hash, role
                           FROM users WHERE LOWER(email)=LOWER(%s) LIMIT 1""",
                        (email,),
                    ).fetchone()
                    if row and row["password_hash"] and verify_password(password, row["password_hash"]) and (not admin_only or row["role"] == "admin"):
                        st.session_state["auth_user"] = {
                            "id": int(row["id"]), "name": row["name"],
                            "email": row["email"], "role": row["role"],
                        }
                        conn.execute(
                            "INSERT INTO auth_login_audit(user_id,event) VALUES (%s,'login_success')",
                            (row["id"],),
                        )
                        st.session_state["nav"] = "Admin Panel" if row["role"] == "admin" else "Dashboard"
                        st.rerun()
                    else:
                        st.error("Invalid administrator credentials." if admin_only else "Invalid email or password.")
    if register_tab is not None:
        with register_tab:
            st.caption("Patient registration only. Admin accounts are configured by the project administrator.")
            with st.form("auth_register_form"):
                name = st.text_input("Full name", key="register_name")
                email = st.text_input("Email address", key="register_email").strip().lower()
                phone = st.text_input("Phone (optional)", key="register_phone")
                password = st.text_input("Create password", type="password", key="register_password")
                confirm = st.text_input("Confirm password", type="password", key="register_confirm")
                submitted = st.form_submit_button("Create account", type="primary", use_container_width=True)
            if submitted:
                if not name.strip() or not email or "@" not in email:
                    st.warning("Enter your full name and a valid email address.")
                elif len(password) < 8:
                    st.warning("Use a password with at least 8 characters.")
                elif password != confirm:
                    st.warning("Passwords do not match.")
                else:
                    try:
                        with db_connect() as conn:
                            row = conn.execute(
                                """INSERT INTO users(name,email,phone,password_hash,role)
                                   VALUES (%s,%s,%s,%s,'patient') RETURNING id,name,email,role""",
                                (name.strip(), email, phone.strip() or None, hash_password(password)),
                            ).fetchone()
                            conn.execute("INSERT INTO patients(user_id) VALUES (%s)", (row["id"],))
                        st.success("Account created. You can now log in.")
                    except psycopg.errors.UniqueViolation:
                        st.error("An account with this email already exists.")
    st.caption(DEMO_DISCLAIMER)


def require_login() -> None:
    if not current_user():
        auth_screen()
        st.stop()


def audit_event(event: str) -> None:
    user = current_user()
    if user:
        with db_connect() as conn:
            conn.execute(
                "INSERT INTO auth_login_audit(user_id,event) VALUES (%s,%s)",
                (user["id"], event[:100]),
            )


def require_admin() -> bool:
    user = current_user()
    if not user or user.get("role") != "admin":
        st.error("Admin access is required for this action.")
        return False
    return True



def seed_demo_doctors() -> None:
    """Seed the demo doctor directory into the migration-managed schema.

    The database structure itself is created only by migrations/001_initial_schema.sql.
    This function only inserts the demo data required by the UI.
    """
    with db_connect() as conn:
        for doctor in DOCTORS:
            specialty_row = conn.execute(
                "SELECT id FROM specialties WHERE name = %s",
                (doctor["specialty"],),
            ).fetchone()

            if specialty_row:
                specialty_id = specialty_row["id"]
            else:
                specialty_row = conn.execute(
                    "INSERT INTO specialties(name) VALUES (%s) RETURNING id",
                    (doctor["specialty"],),
                ).fetchone()
                specialty_id = specialty_row["id"]

            existing = conn.execute(
                "SELECT id FROM doctors WHERE name = %s LIMIT 1",
                (doctor["name"],),
            ).fetchone()

            if not existing:
                conn.execute(
                    """
                    INSERT INTO doctors(name, email, specialty_id)
                    VALUES (%s, %s, %s)
                    """,
                    (
                        doctor["name"],
                        f"{doctor['name'].lower().replace('dr. ', '').replace(' ', '.')}@mediagent.local",
                        specialty_id,
                    ),
                )


def get_or_create_patient_by_phone(full_name: str, phone: str) -> int:
    """Resolve a demo patient by exact name + phone; create profile if needed."""
    name = full_name.strip()
    phone = re.sub(r"\s+", "", phone.strip())
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 10:
        raise ValueError("Enter a valid phone number with at least 10 digits.")
    if not name:
        raise ValueError("Enter your full name.")
    with db_connect() as conn:
        user = conn.execute(
            "SELECT id, name, phone FROM users WHERE LOWER(name)=LOWER(%s) AND regexp_replace(COALESCE(phone,''), '\D', '', 'g')=%s ORDER BY id LIMIT 1",
            (name, digits),
        ).fetchone()
        if user:
            user_id = int(user["id"])
        else:
            # Avoid silently linking a different person's records to this phone number.
            same_phone = conn.execute(
                "SELECT id FROM users WHERE regexp_replace(COALESCE(phone,''), '\D', '', 'g')=%s LIMIT 1",
                (digits,),
            ).fetchone()
            if same_phone:
                raise ValueError("This phone number is already linked to a different name. Please contact support.")
            email = f"patient.{digits}@phone.mediagent.local"
            try:
                user = conn.execute(
                    "INSERT INTO users(name,email,phone,role) VALUES (%s,%s,%s,'patient') RETURNING id",
                    (name, email, phone),
                ).fetchone()
            except UniqueViolation:
                user = conn.execute(
                    "SELECT id FROM users WHERE LOWER(email)=LOWER(%s)", (email,)
                ).fetchone()
                if not user:
                    raise
            user_id = int(user["id"])
        patient = conn.execute("SELECT id FROM patients WHERE user_id=%s LIMIT 1", (user_id,)).fetchone()
        if patient:
            return int(patient["id"])
        patient = conn.execute("INSERT INTO patients(user_id) VALUES (%s) RETURNING id", (user_id,)).fetchone()
        return int(patient["id"])


def find_existing_patient_by_phone(full_name: str, phone: str) -> Optional[int]:
    """Look up an existing patient without creating a profile during lookup."""
    name = full_name.strip()
    digits = re.sub(r"\D", "", phone or "")
    if not name:
        raise ValueError("Enter your full name.")
    if len(digits) < 10:
        raise ValueError("Enter the same phone number used for booking (at least 10 digits).")
    with db_connect() as conn:
        row = conn.execute(
            """SELECT p.id
               FROM patients p
               JOIN users u ON u.id = p.user_id
               WHERE LOWER(TRIM(u.name)) = LOWER(TRIM(%s))
                 AND regexp_replace(COALESCE(u.phone, ''), '\\D', '', 'g') = %s
               ORDER BY p.id LIMIT 1""",
            (name, digits),
        ).fetchone()
    return int(row["id"]) if row else None


def infer_specialty_from_symptoms(symptoms: str) -> Optional[str]:
    """Simple demo routing; not a diagnosis."""
    text = (symptoms or "").lower()
    rules = [
        ("Gynaecology", ("period", "pregnan", "menstrual", "vaginal", "pcos", "gynec", "gynaec")),
        ("Gastroenterology", ("stomach", "abdominal", "acidity", "gastric", "digestion", "vomit", "diarrhea", "diarrhoea", "constipation", "liver")),
        ("Cardiology", ("chest pain", "heart", "palpitation", "blood pressure", "breathlessness")),
        ("Neurology", ("headache", "migraine", "seizure", "numbness", "dizziness", "nerve")),
    ]
    for specialty, keywords in rules:
        if any(word in text for word in keywords):
            return specialty
    return "General Medicine" if text.strip() else None


def ensure_patient_journey_schema() -> None:
    """Add non-destructive fields needed for the appointment journey."""
    with db_connect() as conn:
        conn.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS symptoms TEXT")
        conn.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS appointment_slot TEXT")
        conn.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS payment_status TEXT NOT NULL DEFAULT 'not_required'")
        conn.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS consultation_fee NUMERIC(10,2) NOT NULL DEFAULT 0")
        conn.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS razorpay_order_id TEXT")
        conn.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS razorpay_payment_id TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS patient_documents (
                id BIGSERIAL PRIMARY KEY,
                patient_id BIGINT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                appointment_id BIGINT REFERENCES appointments(id) ON DELETE SET NULL,
                file_name TEXT NOT NULL,
                content_type TEXT,
                file_data BYTEA NOT NULL,
                uploaded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)


def render_patient_dashboard(patient_id: int, name: str, phone: str) -> None:
    st.markdown("<div class='eyebrow'>TOP DOCS · PATIENT DASHBOARD</div><h1 style='color:#173b34'>Welcome, " + name.replace("<", "&lt;").replace(">", "&gt;") + "</h1><p style='color:#64756f'>Your appointments, payment status and medical documents — all in one place.</p>", unsafe_allow_html=True)
    payment_notice = st.session_state.pop("patient_payment_notice", None)
    if payment_notice:
        st.warning(payment_notice)
    a, b, c = st.columns(3)
    rows = fetch_rows(
        """SELECT a.id, d.name AS doctor, s.name AS specialty, a.appointment_date,
                  COALESCE(a.appointment_slot, 'Time to be confirmed') AS time_slot,
                  a.reason, a.status, COALESCE(a.payment_status, 'not_required') AS payment_status,
                  a.consultation_fee
           FROM appointments a JOIN doctors d ON d.id=a.doctor_id
           LEFT JOIN specialties s ON s.id=d.specialty_id
           WHERE a.patient_id=%s ORDER BY a.id DESC""", (patient_id,)
    )
    a.metric("Appointments", len(rows))
    b.metric("Upcoming", sum(
        1 for r in rows
        if str(r.get("status", "")).lower() in ("scheduled", "confirmed", "rescheduled")
        and str(r.get("payment_status", "")).lower() in ("paid", "not_required")
    ))
    c.metric("Paid bookings", sum(1 for r in rows if str(r.get("payment_status", "")).lower() == "paid"))
    st.markdown("### My appointments")
    top_refresh, _ = st.columns([1, 4])
    with top_refresh:
        if st.button("↻ Refresh", key=f"refresh_patient_appointments_{patient_id}", use_container_width=True):
            st.rerun()
    reschedule_notice = st.session_state.pop("patient_reschedule_notice", None)
    if reschedule_notice:
        st.success(reschedule_notice)
    if rows:
        for row in rows:
            status = str(row.get("status") or "pending").replace("_", " ").title()
            payment = str(row.get("payment_status") or "pending").replace("_", " ").title()
            with st.container(border=True):
                head_left, head_right = st.columns([3, 2])
                with head_left:
                    st.markdown(f"**Appointment #{row['id']} · {row.get('doctor') or 'Doctor to be confirmed'}**")
                    st.caption(f"{row.get('specialty') or 'Specialty not listed'} · {row.get('appointment_date') or 'Date to be confirmed'} · {row.get('time_slot') or 'Time to be confirmed'}")
                with head_right:
                    st.markdown(f"**Appointment:** {status}")
                    st.markdown(f"**Payment:** {payment}")
                st.write(row.get("reason") or "No additional concern shared.")
                fee = float(row.get("consultation_fee") or 0)
                st.caption(f"Consultation fee: ₹{fee:.0f}")
    else:
        st.info("No appointments yet. Start a booking to see it here.")

    pending_rows = [r for r in rows if str(r.get("payment_status", "")).lower() != "paid" and str(r.get("payment_status", "")).lower() != "not_required"]
    if pending_rows:
        st.warning("You have a saved appointment with payment pending. You can complete payment from the appointment booking flow; your saved details remain available here.")
        for pending in pending_rows:
            p1, p2 = st.columns([4, 2])
            with p1:
                st.caption(f"Appointment #{pending['id']} · ₹{float(pending.get('consultation_fee') or 0):.0f} · Status: Payment pending")
            with p2:
                if st.button("Continue payment", key=f"resume_payment_{pending['id']}", type="primary", use_container_width=True):
                    st.session_state["patient_journey_appointment_id"] = int(pending["id"])
                    st.session_state["patient_journey_patient_id"] = patient_id
                    st.session_state["patient_journey_name"] = name
                    st.session_state["patient_journey_phone"] = phone
                    st.session_state["patient_journey_doctor"] = pending.get("doctor") or ""
                    st.session_state["patient_journey_specialty"] = pending.get("specialty") or "General Medicine"
                    st.session_state["patient_journey_symptoms"] = pending.get("reason") or ""
                    st.session_state["patient_journey_fee"] = float(pending.get("consultation_fee") or 499)
                    st.session_state["patient_journey_date"] = pending.get("appointment_date") or date.today()
                    st.session_state["patient_journey_slot"] = pending.get("time_slot") or "Time to be confirmed"
                    st.session_state["patient_journey_payment_status"] = "pending"
                    st.session_state["patient_journey_step"] = 5
                    st.rerun()

    st.markdown("### Medical reports & documents")
    st.caption("Upload reports or other relevant documents for your consultation. Only files attached to your patient profile are shown here.")
    uploaded = st.file_uploader(
        "Upload a medical report (PDF, JPG, PNG, DOCX)",
        type=["pdf", "jpg", "jpeg", "png", "docx"],
        accept_multiple_files=False,
        key=f"patient_report_upload_{patient_id}",
    )
    related_options = {"No appointment selected": None}
    for r in rows:
        related_options[f"Appointment #{r['id']} · {r['appointment_date']} · {r['doctor']}"] = int(r["id"])
    selected_label = st.selectbox("Attach to appointment (optional)", list(related_options.keys()), key=f"patient_report_appt_{patient_id}")
    if uploaded is not None and st.button("Save document securely", type="primary", key=f"save_report_{patient_id}"):
        try:
            if uploaded.size > 10 * 1024 * 1024:
                st.error("File is too large. Please upload a file under 10 MB.")
            else:
                with db_connect() as conn:
                    conn.execute(
                        """INSERT INTO patient_documents(patient_id, appointment_id, file_name, content_type, file_data)
                           VALUES (%s,%s,%s,%s,%s)""",
                        (patient_id, related_options[selected_label], uploaded.name, uploaded.type, uploaded.getvalue()),
                    )
                st.success("Document saved to your patient profile.")
                st.rerun()
        except Exception as exc:
            st.error(f"Could not save document: {type(exc).__name__}. Please try again.")
    docs = fetch_rows(
        "SELECT id, appointment_id, file_name, content_type, uploaded_at FROM patient_documents WHERE patient_id=%s ORDER BY uploaded_at DESC",
        (patient_id,),
    )
    if docs:
        for doc in docs:
            d1, d2 = st.columns([4, 1])
            with d1:
                st.write(f"**{doc['file_name']}**")
                st.caption(f"Uploaded: {doc['uploaded_at']} · Appointment: {doc.get('appointment_id') or 'Not linked'}")
            with d2:
                with db_connect() as conn:
                    blob = conn.execute("SELECT file_data FROM patient_documents WHERE id=%s AND patient_id=%s", (doc["id"], patient_id)).fetchone()
                if blob:
                    st.download_button("Download", data=bytes(blob["file_data"]), file_name=doc["file_name"], mime=doc.get("content_type") or "application/octet-stream", key=f"download_doc_{doc['id']}")
    else:
        st.caption("No documents uploaded yet.")

    left, right = st.columns(2)
    with left:
        if st.button("Book another appointment", type="primary", use_container_width=True):
            st.session_state["patient_journey_step"] = 1
            st.session_state["patient_journey_patient_id"] = patient_id
            st.session_state["patient_journey_name"] = name
            st.session_state["patient_journey_phone"] = phone
            st.rerun()
    with right:
        if st.button("Start fresh booking", use_container_width=True):
            # Clear only the draft journey; preserve patient identity and saved database records.
            draft_keys = (
                "patient_journey_step", "patient_journey_symptoms",
                "patient_journey_symptom_categories", "patient_journey_specialty",
                "patient_journey_doctor", "patient_journey_date",
                "patient_journey_slot", "patient_journey_fee",
                "patient_journey_appointment_id", "patient_journey_payment_status",
            )
            for key in draft_keys:
                st.session_state.pop(key, None)
            st.session_state["patient_journey_step"] = 1
            st.session_state["patient_journey_patient_id"] = patient_id
            st.session_state["patient_journey_name"] = name
            st.session_state["patient_journey_phone"] = phone
            st.rerun()


def render_patient_portal() -> None:
    """Guided patient journey: details -> symptoms/specialty -> doctor -> slot -> booking/payment -> dashboard."""
    st.markdown("<div class='eyebrow'>TOP DOCS · PATIENT PORTAL</div><h1 style='color:#173b34'>Book your specialist appointment</h1><p style='color:#64756f'>Book a consultation in a few guided steps. Availability comes from the appointment records; payments use the configured Razorpay mode.</p>", unsafe_allow_html=True)

    # A returning-patient reminder appears when the portal is opened in a fresh session.
    # Name + phone lookup is only a demo convenience; OTP verification is needed for production.
    if not st.session_state.get("patient_return_prompt_seen", False):
        @st.dialog("Pick up where you left off")
        def _returning_patient_prompt():
            st.write("Your appointment details may already be saved. If payment is still pending, you can continue from your dashboard.")
            with st.form("returning_patient_popup_form"):
                popup_name = st.text_input("Full name used while booking")
                popup_phone = st.text_input("Phone number used while booking")
                c1, c2 = st.columns(2)
                with c1:
                    resume = st.form_submit_button("Find my appointment", type="primary", use_container_width=True)
                with c2:
                    start_new = st.form_submit_button("Start a new booking", use_container_width=True)
            if resume:
                try:
                    found_id = find_existing_patient_by_phone(popup_name, popup_phone)
                    if not found_id:
                        st.error("We couldn't find a profile with those details. Please check and try again.")
                    else:
                        st.session_state["patient_journey_patient_id"] = found_id
                        st.session_state["patient_journey_name"] = popup_name.strip()
                        st.session_state["patient_journey_phone"] = popup_phone.strip()
                        st.session_state["patient_journey_step"] = 6
                        st.session_state["patient_return_prompt_seen"] = True
                        st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
            if start_new:
                st.session_state["patient_return_prompt_seen"] = True
                st.rerun()
        _returning_patient_prompt()
        return

    # Carry the name and phone from the landing-page/session identity into a new booking.
    # Do not overwrite values already entered in the patient journey.
    if not str(st.session_state.get("patient_journey_name", "")).strip():
        for candidate in ("patient_name", "full_name", "user_name", "name", "logged_in_name", "auth_name", "current_user_name"):
            value = st.session_state.get(candidate)
            if isinstance(value, str) and value.strip():
                st.session_state["patient_journey_name"] = value.strip()
                break
        if not str(st.session_state.get("patient_journey_name", "")).strip():
            try:
                qp_name = st.query_params.get("name", "")
                if isinstance(qp_name, str) and qp_name.strip():
                    st.session_state["patient_journey_name"] = qp_name.strip()
            except Exception:
                pass
    if not str(st.session_state.get("patient_journey_phone", "")).strip():
        for candidate in ("patient_phone", "user_phone", "phone", "mobile", "mobile_number", "logged_in_phone", "auth_phone", "current_user_phone"):
            value = st.session_state.get(candidate)
            if isinstance(value, str) and value.strip():
                st.session_state["patient_journey_phone"] = value.strip()
                break
        if not str(st.session_state.get("patient_journey_phone", "")).strip():
            try:
                qp_phone = st.query_params.get("phone", "")
                if isinstance(qp_phone, str) and qp_phone.strip():
                    st.session_state["patient_journey_phone"] = qp_phone.strip()
            except Exception:
                pass

    # Journey state is stored only in this Streamlit session; final booking is persisted in PostgreSQL.
    defaults = {"patient_journey_step": 1, "patient_journey_name": "", "patient_journey_phone": "", "patient_journey_symptoms": "", "patient_journey_symptom_categories": [], "patient_journey_specialty": "Not sure — suggest a specialist", "patient_journey_doctor": "", "patient_journey_date": date.today() + timedelta(days=1), "patient_journey_slot": "10:00 AM", "patient_journey_fee": 499.0, "patient_journey_appointment_id": None, "patient_journey_patient_id": None, "patient_journey_payment_status": "pending"}
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

    step = int(st.session_state.get("patient_journey_step", 1))
    steps = ["Your details", "Health concern", "Choose doctor", "Pick a time", "Review & pay", "Your dashboard"]
    st.markdown("""
    <style>
    @keyframes journeyFadeUp { from {opacity:0; transform:translateY(12px)} to {opacity:1; transform:translateY(0)} }
    .journey-hero { animation:journeyFadeUp .55s ease-out both; padding:20px 22px; border-radius:18px; background:linear-gradient(135deg,#eaf5f0,#f7faf8); border:1px solid #d7e9e1; margin:4px 0 18px 0; }
    .journey-kicker { color:#46766a; font-size:12px; font-weight:700; letter-spacing:1.4px; text-transform:uppercase; }
    .journey-title { color:#173b34; font-size:25px; line-height:1.2; font-weight:750; margin-top:5px; }
    .journey-sub { color:#607d78; font-size:14px; margin-top:7px; }
    div[data-testid="stForm"], div[data-testid="stVerticalBlockBorderWrapper"] { animation:journeyFadeUp .45s ease-out both; }
    /* Explicit button foreground/background colors: prevent theme styles hiding labels */
    div[data-testid="stButton"] button[kind="primary"],
    div[data-testid="stFormSubmitButton"] button,
    button[kind="primary"] {
        background:#173b34 !important;
        color:#ffffff !important;
        -webkit-text-fill-color:#ffffff !important;
        border:1px solid #173b34 !important;
        opacity:1 !important;
    }
    div[data-testid="stButton"] button[kind="primary"] *,
    div[data-testid="stFormSubmitButton"] button *,
    button[kind="primary"] * {
        color:#ffffff !important;
        -webkit-text-fill-color:#ffffff !important;
        opacity:1 !important;
    }
    div[data-testid="stButton"] button[kind="secondary"],
    button[kind="secondary"],
    [data-testid="stBaseButton-secondary"] {
        background:#ffffff !important;
        color:#173b34 !important;
        -webkit-text-fill-color:#173b34 !important;
        border:1px solid #d8dfd8 !important;
        opacity:1 !important;
    }
    div.stButton > button, div.stFormSubmitButton > button { transition:transform .18s ease, box-shadow .18s ease; border-radius:12px; min-height:44px; }
    div.stButton > button:hover, div.stFormSubmitButton > button:hover { transform:translateY(-2px); box-shadow:0 7px 18px rgba(19,74,63,.12); }
    /* Premium polish only: preserve the existing palette and typography. */
    .journey-hero { position:relative; overflow:hidden; padding:26px 28px; border-radius:22px; box-shadow:0 12px 30px rgba(34,54,48,.07); }
    .journey-hero:after { content:""; position:absolute; width:170px; height:170px; right:-65px; top:-90px; border:1px solid rgba(29,89,75,.13); border-radius:50%; box-shadow:0 0 0 18px rgba(29,89,75,.025),0 0 0 38px rgba(29,89,75,.02); pointer-events:none; }
    .journey-kicker { display:inline-flex; align-items:center; gap:7px; padding:6px 10px; border-radius:999px; background:rgba(255,255,255,.7); border:1px solid #d7e9e1; }
    .journey-title { position:relative; z-index:1; letter-spacing:-.035em; }
    .journey-sub { max-width:760px; }
    div[data-testid="stProgress"] { margin:4px 0 22px; }
    div[data-testid="stProgress"] > div { height:9px; border-radius:999px; overflow:hidden; }
    div[data-testid="stProgress"] [role="progressbar"] { border-radius:999px; }
    div[data-testid="stForm"] { border:1px solid #e0e7e1; border-radius:18px; padding:22px 24px 18px; background:rgba(255,255,255,.78); box-shadow:0 10px 28px rgba(34,54,48,.045); }
    div[data-testid="stVerticalBlockBorderWrapper"] { border-radius:18px; }
    div[data-testid="stTextInput"] input, div[data-testid="stTextArea"] textarea, div[data-testid="stDateInput"] input, div[data-testid="stSelectbox"] div[role="combobox"] { border-radius:11px!important; }
    div[data-testid="stTextInput"] input:focus, div[data-testid="stTextArea"] textarea:focus, div[data-testid="stDateInput"] input:focus { box-shadow:0 0 0 2px rgba(29,89,75,.13)!important; }
    div[data-testid="stButton"] button, div[data-testid="stFormSubmitButton"] button { font-weight:650; letter-spacing:.005em; }
    div[data-testid="stButton"] button[kind="primary"], div[data-testid="stFormSubmitButton"] button[kind="primary"] { box-shadow:0 6px 15px rgba(23,59,52,.13); }
    div[data-testid="stButton"] button[kind="primary"]:hover, div[data-testid="stFormSubmitButton"] button[kind="primary"]:hover { box-shadow:0 9px 20px rgba(23,59,52,.19); }
    div[data-testid="stAlert"] { border-radius:13px; }
    div[data-testid="stExpander"] { border:1px solid #e0e7e1; border-radius:14px; overflow:hidden; }
    @media (max-width: 768px) { .journey-hero {padding:20px 18px;} .journey-title {font-size:23px;} div[data-testid="stForm"] {padding:17px 15px;} }
    @media (prefers-reduced-motion: reduce) { .journey-hero, div[data-testid="stForm"], div[data-testid="stVerticalBlockBorderWrapper"] {animation:none!important} }
    </style>
    """, unsafe_allow_html=True)
    hero_titles = {
        1: ("LET’S GET STARTED", "Your care, made simpler", "A few details to get your appointment started."),
        2: ("STEP 1 OF 5", "What brings you here?", "Share the key details so we can guide you to a suitable specialist."),
        3: ("STEP 2 OF 5", "Meet your care team", "Choose the doctor that feels right for your needs."),
        4: ("STEP 3 OF 5", "Find your time", "Choose a date and a convenient slot."),
        5: ("STEP 4 OF 5", "One last review", "Check your details before continuing to secure payment."),
        6: ("YOUR SPACE", "Your patient dashboard", "Appointments, payment status and medical documents in one place.")
    }
    kicker, hero_title, hero_sub = hero_titles[min(step, 6)]
    st.markdown(f'<div class="journey-hero"><div class="journey-kicker">{kicker}</div><div class="journey-title">{hero_title}</div><div class="journey-sub">{hero_sub}</div></div>', unsafe_allow_html=True)
    if step < 6:
        journey_labels = ["Details", "Concern", "Doctor", "Time", "Review & pay"]
        tracker_cols = st.columns(5)
        for idx, (col, label) in enumerate(zip(tracker_cols, journey_labels), start=1):
            if idx < step:
                marker, state_label = "✓", "Complete"
            elif idx == step:
                marker, state_label = str(idx), "In progress"
            else:
                marker, state_label = str(idx), "Upcoming"
            with col:
                st.markdown(
                    f"<div style='text-align:center;padding:10px 4px;border:1px solid "
                    f"{'#9fc7b7' if idx <= step else '#e0e7e1'};border-radius:13px;"
                    f"background:{'#edf6f1' if idx <= step else '#ffffff'}'>"
                    f"<div style='font-weight:800;color:#173b34;font-size:16px'>{marker}</div>"
                    f"<div style='font-size:12px;font-weight:700;color:#173b34'>{label}</div>"
                    f"<div style='font-size:10px;color:#64756f'>{state_label}</div></div>",
                    unsafe_allow_html=True,
                )
        st.progress(min(step, 5) / 5, text=f"Step {min(step, 5)} of 5 · Your progress is saved during this session")

    if step == 6:
        patient_id = st.session_state.get("patient_journey_patient_id")
        if patient_id:
            render_patient_dashboard(int(patient_id), st.session_state.get("patient_journey_name", "Patient"), st.session_state.get("patient_journey_phone", ""))
        else:
            st.warning("Patient session was not found. Enter your name and phone number to retrieve your appointments.")
        with st.expander("Returning patient? Find saved appointments"):
            with st.form("journey_returning_patient"):
                old_name = st.text_input("Full name used while booking")
                old_phone = st.text_input("Phone number used while booking")
                find = st.form_submit_button("Open my dashboard", type="primary")
            if find:
                try:
                    found_id = find_existing_patient_by_phone(old_name, old_phone)
                    if not found_id:
                        st.error("No patient profile found for those details. Check the name and phone number.")
                    else:
                        st.session_state["patient_journey_patient_id"] = found_id
                        st.session_state["patient_journey_name"] = old_name.strip()
                        st.session_state["patient_journey_phone"] = old_phone.strip()
                        st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
        return

    # Step 1: contact details
    if step == 1:
        with st.form("journey_patient_details"):
            name = st.text_input("What is your full name?", value=st.session_state["patient_journey_name"], placeholder="Enter your name")
            phone = st.text_input("What is your phone number?", value=st.session_state["patient_journey_phone"], placeholder="10-digit mobile number")
            next_step = st.form_submit_button("Continue", type="primary", use_container_width=True)
        if next_step:
            digits = re.sub(r"\D", "", phone)
            if not name.strip() or len(digits) < 10:
                st.warning("Enter your full name and a valid phone number with at least 10 digits.")
            else:
                st.session_state["patient_journey_name"] = name.strip()
                st.session_state["patient_journey_phone"] = phone.strip()
                st.session_state["patient_return_prompt_seen"] = True
                st.session_state["patient_journey_step"] = 2
                st.rerun()

    # Step 2: collect the problem first, then either use the patient's specialty choice or suggest one.
    elif step == 2:
        st.caption("Choose symptoms or describe your concern. We’ll suggest a department if needed.")
        with st.form("journey_symptoms_specialty"):
            symptom_categories = st.multiselect(
                "Symptoms (select all that apply)",
                ["Pain", "Fever", "Headache / dizziness", "Stomach / digestion issue", "Heart / breathing concern", "Periods / pregnancy concern", "Skin concern", "General check-up", "Other"],
                default=st.session_state.get("patient_journey_symptom_categories", []),
            )
            symptoms = st.text_area(
                "Tell us a little more (optional)",
                value=st.session_state["patient_journey_symptoms"],
                placeholder="What are you experiencing, and when did it start?",
                height=120,
            )
            specialty_options = ["Not sure — suggest a specialist"] + specialties()
            current_specialty = st.session_state.get("patient_journey_specialty", specialty_options[0])
            if current_specialty not in specialty_options:
                current_specialty = specialty_options[0]
            specialty = st.selectbox(
                "Preferred specialist",
                specialty_options,
                index=specialty_options.index(current_specialty),
            )
            back, _, proceed = st.columns([1, 2, 2])
            with back:
                go_back = st.form_submit_button("Back")
            with proceed:
                next_step = st.form_submit_button("Find matching doctors", type="primary", use_container_width=True)
        if go_back:
            st.session_state["patient_journey_step"] = 1
            st.rerun()
        if next_step:
            combined_symptoms = ", ".join(symptom_categories + ([symptoms.strip()] if symptoms.strip() else []))
            if not combined_symptoms.strip():
                st.warning("Choose at least one symptom category or describe your problem before continuing.")
            else:
                suggested = infer_specialty_from_symptoms(combined_symptoms)
                chosen = suggested if specialty == "Not sure — suggest a specialist" else specialty
                st.session_state["patient_journey_symptom_categories"] = symptom_categories
                st.session_state["patient_journey_symptoms"] = combined_symptoms
                st.session_state["patient_journey_specialty"] = chosen or "General Medicine"
                st.session_state["patient_journey_step"] = 3
                st.rerun()
        if st.session_state.get("patient_journey_symptoms"):
            suggestion = infer_specialty_from_symptoms(st.session_state["patient_journey_symptoms"])
            if suggestion:
                st.caption(f"Suggested department: {suggestion}. This is an illustrative routing suggestion, not a diagnosis. Seek urgent care for severe or emergency symptoms.")

    # Step 3: doctor list based on specialty
    elif step == 3:
        specialty = st.session_state.get("patient_journey_specialty", "General Medicine")
        doctor_choices = [d for d in DOCTORS if d["specialty"] == specialty]
        if not doctor_choices:
            doctor_choices = [d for d in DOCTORS if d["specialty"] == "General Medicine"] or DOCTORS
        st.markdown(f"### Recommended for {specialty}")
        for d in doctor_choices:
            st.markdown(f"**{d['name']}** · {d['specialty']} · {d['mode']} · {d['city']}")
        with st.form("journey_choose_doctor"):
            doctor_names = [d["name"] for d in doctor_choices]
            selected_doctor = st.selectbox("Choose your doctor", doctor_names, index=0)
            back, _, proceed = st.columns([1, 2, 2])
            with back: go_back = st.form_submit_button("Back")
            with proceed: next_step = st.form_submit_button("Choose time", type="primary", use_container_width=True)
        if go_back:
            st.session_state["patient_journey_step"] = 2
            st.rerun()
        if next_step:
            st.session_state["patient_journey_doctor"] = selected_doctor
            st.session_state["patient_journey_step"] = 4
            st.rerun()

    # Step 4: show slots based on the shared database for this doctor and date.
    elif step == 4:
        doctor_name = st.session_state.get("patient_journey_doctor", "")
        st.markdown(f"### Choose a time with {doctor_name or 'your doctor'}")
        appt_date = st.date_input(
            "Appointment date",
            min_value=date.today(),
            value=max(date.today(), st.session_state.get("patient_journey_date", date.today()+timedelta(days=1))),
            key="journey_live_slot_date",
        )
        try:
            slots = get_available_slots(doctor_name, appt_date)
        except Exception as exc:
            slots = []
            st.error(f"Could not refresh doctor availability ({type(exc).__name__}).")
        if not slots:
            st.warning("No slots are currently available for this doctor on that date. Choose another date.")
        else:
            previous_slot = st.session_state.get("patient_journey_slot")
            default_index = slots.index(previous_slot) if previous_slot in slots else 0
            with st.form("journey_choose_slot"):
                slot = st.radio("Available times", slots, horizontal=True, index=default_index)
                back, _, proceed = st.columns([1, 2, 2])
                with back: go_back = st.form_submit_button("Back")
                with proceed: next_step = st.form_submit_button("Continue to confirmation", type="primary", use_container_width=True)
            if go_back:
                st.session_state["patient_journey_step"] = 3
                st.rerun()
            if next_step:
                st.session_state["patient_journey_date"] = appt_date
                st.session_state["patient_journey_slot"] = slot
                st.session_state["patient_journey_step"] = 5
                st.rerun()

    # Step 5: create appointment once, then demo payment action
    elif step == 5:
        if not st.session_state.get("patient_journey_appointment_id"):
            st.markdown("### Review your appointment")
            st.info("Please verify the doctor, date and time. Your request is saved first; the final confirmation depends on the payment status shown on your dashboard.")
            st.write(f"**Patient:** {st.session_state['patient_journey_name']}")
            st.write(f"**Phone:** {st.session_state['patient_journey_phone']}")
            st.write(f"**Symptoms / reason:** {st.session_state['patient_journey_symptoms']}")
            st.write(f"**Specialist:** {st.session_state['patient_journey_specialty']}")
            st.write(f"**Doctor:** {st.session_state['patient_journey_doctor']}")
            st.write(f"**Date:** {st.session_state['patient_journey_date']} · **Time:** {st.session_state['patient_journey_slot']}")
            st.write(f"**Consultation fee: ₹{st.session_state['patient_journey_fee']:.0f}")
            left, _, right = st.columns([1, 2, 2])
            with left:
                if st.button("Back", key="journey_back_review"):
                    st.session_state["patient_journey_step"] = 4
                    st.rerun()
            with right:
                if st.button("Confirm appointment", type="primary", use_container_width=True):
                    try:
                        patient_id = get_or_create_patient_by_phone(st.session_state["patient_journey_name"], st.session_state["patient_journey_phone"])
                        doctor_id = get_doctor_id(st.session_state["patient_journey_doctor"])
                        selected_date = st.session_state["patient_journey_date"]
                        selected_slot = st.session_state["patient_journey_slot"]
                        with db_connect() as conn:
                            # Give a clear message if this doctor/time is already booked.
                            occupied = conn.execute(
                                """SELECT id FROM appointments
                                   WHERE doctor_id=%s AND appointment_date=%s AND appointment_slot=%s
                                     AND LOWER(COALESCE(status,'')) NOT IN ('cancelled','canceled')
                                   LIMIT 1""",
                                (doctor_id, selected_date, selected_slot),
                            ).fetchone()
                            if occupied:
                                st.warning("That time slot has just been booked. Please go back and choose another available time.")
                                st.session_state["patient_journey_step"] = 4
                                st.stop()
                            row = conn.execute(
                                """INSERT INTO appointments(patient_id,doctor_id,appointment_date,reason,status,created_at,symptoms,appointment_slot,payment_status,consultation_fee)
                                   VALUES (%s,%s,%s,%s,'pending_payment',NOW(),%s,%s,'pending',%s) RETURNING id""",
                                (patient_id, doctor_id, selected_date, st.session_state["patient_journey_symptoms"], st.session_state["patient_journey_symptoms"], selected_slot, st.session_state["patient_journey_fee"]),
                            ).fetchone()
                        st.session_state["patient_journey_patient_id"] = patient_id
                        st.session_state["patient_journey_appointment_id"] = int(row["id"])
                        st.session_state["patient_journey_payment_status"] = "pending"
                        st.rerun()
                    except ValueError as exc:
                        st.error(f"Could not save booking: {exc}")
                    except UniqueViolation:
                        st.warning("This appointment conflicts with an existing booking. No duplicate booking was created. Please choose another time slot.")
                        st.session_state["patient_journey_step"] = 4
                    except Exception as exc:
                        st.error(f"Could not save booking ({type(exc).__name__}). Please check the terminal logs for the detailed database error.")
        else:
            appointment_id = int(st.session_state["patient_journey_appointment_id"])
            st.success(f"Appointment #{appointment_id} saved · Payment pending")
            st.caption("Your booking details are saved. You can return to your dashboard now and continue payment later.")
            back_col, _ = st.columns([1, 2])
            with back_col:
                if st.button("Return to patient dashboard", key=f"return_dashboard_pending_{appointment_id}", use_container_width=True):
                    st.session_state["patient_journey_step"] = 6
                    st.rerun()
            st.markdown(f"### Pay ₹{st.session_state['patient_journey_fee']:.0f}")
            if not RAZORPAY_KEY_ID or not RAZORPAY_KEY_SECRET:
                st.warning("Razorpay keys are not configured. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to .env, then restart Streamlit.")
            elif razorpay is None:
                st.error("Razorpay SDK is missing. Run: pip install razorpay")
            else:
                client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

                # Handle the Checkout callback only after verifying the signature on the server.
                qp = st.query_params
                callback_payment_id = qp.get("razorpay_payment_id")
                callback_order_id = qp.get("razorpay_order_id")
                callback_signature = qp.get("razorpay_signature")
                callback_error = qp.get("razorpay_error")
                if callback_error:
                    # Keep the patient in their dashboard after a failed/cancelled checkout.
                    st.session_state["patient_payment_notice"] = (
                        "Payment was not completed. Your appointment is still saved as pending. "
                        "You can retry payment anytime from your patient dashboard."
                    )
                    st.session_state["patient_journey_step"] = 6
                    for key in ("razorpay_error", "razorpay_payment_id", "razorpay_order_id", "razorpay_signature"):
                        if key in st.query_params:
                            del st.query_params[key]
                    st.rerun()
                elif callback_payment_id and callback_order_id and callback_signature:
                    try:
                        client.utility.verify_payment_signature({
                            "razorpay_order_id": str(callback_order_id),
                            "razorpay_payment_id": str(callback_payment_id),
                            "razorpay_signature": str(callback_signature),
                        })
                        with db_connect() as conn:
                            saved = conn.execute(
                                """SELECT id FROM appointments
                                   WHERE id=%s AND patient_id=%s AND razorpay_order_id=%s
                                   LIMIT 1""",
                                (appointment_id, st.session_state["patient_journey_patient_id"], str(callback_order_id)),
                            ).fetchone()
                            if not saved:
                                raise ValueError("Payment order does not match this appointment.")
                            conn.execute(
                                """UPDATE appointments
                                   SET payment_status='paid', status='scheduled', razorpay_payment_id=%s
                                   WHERE id=%s AND patient_id=%s AND razorpay_order_id=%s
                                     AND payment_status <> 'paid'""",
                                (str(callback_payment_id), appointment_id,
                                 st.session_state["patient_journey_patient_id"], str(callback_order_id)),
                            )
                        st.session_state["patient_journey_payment_status"] = "paid"
                        st.session_state["patient_journey_step"] = 6
                        st.query_params.clear()
                        st.rerun()
                    except Exception:
                        st.error("Payment verification failed. Appointment has not been marked as paid. Please contact support if your payment was deducted.")
                        for key in ("razorpay_payment_id", "razorpay_order_id", "razorpay_signature"):
                            if key in st.query_params:
                                del st.query_params[key]

                with db_connect() as conn:
                    saved_order = conn.execute(
                        "SELECT razorpay_order_id, payment_status FROM appointments WHERE id=%s AND patient_id=%s",
                        (appointment_id, st.session_state["patient_journey_patient_id"]),
                    ).fetchone()

                if saved_order and saved_order.get("payment_status") == "paid":
                    st.success("Payment verified. Your appointment is confirmed.")
                    if st.button("Open dashboard", type="primary", use_container_width=True):
                        st.session_state["patient_journey_step"] = 6
                        st.rerun()
                else:
                    if st.button("Pay securely with Razorpay", type="primary", use_container_width=True):
                        try:
                            # Reuse an existing pending order to avoid creating duplicates on reruns.
                            order_id = saved_order.get("razorpay_order_id") if saved_order else None
                            if not order_id:
                                amount_paise = int(round(float(st.session_state["patient_journey_fee"]) * 100))
                                order = client.order.create(data={
                                    "amount": amount_paise,
                                    "currency": "INR",
                                    "receipt": f"appt_{appointment_id}",
                                    "notes": {"appointment_id": str(appointment_id)},
                                })
                                order_id = order["id"]
                                with db_connect() as conn:
                                    conn.execute(
                                        "UPDATE appointments SET razorpay_order_id=%s, payment_status='pending' WHERE id=%s AND patient_id=%s",
                                        (order_id, appointment_id, st.session_state["patient_journey_patient_id"]),
                                    )
                            callback_url = st.get_option("server.baseUrlPath")
                            # Streamlit is served from the current URL; preserve patient portal routing.
                            current_url = ""
                            try:
                                current_url = st.context.url
                            except Exception:
                                pass
                            if not current_url:
                                current_url = "http://localhost:8501/?patient=1"
                            from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
                            parts = urlsplit(current_url)
                            query = dict(parse_qsl(parts.query, keep_blank_values=True))
                            query["patient"] = "1"
                            callback_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
                            checkout_html = f"""
                            <div style="font-family:Arial,sans-serif;color:#173b34;padding:12px 0;box-sizing:border-box;width:100%;min-height:620px;overflow:visible">
                              <p>Razorpay Test Mode checkout · ₹{float(st.session_state['patient_journey_fee']):.0f}</p>
                              <p style="font-size:14px;color:#607d78">Select “Open Razorpay Checkout” below. If the secure checkout is clipped, use the browser’s open-in-new-tab option or widen the browser window.</p>
                              <button id="rzp-pay" style="background:#173b34;color:white;border:0;border-radius:10px;padding:12px 18px;font-weight:bold;cursor:pointer">Open Razorpay Checkout</button>
                            </div>
                            <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
                            <script>
                            document.getElementById('rzp-pay').onclick = function(e) {{
                              var options = {{
                                key: {json.dumps(RAZORPAY_KEY_ID)},
                                amount: {int(round(float(st.session_state['patient_journey_fee']) * 100))},
                                currency: "INR",
                                name: "MediAgent AI",
                                description: "Consultation fee · Appointment #{appointment_id}",
                                order_id: {json.dumps(order_id)},
                                callback_url: {json.dumps(callback_url)},
                                redirect: true,
                                prefill: {{name: {json.dumps(st.session_state['patient_journey_name'])}}},
                                notes: {{appointment_id: {json.dumps(str(appointment_id))}}},
                                theme: {{color: "#173b34"}}
                              }};
                              var rzp = new Razorpay(options);
                              rzp.on('payment.failed', function() {{
                                window.location.href = {json.dumps(callback_url + ('&' if '?' in callback_url else '?') + 'razorpay_error=1')};
                              }});
                              rzp.open();
                              e.preventDefault();
                            }};
                            </script>
                            """
                            components.html(checkout_html, height=650, scrolling=True)
                            st.info("Checkout button is shown above. Use Razorpay Test Mode payment details only.")
                        except Exception as exc:
                            st.error(f"Could not start Razorpay checkout: {type(exc).__name__}. Check Test Mode keys and connection.")

    st.caption("Privacy note: name + phone is convenient for this demo but is not strong identity verification. Add OTP verification before using real patient information. Doctor slots are based on the demo schedule. Use test-mode payment credentials for demonstrations; do not enter real patient data.")


def render_floating_mediagent() -> None:
    """Compact help widget for patients throughout the appointment journey."""
    st.markdown(
        """
        <style>
        /* Keep the MediAgent launcher visible while the patient scrolls the journey. */
        div[data-testid="stPopover"] {
            position: fixed !important;
            right: 24px !important;
            bottom: 22px !important;
            z-index: 99999 !important;
            width: auto !important;
        }
        div[data-testid="stPopover"] > button {
            border-radius: 999px !important;
            min-height: 52px !important;
            padding: 0 18px !important;
            background: #173b34 !important;
            color: #ffffff !important;
            border: 2px solid #f8f6f0 !important;
            box-shadow: 0 12px 32px rgba(23,59,52,.28) !important;
            font-weight: 800 !important;
        }
        @media(max-width:700px) {
            div[data-testid="stPopover"] { right: 12px !important; bottom: 12px !important; }
            div[data-testid="stPopover"] > button { min-height: 48px !important; padding: 0 14px !important; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "mediagent_help_messages" not in st.session_state:
        st.session_state["mediagent_help_messages"] = [{
            "role": "assistant",
            "content": "Hi! I’m MediAgent. I can explain booking steps, share general symptom information, or help you understand which specialist may be relevant. I can’t diagnose or prescribe.",
        }]

    with st.popover("✦ Need help? MediAgent", use_container_width=False):
        st.markdown("#### MediAgent AI")
        st.caption("Ask about doctors, available slots, rescheduling, or booking steps.")

        suggestions = [
            "What doctor slots are available?",
            "What if my preferred slot is unavailable?",
            "Can I reschedule my appointment?",
            "What should I prepare before my consultation?",
        ]
        cols = st.columns(2)
        selected_question = None
        for i, question in enumerate(suggestions):
            if cols[i % 2].button(question, key=f"mediagent_suggest_{i}", use_container_width=True):
                selected_question = question

        for message in st.session_state["mediagent_help_messages"][-6:]:
            with st.chat_message(message["role"]):
                st.write(message["content"])

        # Deterministic live availability picker: never rely on the LLM to invent slots.
        if st.session_state.get("mediagent_show_live_slots"):
            st.markdown("### Live doctor availability")
            doctor_rows = fetch_rows(
                """SELECT d.name AS doctor, COALESCE(sp.name, 'General Medicine') AS specialty
                   FROM doctors d LEFT JOIN specialties sp ON sp.id=d.specialty_id
                   ORDER BY sp.name, d.name"""
            )
            if doctor_rows:
                doctor_labels = {
                    f"{r['doctor']} · {r['specialty']}": (r["doctor"], r["specialty"])
                    for r in doctor_rows
                }
                chosen_label = st.selectbox(
                    "Choose a doctor", list(doctor_labels.keys()),
                    key="mediagent_live_doctor",
                )
                live_date = st.date_input(
                    "Choose a date", min_value=date.today(),
                    value=max(date.today(), st.session_state.get("mediagent_live_date", date.today()+timedelta(days=1))),
                    key="mediagent_live_date_picker",
                )
                doctor_name, specialty_name = doctor_labels[chosen_label]
                try:
                    live_slots = get_available_slots(doctor_name, live_date)
                except Exception as exc:
                    live_slots = []
                    st.error(f"Could not read live availability ({type(exc).__name__}).")
                if live_slots:
                    st.caption(f"Available times for {doctor_name} · {live_date.strftime('%d %b %Y')}")
                    chosen_slot = st.radio(
                        "Available slots (already-booked times are hidden)",
                        live_slots, key=f"mediagent_live_slot_{doctor_name}_{live_date}",
                    )
                    if st.button("Use this slot in my booking", type="primary", use_container_width=True, key="mediagent_use_live_slot"):
                        st.session_state["patient_journey_doctor"] = doctor_name
                        st.session_state["patient_journey_doctor_name"] = doctor_name
                        st.session_state["patient_journey_specialty"] = specialty_name
                        st.session_state["patient_journey_date"] = live_date
                        st.session_state["patient_journey_slot"] = chosen_slot
                        st.session_state["patient_journey_step"] = 4
                        st.session_state["patient_return_prompt_seen"] = True
                        st.session_state["mediagent_show_live_slots"] = False
                        st.query_params["patient"] = "1"
                        st.rerun()
                else:
                    st.info("No free slots for this doctor on this date. Choose another doctor or date.")
            else:
                st.info("No doctors are currently listed in the database.")

        with st.form("mediagent_floating_help_form", clear_on_submit=True):
            typed_prompt = st.text_input(
                "Ask a question",
                placeholder="Ask about slots, doctors, or booking…",
                label_visibility="collapsed",
            )
            send = st.form_submit_button("Send", type="primary", use_container_width=True)

        prompt = selected_question or (typed_prompt.strip() if send else "")
        if prompt:
            st.session_state["mediagent_help_messages"].append({"role": "user", "content": prompt})
            normalized_prompt = prompt.lower()
            slot_request = any(term in normalized_prompt for term in (
                "slot", "slots", "available time", "availability", "available doctor", "show me the time"
            ))
            if slot_request:
                st.session_state["mediagent_show_live_slots"] = True
                st.session_state["mediagent_help_messages"].append({
                    "role": "assistant",
                    "content": "I’ll check the database for the selected doctor and date. Already-booked slots will be hidden. Choose a doctor and date below to see the remaining available times."
                })
                st.rerun()
            journey_context = {
                "current_step": st.session_state.get("patient_journey_step", 1),
                "selected_specialty": st.session_state.get("patient_journey_specialty", "not selected"),
                "selected_doctor": st.session_state.get("patient_journey_doctor_name", "not selected"),
                "selected_date": str(st.session_state.get("patient_journey_date", "not selected")),
                "selected_slot": st.session_state.get("patient_journey_slot", "not selected"),
            }
            contextual_prompt = (
                "You are MediAgent, a helpful patient appointment booking assistant. "
                "Answer in simple, friendly language. Help with doctor availability, choosing another slot, "
                "rescheduling/cancellation, consultation preparation, and the booking flow. "
                "Use this current journey context when relevant: " + json.dumps(journey_context, default=str) + ". "
                "Do not invent live doctor availability. Slots in this demo may be illustrative; tell the patient "
                "to check the slots shown in the booking UI for confirmed choices. If a requested slot is unavailable, "
                "suggest another displayed slot/date or another doctor; do not claim a booking changed unless confirmed. "
                "Do not diagnose or prescribe medication. For emergency symptoms, advise urgent medical care.\n\n"
                f"Patient question: {prompt}"
            )
            try:
                # Answer directly in the patient-facing chat. Do not expose internal
                # Supervisor/agent-routing status messages to the patient.
                answer = llm_chat(
                    system_prompt=(
                        "You are MediAgent, the patient-facing appointment assistant inside the booking journey. "
                        "Always answer the patient's question directly in friendly, simple language. "
                        "NEVER mention internal agents, supervisor routing, tools, panels, workflows, or system architecture. "
                        "For unavailable slots, explain that they can select another slot/date shown on screen or choose another doctor. "
                        "For availability questions, only report slots explicitly present in the supplied journey context; "
                        "if no live slot list is supplied, say you cannot confirm live availability here and guide them to the slots displayed. "
                        "Do not invent doctors, dates, times, bookings, or confirmations. "
                        "Answer general booking questions helpfully, and ask one short clarifying question only when needed. "
                        "Do not diagnose, prescribe, or recommend medication. For emergency symptoms, advise urgent medical care."
                    ),
                    user_prompt=(
                        "Current booking context: " + json.dumps(journey_context, default=str) +
                        "\\nPatient question: " + prompt
                    ),
                    fallback=(
                        "I’m unable to connect to the assistant right now. Please check the available slots shown on this page. "
                        "If your preferred time is unavailable, choose another displayed time/date or select another doctor."
                    ),
                    temperature=0.3,
                )
            except Exception:
                answer = (
                    "I’m unable to connect to the assistant right now. Please check the available slots shown on this page. "
                    "If your preferred time is unavailable, choose another displayed time/date or select another doctor."
                )
            st.session_state["mediagent_help_messages"].append({"role": "assistant", "content": answer})
            st.rerun()

        st.caption(
            "General information only. For severe or emergency symptoms, seek urgent medical care."
        )


def get_or_create_patient(full_name: str) -> int:
    """Resolve a patient through users -> patients in the migration schema."""
    name = full_name.strip()
    if not name:
        raise ValueError("Patient name is required.")
    signed_in = current_user()
    if signed_in and signed_in.get("role") == "patient":
        if name.casefold() != str(signed_in.get("name", "")).casefold():
            raise ValueError("You can only create records for your own signed-in account.")
        patient_id = current_patient_id()
        if patient_id is None:
            raise ValueError("Patient account is not available.")
        return patient_id

    with db_connect() as conn:
        user = conn.execute(
            """
            SELECT id FROM users
            WHERE LOWER(name) = LOWER(%s)
            ORDER BY id
            LIMIT 1
            """,
            (name,),
        ).fetchone()

        if user:
            user_id = user["id"]
        else:
            email = f"{name.lower().replace(' ', '.')}@mediagent.local"
            user = conn.execute(
                """
                INSERT INTO users(name, email)
                VALUES (%s, %s)
                ON CONFLICT (email) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (name, email),
            ).fetchone()
            user_id = user["id"]

        patient = conn.execute(
            "SELECT id FROM patients WHERE user_id = %s LIMIT 1",
            (user_id,),
        ).fetchone()

        if patient:
            return int(patient["id"])

        patient = conn.execute(
            "INSERT INTO patients(user_id) VALUES (%s) RETURNING id",
            (user_id,),
        ).fetchone()
        return int(patient["id"])


def get_doctor_id(doctor_name: str) -> int:
    with db_connect() as conn:
        row = conn.execute(
            "SELECT id FROM doctors WHERE name = %s",
            (doctor_name,),
        ).fetchone()
        if not row:
            raise ValueError(
                f"Doctor '{doctor_name}' is not available in the demo directory."
            )
        return int(row["id"])


def get_available_slots(doctor_name: str, appointment_date: date, exclude_appointment_id: int | None = None) -> list[str]:
    """Return demo slot options that are not occupied in the shared appointments table."""
    candidate_slots = ["09:30 AM", "10:00 AM", "11:00 AM", "11:30 AM", "02:00 PM", "04:30 PM", "06:00 PM"]
    doctor_id = get_doctor_id(doctor_name)
    sql = """
        SELECT appointment_slot
        FROM appointments
        WHERE doctor_id=%s AND appointment_date=%s
          AND appointment_slot IS NOT NULL
          AND LOWER(COALESCE(status,'')) NOT IN ('cancelled','canceled','completed')
    """
    params: list[object] = [doctor_id, appointment_date]
    if exclude_appointment_id is not None:
        sql += " AND id <> %s"
        params.append(int(exclude_appointment_id))
    with db_connect() as conn:
        rows = conn.execute(sql, tuple(params)).fetchall()
    booked = {str(r["appointment_slot"]).strip() for r in rows}
    available = [slot for slot in candidate_slots if slot not in booked]

    # A same-day appointment cannot be booked for a time that has already passed.
    if appointment_date == date.today():
        now = datetime.now().time()
        future_slots = []
        for slot in available:
            try:
                slot_time = datetime.strptime(slot, "%I:%M %p").time()
            except ValueError:
                continue
            if slot_time > now:
                future_slots.append(slot)
        available = future_slots

    return available


def insert_interaction(
    task: str,
    agent: str,
    user_input: str,
    response: str,
    patient_id: Optional[int] = None,
) -> None:
    with db_connect() as conn:
        conn.execute(
            """
            INSERT INTO interactions(
                patient_id, task, agent, user_input, response, created_at
            )
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (
                patient_id,
                task,
                agent,
                user_input[:5000],
                response[:10000],
            ),
        )


def get_scalar(query: str, params: Tuple[Any, ...] = ()) -> int:
    with db_connect() as conn:
        row = conn.execute(query, params).fetchone()
        if not row:
            return 0
        value = next(iter(row.values()))
        return int(value or 0)


def fetch_rows(
    query: str,
    params: Tuple[Any, ...] = (),
) -> List[Dict[str, Any]]:
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


seed_demo_doctors()

ensure_auth_schema()
ensure_patient_journey_schema()





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
        except requests.exceptions.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "unknown"
            if status in (401, 403):
                return False, "Groq API key invalid or unauthorized · check GROQ_API_KEY in .env"
            return False, f"Groq API returned HTTP {status}"
        except requests.exceptions.RequestException:
            return False, "Groq unavailable · check internet connection / API endpoint"

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

    except requests.exceptions.HTTPError as exc:
        status = exc.response.status_code if exc.response is not None else "unknown"
        if LLM_PROVIDER == "groq" and status in (401, 403):
            message = "Groq API key is invalid or unauthorized. Check GROQ_API_KEY in your .env file."
        elif LLM_PROVIDER == "groq" and status == 404:
            message = f"Groq model or endpoint not found (HTTP {status}). Check GROQ_MODEL and GROQ_BASE_URL."
        elif LLM_PROVIDER == "groq" and status == 429:
            message = "Groq rate limit or quota reached. Check your Groq account limits."
        else:
            message = f"{'Groq' if LLM_PROVIDER == 'groq' else 'Ollama'} returned HTTP {status}."
        return f"{fallback}\n\n_AI service error: {message} The fallback response is shown._"
    except requests.exceptions.ConnectionError:
        provider = "Groq" if LLM_PROVIDER == "groq" else "Ollama"
        return f"{fallback}\n\n_{provider} connection failed. The fallback response is shown._"
    except requests.exceptions.Timeout:
        return fallback + "\n\n_AI service timed out. The fallback response is shown._"
    except requests.exceptions.RequestException:
        provider = "Groq" if LLM_PROVIDER == "groq" else "Ollama"
        return f"{fallback}\n\n_{provider} request failed. The fallback response is shown._"


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
        safe_footer = (
            "\n\n**Safety note:** This is general information, not a diagnosis or prescription. "
            "For personal medical decisions, consult a qualified healthcare professional."
        )
        if status == "NEEDS_REVISION":
            cleaned = text + safe_footer
            return cleaned, status, issues
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

    def book(
        self,
        patient: str,
        doctor: str,
        appointment_date: date,
        reason: str,
    ) -> int:
        patient_id = get_or_create_patient(patient)
        doctor_id = get_doctor_id(doctor)

        try:
            with db_connect() as conn:
                row = conn.execute(
                    """
                    INSERT INTO appointments(
                        patient_id, doctor_id, appointment_date, reason, status, created_at
                    )
                    VALUES (%s, %s, %s, %s, 'scheduled', NOW())
                    RETURNING id
                    """,
                    (
                        patient_id,
                        doctor_id,
                        appointment_date,
                        reason,
                    ),
                ).fetchone()
                return int(row["id"])
        except UniqueViolation as exc:
            raise ValueError(
                f"{doctor} already has an active appointment on "
                f"{appointment_date.isoformat()}. Please choose another date."
            ) from exc

    def reschedule(self, appointment_id: int, new_date: date, new_slot: Optional[str] = None) -> bool:
        """Reschedule in-place: update the selected appointment row, never INSERT a new booking."""
        try:
            with db_connect() as conn:
                # Check the chosen slot against other active bookings, excluding this appointment.
                if new_slot:
                    occupied = conn.execute(
                        """
                        SELECT id FROM appointments
                        WHERE doctor_id = (SELECT doctor_id FROM appointments WHERE id = %s)
                          AND appointment_date = %s
                          AND appointment_slot = %s
                          AND id <> %s
                          AND LOWER(COALESCE(status, '')) NOT IN ('cancelled', 'canceled', 'completed')
                        LIMIT 1
                        """,
                        (appointment_id, new_date, new_slot, appointment_id),
                    ).fetchone()
                    if occupied:
                        raise ValueError("That slot is already booked. Please choose another available time.")

                    cur = conn.execute(
                        """
                        UPDATE appointments
                        SET appointment_date = %s,
                            appointment_slot = %s,
                            status = 'rescheduled'
                        WHERE id = %s
                          AND LOWER(COALESCE(status, '')) NOT IN ('cancelled', 'canceled', 'completed')
                        RETURNING id
                        """,
                        (new_date, new_slot, appointment_id),
                    )
                else:
                    cur = conn.execute(
                        """
                        UPDATE appointments
                        SET appointment_date = %s,
                            status = 'rescheduled'
                        WHERE id = %s
                          AND LOWER(COALESCE(status, '')) NOT IN ('cancelled', 'canceled', 'completed')
                        RETURNING id
                        """,
                        (new_date, appointment_id),
                    )
                return cur.fetchone() is not None
        except UniqueViolation as exc:
            raise ValueError(
                f"The doctor already has an active appointment on {new_date.isoformat()}."
            ) from exc

    def cancel(self, appointment_id: int) -> bool:
        with db_connect() as conn:
            cur = conn.execute(
                """
                UPDATE appointments
                SET status = 'cancelled'
                WHERE id = %s
                """,
                (appointment_id,),
            )
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

    def run(
        self,
        report_text: str,
        title: str = "Medical Report",
        patient_name: str = "Demo Patient",
    ) -> AgentResult:
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

        patient_id = get_or_create_patient(patient_name)

        with db_connect() as conn:
            row = conn.execute(
                """
                INSERT INTO medical_reports(
                    patient_id, title, report_text, summary, created_at
                )
                VALUES (%s, %s, %s, %s, NOW())
                RETURNING id
                """,
                (
                    patient_id,
                    title[:200],
                    report_text[:20000],
                    response[:15000],
                ),
            ).fetchone()
            report_id = int(row["id"])

        return AgentResult(
            task="Medical report summarization",
            agent=self.name,
            response=response,
            page="Medical Reports",
            data={
                "report_id": report_id,
                "title": title,
                "patient_id": patient_id,
            },
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
            return "high"
        if any(x in q for x in medium):
            return "normal"
        return "low"

    def create_ticket(self, patient: str, issue: str) -> Tuple[int, str]:
        priority = self.priority(issue)
        patient_id = get_or_create_patient(patient)

        with db_connect() as conn:
            row = conn.execute(
                """
                INSERT INTO support_tickets(
                    patient_id, issue, priority, status, created_at
                )
                VALUES (%s, %s, %s, 'open', NOW())
                RETURNING id
                """,
                (patient_id, issue, priority),
            ).fetchone()
            return int(row["id"]), priority

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

        if any(x in q for x in [
            "follow up", "follow-up", "next step", "after my appointment",
            "after visit", "what should i ask", "what should i monitor",
        ]):
            return "followup"

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
    st.query_params.clear()
    st.rerun()

try:
    admin_mode = st.query_params.get("admin") == "1"
    patient_mode = st.query_params.get("patient") == "1"
except Exception:
    admin_mode = False
    patient_mode = False

if admin_mode:
    st.session_state["nav"] = "Admin Panel"
elif patient_mode:
    st.session_state["nav"] = "Patient Portal"

nav = st.session_state.get("nav", "Top Docs Home")

# Admin has a separate URL and admin-only login. Patient Portal is public and uses name + phone.
if admin_mode and not (current_user() and current_user().get("role") == "admin"):
    auth_screen(admin_only=True)
    st.stop()
if nav not in ("Top Docs Home", "Patient Portal") and not current_user():
    auth_screen()
    st.stop()

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

if st.session_state.get("nav") not in ("Top Docs Home", "Patient Portal"):
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

        signed_in = current_user()
        st.caption(f"Signed in: **{signed_in['name']}** · {signed_in['role'].title()}")
        allowed_pages = PAGES[1:] if signed_in["role"] == "admin" else [
            "Dashboard", "AI Assistant", "Find a Doctor", "Appointments",
            "Medical Reports", "Medication Info", "Symptom Triage",
            "Patient Education", "Support", "Follow-up"
        ]
        current_nav = st.session_state.get("nav", "Dashboard")
        if current_nav not in allowed_pages:
            st.session_state["nav"] = allowed_pages[0]
        nav = st.radio(
            "Navigation",
            allowed_pages,
            key="nav",
            format_func=lambda p: f"{PAGE_ICONS.get(p, '•')}  {p}",
            label_visibility="collapsed",
        )
        if st.button("Log out", key="logout_button", use_container_width=True):
            audit_event("logout")
            st.session_state.pop("auth_user", None)
            st.session_state["nav"] = "Top Docs Home"
            st.rerun()

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
            <a class="td-nav-cta" href="?patient=1">Book / My appointments</a>
          </div>

          <div class="td-hero" id="how-it-works">
            <div>
              <div class="td-eyebrow">Online specialist consultations and second opinions</div>
              <h1 class="td-title">India's top<br>doctors,<br><em>now within<br>reach.</em></h1>
              <div class="td-copy">Get a specialist consultation from doctors trained at leading medical institutes.</div>
              <a class="td-main-cta" href="?patient=1">Book an appointment <span class="arrow">→</span></a>
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

        <section class="td-specialties" id="specialties">
          <div class="td-wrap">
            <div class="td-institutes-title">Explore specialist care</div>
            <div class="td-specialty-grid">
              <a class="td-specialty" href="?patient=1">Gynaecology</a>
              <a class="td-specialty" href="?patient=1">Gastroenterology</a>
              <a class="td-specialty" href="?patient=1">Cardiology</a>
              <a class="td-specialty" href="?patient=1">Neurology</a>
              <a class="td-specialty" href="?patient=1">General Medicine</a>
            </div>
          </div>
        </section>

        <section class="td-institutes" id="institutes">
          <div class="td-wrap">
            <div class="td-institutes-title">Doctors trained at leading medical institutes</div>
            <div class="td-logos">
              <div class="td-inst"><div class="td-inst-mark">◉</div>AIIMS</div>
              <div class="td-inst"><div class="td-inst-mark">◍</div>PGIMER</div>
              <div class="td-inst"><div class="td-inst-mark">◆</div>Tata Memorial</div>
              <div class="td-inst"><div class="td-inst-mark">◌</div>JIPMER</div>
              <div class="td-inst"><div class="td-inst-mark">◎</div>CMC Vellore</div>
            </div>
            <div class="td-footer-note">Institute names describe where doctors trained. They do not mean the institutes employ, partner with or endorse Top Docs.</div>
          </div>
        </section>

        <section class="td-faq" id="questions">
          <div class="td-wrap">
            <div class="td-institutes-title">Questions, answered</div>
            <div class="td-faq-item"><strong>How do I find the right specialist?</strong>Click “Find my specialist” or choose a specialty above to open the MediAgent assistant.</div>
            <div class="td-faq-item"><strong>Are the doctor profiles and availability live?</strong>This academic demo uses illustrative doctor profiles and availability; it does not confirm real appointments.</div>
            <div class="td-faq-item"><strong>Can the assistant diagnose or prescribe?</strong>No. It provides general information and helps route requests; medical decisions should be discussed with a qualified healthcare professional.</div>
            <div class="td-footer-note">Demo / academic system. Doctor data, availability, and responses are illustrative.</div><div class="td-footer-note">Administrator? Open the separate admin URL: <code>http://localhost:8501/?admin=1</code> (replace localhost with your deployed site domain when hosted).</div>
          </div>
        </section>

        <div class="td-assistant-note">Your Top Docs patient portal</div>
        <a id="assistant" class="td-fab" href="?patient=1" aria-label="Open patient appointment portal">
          <span class="td-fab-label">Book / My appointments</span>
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
# DASHBOARD / PUBLIC PATIENT PORTAL

if nav == "Patient Portal":
    render_patient_portal()
    render_floating_mediagent()

if nav not in ("Top Docs Home", "Patient Portal"):
    c_back, c_space = st.columns([1, 5])
    with c_back:
        if st.button("← Top Docs", key="back_to_topdocs"):
            st.session_state["nav_target"] = "Top Docs Home"
            st.rerun()

if nav == "Admin Panel":
    hero("Admin Control Panel", "Private operations workspace for patient accounts, appointment oversight, payment follow-up, support workload, and security activity.")
    if require_admin():
        st.markdown("### Operations overview")
        metric_cols = st.columns(4, gap="medium")
        admin_metrics = [
            ("Registered patients", "SELECT COUNT(*) FROM patients"),
            ("Total appointments", "SELECT COUNT(*) FROM appointments"),
            ("Pending payments", "SELECT COUNT(*) FROM appointments WHERE LOWER(COALESCE(payment_status, 'pending')) NOT IN ('paid','not_required') AND LOWER(COALESCE(status,'')) <> 'cancelled'"),
            ("Open support tickets", "SELECT COUNT(*) FROM support_tickets WHERE LOWER(COALESCE(status,'')) IN ('open','pending','in_progress')"),
        ]
        for col, (label, query) in zip(metric_cols, admin_metrics):
            with col:
                try:
                    metric_card(label, get_scalar(query))
                except Exception:
                    metric_card(label, "—")

        st.markdown("### Create patient account")
        with st.form("admin_create_patient"):
            patient_name = st.text_input("Patient full name")
            patient_email = st.text_input("Patient email").strip().lower()
            patient_phone = st.text_input("Patient phone (optional)")
            patient_password = st.text_input("Temporary password (minimum 8 characters)", type="password")
            create_patient = st.form_submit_button("Create patient", type="primary")
        if create_patient:
            if not patient_name.strip() or "@" not in patient_email:
                st.warning("Enter a name and valid email.")
            elif len(patient_password) < 8:
                st.warning("Temporary password must have at least 8 characters.")
            else:
                try:
                    with db_connect() as conn:
                        created = conn.execute(
                            """INSERT INTO users(name,email,phone,password_hash,role)
                               VALUES (%s,%s,%s,%s,'patient') RETURNING id""",
                            (patient_name.strip(), patient_email, patient_phone.strip() or None,
                             hash_password(patient_password)),
                        ).fetchone()
                        conn.execute("INSERT INTO patients(user_id) VALUES (%s)", (created["id"],))
                    st.success(f"Patient account created for {patient_email}. Share the temporary password securely.")
                    audit_event("admin_created_patient")
                except psycopg.errors.UniqueViolation:
                    st.error("That email is already registered.")
                except Exception as exc:
                    st.error(f"Could not create the patient account: {exc}")

        st.markdown("### Patient directory")
        patient_search = st.text_input("Search patients by name, email, or phone", key="admin_patient_search")
        patients = fetch_rows(
            """SELECT u.id, u.name, u.email, u.phone, u.created_at
               FROM users u JOIN patients p ON p.user_id=u.id
               WHERE (%s = '' OR u.name ILIKE %s OR u.email ILIKE %s OR COALESCE(u.phone,'') ILIKE %s)
               ORDER BY u.id DESC LIMIT 500""",
            (patient_search.strip(), f"%{patient_search.strip()}%", f"%{patient_search.strip()}%", f"%{patient_search.strip()}%"),
        )
        if patients:
            st.dataframe(patients, use_container_width=True, hide_index=True)
            st.download_button("Export patient directory (CSV)", data=__import__('pandas').DataFrame(patients).to_csv(index=False).encode('utf-8'), file_name="patient_directory.csv", mime="text/csv")
        else:
            st.info("No patient accounts match this search.")

        st.markdown("### Appointment operations")
        a1, a2 = st.columns(2)
        with a1:
            appt_status_filter = st.selectbox("Appointment status", ["All", "pending", "confirmed", "completed", "cancelled"], key="admin_appt_status")
        with a2:
            payment_filter = st.selectbox("Payment status", ["All", "pending", "paid", "failed", "not_required"], key="admin_payment_status")
        appt_rows = fetch_rows(
            """SELECT a.id AS appointment_id, u.name AS patient, u.phone, d.name AS doctor,
                      COALESCE(sp.name,'General Medicine') AS specialty, a.appointment_date,
                      COALESCE(a.appointment_slot,'To be confirmed') AS appointment_slot,
                      a.status, COALESCE(a.payment_status,'pending') AS payment_status,
                      COALESCE(a.consultation_fee,0) AS fee
               FROM appointments a JOIN patients p ON p.id=a.patient_id
               JOIN users u ON u.id=p.user_id JOIN doctors d ON d.id=a.doctor_id
               LEFT JOIN specialties sp ON sp.id=d.specialty_id
               WHERE (%s='All' OR LOWER(COALESCE(a.status,''))=LOWER(%s))
                 AND (%s='All' OR LOWER(COALESCE(a.payment_status,'pending'))=LOWER(%s))
               ORDER BY a.appointment_date DESC, a.id DESC LIMIT 500""",
            (appt_status_filter, appt_status_filter, payment_filter, payment_filter),
        )
        if appt_rows:
            st.dataframe(appt_rows, use_container_width=True, hide_index=True)
            st.download_button("Export appointment report (CSV)", data=__import__('pandas').DataFrame(appt_rows).to_csv(index=False).encode('utf-8'), file_name="appointment_operations.csv", mime="text/csv")
        else:
            st.info("No appointments match the selected filters.")

        st.markdown("### Support queue")
        try:
            tickets = fetch_rows(
                """SELECT id AS ticket_id, status, priority, issue, created_at
                   FROM support_tickets ORDER BY
                   CASE LOWER(COALESCE(priority,'')) WHEN 'high' THEN 0 WHEN 'urgent' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                   created_at DESC LIMIT 100"""
            )
            if tickets:
                st.dataframe(tickets, use_container_width=True, hide_index=True)
            else:
                st.info("No support tickets found.")
        except Exception:
            st.info("Support queue is unavailable in the current database schema.")

        st.markdown("### Recent login and security events")
        events = fetch_rows(
            """SELECT a.created_at, u.email, a.event
               FROM auth_login_audit a LEFT JOIN users u ON u.id=a.user_id
               ORDER BY a.id DESC LIMIT 50"""
        )
        if events:
            st.dataframe(events, use_container_width=True, hide_index=True)
        else:
            st.info("No login/security events recorded yet.")


# ============================================================
# PATIENT-SCOPED APPOINTMENT CHAT HELPERS
# ============================================================

def get_signed_in_patient_appointments() -> List[Dict[str, Any]]:
    """Return appointment data only for the currently authenticated patient."""
    patient_id = current_patient_id()
    if not patient_id:
        return []
    return fetch_rows(
        """SELECT a.id, a.appointment_date,
                  COALESCE(a.appointment_slot, 'Time to be confirmed') AS appointment_slot,
                  a.status, COALESCE(a.payment_status, 'not_required') AS payment_status,
                  COALESCE(a.consultation_fee, 0) AS consultation_fee,
                  d.name AS doctor, COALESCE(sp.name, 'General Medicine') AS specialty
           FROM appointments a
           JOIN doctors d ON d.id = a.doctor_id
           LEFT JOIN specialties sp ON sp.id = d.specialty_id
           WHERE a.patient_id = %s
           ORDER BY a.appointment_date DESC, a.id DESC""",
        (patient_id,),
    )


def answer_patient_appointment_question(prompt: str) -> Optional[str]:
    """Deterministic appointment answers; never infer patient identity from chat text."""
    user = current_user()
    if not user or user.get("role") != "patient":
        if any(k in prompt.lower() for k in ("my appointment", "my booking", "appointment booked", "reschedule", "payment pending", "payment done")):
            return "Please sign in to your patient account first. I can then check only the appointments linked to your account."
        return None

    q = prompt.lower()
    appt_words = ("appointment", "booking", "reschedule", "re-schedule", "payment pending", "payment done", "payment status")
    if not any(k in q for k in appt_words):
        return None

    rows = get_signed_in_patient_appointments()
    if not rows:
        return "I couldn't find an appointment linked to your signed-in account yet. You can book one from the Patient Portal."

    if any(k in q for k in ("reschedule", "re-schedule", "change my time", "change appointment", "change the date")):
        active_rows = [
            r for r in rows
            if str(r.get("status", "")).lower() not in ("cancelled", "canceled", "completed")
        ]
        if not active_rows:
            return "I couldn't find an active appointment to reschedule. You can book a new appointment from the Patient Portal."
        st.session_state["chat_reschedule_active"] = True
        st.session_state["chat_reschedule_phase"] = "confirm"
        st.session_state["chat_reschedule_rows"] = active_rows
        st.session_state["chat_reschedule_selected_id"] = None
        st.session_state.pop("chat_reschedule_new_date", None)
        st.session_state.pop("chat_reschedule_new_slot", None)
        if len(active_rows) == 1:
            current = active_rows[0]
            st.session_state["chat_reschedule_selected_id"] = int(current["id"])
            appt_date = current.get("appointment_date")
            date_text = appt_date.strftime("%d %b %Y") if hasattr(appt_date, "strftime") else str(appt_date)
            time_text = current.get("appointment_slot") or "Time to be confirmed"
            payment_text = str(current.get("payment_status") or "not_required").replace("_", " ").title()
            return (
                f"I found your current booking:\\n\\n"
                f"- **Appointment ID:** #{current['id']}\\n"
                f"- **Doctor:** {current.get('doctor', 'Doctor not listed')}\\n"
                f"- **Specialty:** {current.get('specialty', 'General Medicine')}\\n"
                f"- **Current date:** {date_text}\\n"
                f"- **Current time:** {time_text}\\n"
                f"- **Payment:** {payment_text}\\n\\n"
                f"Would you like to reschedule this appointment? Choose **Yes, reschedule** or **No, keep current booking** below. "
                f"I will update this same appointment only after you review and confirm the new date and time."
            )
        return (
            f"I found {len(active_rows)} active appointments linked to your account. "
            "Choose which booking you want to change in the selector below. I’ll show its current doctor, date, time, and payment status before asking you to confirm. "
            "No appointment will change until you confirm the final review."
        )

    active = [r for r in rows if str(r.get("status", "")).lower() != "cancelled"]
    if not active:
        return "I found your previous appointments, but none are currently active. You can start a new booking from the Patient Portal."

    lines = []
    for r in active[:5]:
        payment = str(r.get("payment_status") or "not_required").lower()
        date_text = r["appointment_date"].strftime("%d %b %Y") if hasattr(r["appointment_date"], "strftime") else str(r["appointment_date"])
        slot = r.get("appointment_slot") or "Time to be confirmed"
        if payment not in ("paid", "not_required"):
            lines.append(f"- **Appointment #{r['id']} — payment pending**. Your saved slot is **{date_text} at {slot}** with **{r['doctor']}**. Fee: ₹{float(r.get('consultation_fee') or 0):.0f}. Complete payment to finish the booking.")
        else:
            lines.append(f"- **Appointment #{r['id']}**: **{date_text} at {slot}** with **{r['doctor']}** ({r['specialty']}).")
    return "Here’s the latest appointment information linked to your account:\n\n" + "\n".join(lines)



if nav == "Dashboard":
    hero(
        "Healthcare AI Command Center",
        "A unified workspace for intelligent patient support, specialist routing, clinical-document assistance, appointments, and service operations.",
    )

    cols = st.columns(4, gap="medium")
    with cols[0]: metric_card("Appointments", get_scalar("SELECT COUNT(*) FROM appointments"))
    with cols[1]: metric_card("Open Tickets", get_scalar("SELECT COUNT(*) FROM support_tickets WHERE status='open'"))
    with cols[2]: metric_card("Saved Reports", get_scalar("SELECT COUNT(*) FROM medical_reports"))
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

    signed_user = current_user()
    if signed_user and signed_user.get("role") == "patient":
        st.caption(f"Signed in as {signed_user.get('name', 'patient')} · Appointment answers use your account only.")
    else:
        st.info("Sign in as a patient to view your personal appointment and payment details.")

    if st.session_state.get("chat_reschedule_active") and signed_user and signed_user.get("role") == "patient":
        reschedule_rows = [
            r for r in get_signed_in_patient_appointments()
            if str(r.get("status", "")).lower() not in ("cancelled", "canceled", "completed")
        ]
        phase = st.session_state.get("chat_reschedule_phase", "confirm")

        if not reschedule_rows:
            st.info("There are no active appointments available to reschedule.")
            if st.button("Close reschedule", key="close_reschedule_empty"):
                st.session_state["chat_reschedule_active"] = False
                st.rerun()
        else:
            st.markdown("### Reschedule your appointment")
            st.caption("We'll keep the same appointment ID. No new appointment will be created.")

            if len(reschedule_rows) > 1:
                appt_options = {
                    int(r["id"]): f"#{r['id']} · {r['doctor']} · {r['appointment_date']} · {r.get('appointment_slot') or 'Time to be confirmed'}"
                    for r in reschedule_rows
                }
                default_id = st.session_state.get("chat_reschedule_selected_id")
                selected_appt = st.selectbox(
                    "Which appointment would you like to change?",
                    list(appt_options.keys()),
                    index=list(appt_options.keys()).index(default_id) if default_id in appt_options else 0,
                    format_func=lambda x: appt_options[x],
                    key="chat_reschedule_appt_choice",
                )
                st.session_state["chat_reschedule_selected_id"] = int(selected_appt)
            else:
                selected_appt = int(reschedule_rows[0]["id"])
                st.session_state["chat_reschedule_selected_id"] = selected_appt

            selected_row = next((r for r in reschedule_rows if int(r["id"]) == int(selected_appt)), None)

            if selected_row:
                current_date = selected_row.get("appointment_date")
                current_date_text = current_date.strftime("%d %b %Y") if hasattr(current_date, "strftime") else str(current_date)
                current_slot = selected_row.get("appointment_slot") or "Time to be confirmed"
                current_status = str(selected_row.get("status") or "scheduled").replace("_", " ").title()
                current_payment = str(selected_row.get("payment_status") or "pending").replace("_", " ").title()
                with st.container(border=True):
                    st.markdown(f"**Your current booking · Appointment #{selected_appt}**")
                    st.markdown(f"**Doctor:** {selected_row.get('doctor', 'Doctor not listed')}")
                    st.markdown(f"**Specialty:** {selected_row.get('specialty', 'General Medicine')}")
                    st.markdown(f"**Current date:** {current_date_text}")
                    st.markdown(f"**Current time:** {current_slot}")
                    st.markdown(f"**Appointment status:** {current_status} · **Payment:** {current_payment}")

                if phase == "confirm":
                    st.markdown("**Would you like to reschedule this appointment?**")
                    yes_col, no_col = st.columns(2)
                    with yes_col:
                        if st.button("Yes, reschedule", type="primary", use_container_width=True, key="reschedule_yes"):
                            st.session_state["chat_reschedule_phase"] = "date"
                            st.rerun()
                    with no_col:
                        if st.button("No, keep current booking", use_container_width=True, key="reschedule_no"):
                            st.session_state["chat_reschedule_active"] = False
                            st.session_state["chat_reschedule_phase"] = "confirm"
                            st.session_state["chat_messages"].append({
                                "role": "assistant",
                                "content": f"No changes made. Your appointment #{selected_appt} remains booked for {current_date_text} at {current_slot} with {selected_row.get('doctor')}."
                            })
                            st.rerun()

                elif phase == "date":
                    st.markdown("**Step 1 of 3 · Choose a new date**")
                    min_date = date.today()
                    default_date = st.session_state.get("chat_reschedule_new_date", min_date + timedelta(days=1))
                    chosen_date = st.date_input(
                        "New appointment date",
                        min_value=min_date,
                        value=max(default_date, min_date),
                        key="chat_reschedule_date_picker",
                    )
                    date_col, cancel_col = st.columns(2)
                    with date_col:
                        if st.button("Continue to available times", type="primary", use_container_width=True, key="reschedule_date_continue"):
                            st.session_state["chat_reschedule_new_date"] = chosen_date
                            st.session_state.pop("chat_reschedule_new_slot", None)
                            st.session_state["chat_reschedule_phase"] = "time"
                            st.rerun()
                    with cancel_col:
                        if st.button("Cancel reschedule", use_container_width=True, key="reschedule_cancel_date"):
                            st.session_state["chat_reschedule_active"] = False
                            st.rerun()

                elif phase == "time":
                    chosen_date = st.session_state.get("chat_reschedule_new_date")
                    if not chosen_date:
                        st.session_state["chat_reschedule_phase"] = "date"
                        st.rerun()
                    date_text = chosen_date.strftime("%d %b %Y")
                    st.markdown(f"**Step 2 of 3 · Choose a time for {date_text}**")
                    try:
                        available_slots = get_available_slots(
                            selected_row["doctor"], chosen_date, exclude_appointment_id=int(selected_appt)
                        )
                    except Exception:
                        available_slots = []
                    if not available_slots:
                        st.warning("No available times were found for this doctor on that date. Go back and choose another date.")
                    else:
                        chosen_slot = st.radio(
                            "Available appointment times",
                            available_slots,
                            horizontal=True,
                            key=f"chat_reschedule_slot_picker_{selected_appt}_{chosen_date}",
                        )
                        left, right = st.columns(2)
                        with left:
                            if st.button("Review new appointment", type="primary", use_container_width=True, key="reschedule_time_continue"):
                                st.session_state["chat_reschedule_new_slot"] = chosen_slot
                                st.session_state["chat_reschedule_phase"] = "review"
                                st.rerun()
                        with right:
                            if st.button("Choose another date", use_container_width=True, key="reschedule_back_date"):
                                st.session_state["chat_reschedule_phase"] = "date"
                                st.rerun()

                elif phase == "review":
                    chosen_date = st.session_state.get("chat_reschedule_new_date")
                    chosen_slot = st.session_state.get("chat_reschedule_new_slot")
                    if not chosen_date or not chosen_slot:
                        st.session_state["chat_reschedule_phase"] = "date"
                        st.rerun()
                    st.markdown("**Step 3 of 3 · Confirm your changes**")
                    with st.container(border=True):
                        st.markdown(f"**Doctor:** {selected_row.get('doctor')}")
                        st.markdown(f"**Old booking:** {current_date_text} · {current_slot}")
                        st.markdown(f"**New booking:** {chosen_date.strftime('%d %b %Y')} · {chosen_slot}")
                        st.caption("Only the existing appointment will be updated. Its appointment ID and payment status will be retained.")
                    confirm_col, back_col = st.columns(2)
                    with confirm_col:
                        if st.button("Confirm reschedule", type="primary", use_container_width=True, key="reschedule_final_confirm"):
                            patient_id = current_patient_id()
                            try:
                                with db_connect() as conn:
                                    occupied = conn.execute(
                                        """SELECT id FROM appointments
                                           WHERE doctor_id=(SELECT doctor_id FROM appointments WHERE id=%s)
                                             AND appointment_date=%s AND appointment_slot=%s
                                             AND id<>%s
                                             AND LOWER(COALESCE(status,'')) NOT IN ('cancelled','canceled','completed')
                                           LIMIT 1""",
                                        (int(selected_appt), chosen_date, chosen_slot, int(selected_appt)),
                                    ).fetchone()
                                    if occupied:
                                        st.warning("That time was just booked. Please choose another available time.")
                                        st.session_state["chat_reschedule_phase"] = "time"
                                        st.stop()
                                    updated = conn.execute(
                                        """UPDATE appointments
                                           SET appointment_date=%s, appointment_slot=%s, status='rescheduled'
                                           WHERE id=%s AND patient_id=%s
                                             AND LOWER(COALESCE(status,'')) NOT IN ('cancelled','canceled','completed')
                                           RETURNING id""",
                                        (chosen_date, chosen_slot, int(selected_appt), patient_id),
                                    ).fetchone()
                                if updated:
                                    confirmation = (
                                        f"Rescheduled successfully. Your existing appointment **#{selected_appt}** "
                                        f"with **{selected_row.get('doctor')}** is now **{chosen_date.strftime('%d %b %Y')} "
                                        f"at {chosen_slot}**. No new appointment was created."
                                    )
                                    st.session_state["chat_messages"].append({"role": "assistant", "content": confirmation})
                                    st.session_state["chat_reschedule_active"] = False
                                    st.session_state["chat_reschedule_phase"] = "confirm"
                                    st.session_state["patient_reschedule_notice"] = (
                                        f"Appointment #{selected_appt} updated to {chosen_date.strftime('%d %b %Y')} at {chosen_slot}."
                                    )
                                    st.session_state["nav"] = "Patient Portal"
                                    st.session_state["patient_journey_step"] = 6
                                    st.session_state["patient_journey_patient_id"] = patient_id
                                    st.session_state["patient_journey_appointment_id"] = int(selected_appt)
                                    st.rerun()
                                else:
                                    st.error("This appointment could not be updated. Please refresh and try again.")
                            except Exception as exc:
                                st.error(f"Reschedule failed ({type(exc).__name__}). Your existing appointment has not been intentionally replaced.")
                    with back_col:
                        if st.button("Back to time selection", use_container_width=True, key="reschedule_review_back"):
                            st.session_state["chat_reschedule_phase"] = "time"
                            st.rerun()

    user_prompt = st.chat_input("Ask about your appointment or health guidance…")
    if user_prompt and user_prompt.strip():
        user_prompt = user_prompt.strip()
        st.session_state["chat_messages"].append({"role": "user", "content": user_prompt})
        personal_answer = answer_patient_appointment_question(user_prompt)
        if personal_answer is not None:
            st.session_state["chat_messages"].append({"role": "assistant", "content": personal_answer})
            st.rerun()
        else:
            result = SUPERVISOR.run(user_prompt)
            st.session_state["chat_messages"].append({"role": "assistant", "content": result.response})
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
            signed_in = current_user()
            patient = st.text_input(
                "Patient name",
                value=signed_in["name"] if signed_in and signed_in["role"] == "patient" else "",
                disabled=bool(signed_in and signed_in["role"] == "patient"),
            )
            doctor = st.selectbox("Doctor", [d["name"] for d in DOCTORS])
            appt_date = st.date_input("Appointment date", min_value=date.today())
            reason = st.text_area("Reason for appointment")
            submitted = st.form_submit_button("Create appointment", type="primary")

        if submitted:
            if not patient.strip() or not reason.strip():
                st.warning("Please fill in patient name and reason.")
            else:
                try:
                    appointment_id = SUPERVISOR.appointment.book(
                        patient.strip(),
                        doctor,
                        appt_date,
                        reason.strip(),
                    )
                    response = (
                        f"Appointment **#{appointment_id}** created for **{patient.strip()}** "
                        f"with **{doctor}** on **{appt_date.isoformat()}**."
                    )
                    st.success(response)
                    patient_id = get_or_create_patient(patient.strip())
                    insert_interaction(
                        "Appointment booking",
                        SUPERVISOR.appointment.name,
                        reason,
                        response,
                        patient_id=patient_id,
                    )
                except ValueError as exc:
                    st.error(str(exc))
                except psycopg.Error as exc:
                    st.error(
                        f"Database error while creating the appointment: {type(exc).__name__}."
                    )

    elif action == "Reschedule":
        rows = fetch_rows(
            """
            SELECT a.id,
                   u.name AS patient,
                   d.name AS doctor,
                   a.appointment_date,
                   a.status
            FROM appointments a
            JOIN patients p ON p.id = a.patient_id
            JOIN users u ON u.id = p.user_id
            JOIN doctors d ON d.id = a.doctor_id
            WHERE a.status <> 'cancelled'
              AND (%s = 'admin' OR p.user_id = %s)
            ORDER BY a.id DESC
            """,
            (current_user()["role"], current_user()["id"]),
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
            new_date = st.date_input("New date", min_value=date.today(), key="management_reschedule_date")
            selected = next((r for r in rows if int(r["id"]) == int(appointment_id)), None)
            available_slots = []
            if selected:
                try:
                    available_slots = get_available_slots(
                        selected["doctor"], new_date, exclude_appointment_id=int(appointment_id)
                    )
                except Exception:
                    available_slots = []
            if available_slots:
                new_slot = st.selectbox("New time", available_slots, key=f"management_reschedule_slot_{appointment_id}_{new_date}")
            else:
                new_slot = None
                st.warning("No available slots for this doctor on the selected date.")
            if st.button("Reschedule existing appointment", type="primary", disabled=not bool(new_slot)):
                try:
                    ok = SUPERVISOR.appointment.reschedule(int(appointment_id), new_date, new_slot)
                    if ok:
                        st.session_state["patient_reschedule_notice"] = (
                            f"Existing appointment #{appointment_id} updated to {new_date.isoformat()} at {new_slot}. No new appointment was created."
                        )
                        st.rerun()
                    else:
                        st.error("Unable to reschedule this appointment.")
                except ValueError as exc:
                    st.error(str(exc))
                except psycopg.Error as exc:
                    st.error(
                        f"Database error while rescheduling: {type(exc).__name__}."
                    )

    else:
        rows = fetch_rows(
            """
            SELECT a.id,
                   u.name AS patient,
                   d.name AS doctor,
                   a.appointment_date,
                   a.status
            FROM appointments a
            JOIN patients p ON p.id = a.patient_id
            JOIN users u ON u.id = p.user_id
            JOIN doctors d ON d.id = a.doctor_id
            WHERE a.status <> 'cancelled'
              AND (%s = 'admin' OR p.user_id = %s)
            ORDER BY a.id DESC
            """,
            (current_user()["role"], current_user()["id"]),
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
        SELECT a.id,
               u.name AS patient,
               d.name AS doctor,
               a.appointment_date,
               a.reason,
               a.status,
               a.created_at
        FROM appointments a
        JOIN patients p ON p.id = a.patient_id
        JOIN users u ON u.id = p.user_id
        JOIN doctors d ON d.id = a.doctor_id
        WHERE (%s = 'admin' OR p.user_id = %s)
        ORDER BY a.id DESC
        """,
        (current_user()["role"], current_user()["id"]),
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

    signed_in = current_user()
    patient_name = st.text_input(
        "Patient name",
        value=signed_in["name"] if signed_in and signed_in["role"] == "patient" else "Demo Patient",
        disabled=bool(signed_in and signed_in["role"] == "patient"),
    )
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
            result = SUPERVISOR.report.run(
                report_text,
                title.strip() or "Medical Report",
                patient_name.strip() or "Demo Patient",
            )
            st.session_state["report_result"] = result.as_dict()

    if "report_result" in st.session_state:
        render_result(st.session_state["report_result"])

    st.markdown("### Saved Reports")
    rows = fetch_rows(
        """
        SELECT r.id, u.name AS patient, r.title, r.created_at
        FROM medical_reports r
        JOIN patients p ON p.id = r.patient_id
         JOIN users u ON u.id = p.user_id
        WHERE (%s = 'admin' OR p.user_id = %s)
        ORDER BY r.id DESC
        LIMIT 10
        """,
        (current_user()["role"], current_user()["id"]),
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
        signed_in = current_user()
        patient = st.text_input(
            "Your name",
            value=signed_in["name"] if signed_in and signed_in["role"] == "patient" else "",
            disabled=bool(signed_in and signed_in["role"] == "patient"),
        )
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
                f"Priority: **{priority}**. Status: **open**."
            )
            st.success(response)
            patient_id = get_or_create_patient(patient.strip())
            insert_interaction(
                "Customer support",
                SUPERVISOR.support.name,
                issue,
                response,
                patient_id=patient_id,
            )

    st.markdown("### Ticket Records")
    rows = fetch_rows(
        """
        SELECT t.id,
               u.name AS patient,
               t.issue,
               t.priority,
               t.status,
               t.created_at
        FROM support_tickets t
        JOIN patients p ON p.id = t.patient_id
         JOIN users u ON u.id = p.user_id
        WHERE (%s = 'admin' OR p.user_id = %s)
        ORDER BY t.id DESC
        """,
        (current_user()["role"], current_user()["id"]),
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
    f"LLM: {LLM_PROVIDER}/{GROQ_MODEL if LLM_PROVIDER == 'groq' else OLLAMA_MODEL} · Database: PostgreSQL"
)
