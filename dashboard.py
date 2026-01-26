import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
import os
import re
import time
import traceback
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# =========================================================
#   CONFIGURATION
# =========================================================
st.set_page_config(
    page_title="Potwell Hintaseuranta",
    page_icon="🥔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
#   LOGIN & DASHBOARD CSS (ORIGINAL)
# =========================================================
def apply_login_css():
    st.markdown("""
        <style>
        .stApp {
            background: radial-gradient(circle at 50% 10%, rgb(25,25,30) 0%, rgb(5,5,5) 100%);
            color: #e0e0e0;
        }
        div[data-testid="stTextInput"] input {
            background-color: rgba(255,255,255,0.05) !important;
            color: #e0e0e0 !important;
            border: 1px solid rgba(255,255,255,0.12) !important;
            border-radius: 10px !important;
            padding: 10px 12px !important;
        }
        </style>
    """, unsafe_allow_html=True)

def apply_dashboard_css():
    st.markdown("""
        <style>
        .stApp {
            background: radial-gradient(circle at 50% 10%, rgb(245,246,250) 0%, rgb(232,235,242) 100%);
            color: #111827;
        }
        h1,h2,h3,h4,h5,h6,p,div,span,label { color:#111827; }
        section[data-testid="stSidebar"] {
            background: rgba(255,255,255,0.75);
            backdrop-filter: blur(8px);
            border-right: 1px solid rgba(17,24,39,0.08);
        }
        </style>
    """, unsafe_allow_html=True)

# =========================================================
#   AUTHENTICATION
# =========================================================
def check_password():
    apply_login_css()
    CORRECT_PASSWORD = "Potwell25!"

    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    st.markdown("## POTWELL HINTASEURANTA")
    with st.form("login_form"):
        password = st.text_input("SYÖTÄ SALASANA", type="password")
        if st.form_submit_button("KIRJAUDU"):
            if password == CORRECT_PASSWORD:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("Väärä salasana")
    return False

if not check_password():
    st.stop()

apply_dashboard_css()

# =========================================================
#   STORE NORMALIZATION & CHAIN LOGIC
# =========================================================
def normalize_store_name(x):
    x = str(x).strip()
    x = re.sub(r"\s+", " ", x)
    x = re.sub(r"\(\s*", "(", x)
    x = re.sub(r"\s*\)", ")", x)
    return x

# Explicit Citymarket overrides (plain names)
CITYMARKET_OVERRIDES = {
    "Espoo (Iso Omena)",
    "Jyväskylä (Seppälä)",
    "Kuopio (Päiväranta)",
    "Pirkkala",
    "Rovaniemi",
    "Seinäjoki (Päivölä)",
    "Turku (Kupittaa)",
    "Vaasa (Kivihaka)",
}

K_CHAIN_ORDER = ["Citymarket", "K-Supermarket", "K-Market"]
S_CHAINS = {"Prisma", "S-Market", "Sale", "Alepa"}

def get_chain(store):
    s = normalize_store_name(store)
    u = s.upper()

    if s in CITYMARKET_OVERRIDES:
        return "Citymarket"

    if re.search(r"\(\s*SM\b", u):
        return "K-Supermarket"

    if re.search(r"\(\s*KM\b", u):
        return "K-Market"

    if "CITYMARKET" in u:
        return "Citymarket"

    if "PRISMA" in u:
        return "Prisma"
    if "ALEPA" in u:
        return "Alepa"
    if re.search(r"\bSALE\b", u):
        return "Sale"
    if "S-MARKET" in u:
        return "S-Market"

    return "Muu"

def get_group(chain):
    if chain in K_CHAIN_ORDER:
        return "K-Ryhmä"
    if chain in S_CHAINS:
        return "S-Ryhmä"
    return "Muu"

# =========================================================
#   DATA LOADER
# =========================================================
@st.cache_data(ttl=60)
def load_data():
    try:
        scope = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        if os.path.exists("service_account.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
        else:
            creds = ServiceAccountCredentials.from_json_keyfile_dict(
                dict(st.secrets["gcp_service_account"]), scope
            )

        sheet = gspread.authorize(creds).open("Potwell Data").sheet1
        df = pd.DataFrame(sheet.get_all_records())

        # Normalize EAN column
        ean_cols = [c for c in df.columns if c.lower() == "ean"]
        if ean_cols:
            df.rename(columns={ean_cols[0]: "ean"}, inplace=True)
        else:
            df["ean"] = ""

        df["kauppa"] = df["kauppa"].apply(normalize_store_name)
        df["Ketju"] = df["kauppa"].apply(get_chain)
        df["Ryhmä"] = df["Ketju"].apply(get_group)

        df["pvm"] = pd.to_datetime(df["pvm"], errors="coerce")
        df["hinta"] = (
            df["hinta"].astype(str).str.replace(",", ".").astype(float)
        )
        df.loc[df["hinta"] > 40, "hinta"] /= 100

        return df.dropna(subset=["pvm"])

    except Exception:
        st.error("Data load failed")
        st.code(traceback.format_exc())
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.stop()

# =========================================================
#   HINTAMATRIISI (WITH EAN + ORDERING)
# =========================================================
st.subheader("📊 Hintamatriisi")

matrix_group = st.radio("Valitse Ryhmä", ["K-Ryhmä", "S-Ryhmä"], horizontal=True)

allowed_chains = K_CHAIN_ORDER if matrix_group == "K-Ryhmä" else sorted(S_CHAINS)
m_df = df[df["Ketju"].isin(allowed_chains)].copy()

dates = sorted(m_df["pvm"].unique(), reverse=True)
latest, prev = dates[0], dates[1] if len(dates) > 1 else None

cur = m_df[m_df["pvm"] == latest].rename(columns={"hinta": "now"})
prev = (
    m_df[m_df["pvm"] == prev][["kauppa", "tuote", "ean", "hinta"]]
    .rename(columns={"hinta": "prev"})
    if prev is not None else None
)

if prev is not None:
    cur = cur.merge(prev, on=["kauppa", "tuote", "ean"], how="left")
else:
    cur["prev"] = np.nan

def fmt(r):
    if pd.isna(r["now"]):
        return None
    if pd.isna(r["prev"]):
        return f"{r['now']:.2f} €"
    return f"{r['now']:.2f} € {'▲' if r['now']>r['prev'] else '▼' if r['now']<r['prev'] else '➖'}"

cur["cell"] = cur.apply(fmt, axis=1)

matrix = cur.pivot_table(
    index=["tuote", "ean"],
    columns=["Ketju", "kauppa"],
    values="cell",
    aggfunc="first"
).dropna(how="all")

# Reorder chain columns
cols = sorted(
    matrix.columns,
    key=lambda c: (allowed_chains.index(c[0]), c[1])
)
matrix = matrix[cols].reset_index()

st.dataframe(
    matrix.style.map(
        lambda v: "color:green;font-weight:700" if "▲" in str(v)
        else "color:red;font-weight:700" if "▼" in str(v)
        else "",
        subset=[c for c in matrix.columns if c not in ["tuote", "ean"]]
    ),
    use_container_width=True,
    height=800
)

if st.button("🔄 Päivitä"):
    st.rerun()
