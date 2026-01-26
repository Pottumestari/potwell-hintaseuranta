import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
import os
import re
import traceback
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Potwell Hintaseuranta",
    page_icon="🥔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =========================================================
#   CSS: LOGIN (dark) vs DASHBOARD (light)
# =========================================================

def apply_login_css():
    st.markdown("""
        <style>
        .stApp {
            background: radial-gradient(circle at 50% 10%, rgb(25, 25, 30) 0%, rgb(5, 5, 5) 100%);
            color: #e0e0e0;
        }
        div[data-testid="stTextInput"] input {
            background-color: rgba(255, 255, 255, 0.05) !important;
            color: #e0e0e0 !important;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
            border-radius: 10px !important;
            padding: 10px 12px !important;
        }
        </style>
    """, unsafe_allow_html=True)

def apply_dashboard_css():
    st.markdown("""
        <style>
        .stApp {
            background: radial-gradient(circle at 50% 10%, rgb(245, 246, 250) 0%, rgb(232, 235, 242) 100%);
            color: #111827;
        }
        h1, h2, h3, h4, h5, h6, p, div, span, label { color: #111827; }
        section[data-testid="stSidebar"] {
            background: rgba(255, 255, 255, 0.75);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border-right: 1px solid rgba(17, 24, 39, 0.08);
        }
        div[data-testid="stDataFrame"], div[data-testid="stAltairChart"] {
            background: rgba(255,255,255,0.85) !important;
            border-radius: 12px;
            padding: 12px;
            border: 1px solid rgba(17, 24, 39, 0.08);
        }
        </style>
    """, unsafe_allow_html=True)

# =========================================================
#   AUTHENTICATION LOGIC
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
        password = st.text_input("SYÖTÄ SALASANA", type="password", placeholder="SYÖTÄ SALASANA")
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
#   STORE / CHAIN / GROUP MAPPING (ROBUST)
# =========================================================

def normalize_store_name(x: str) -> str:
    """
    Normalizes store names to make exact matching reliable:
    - trims
    - collapses multiple spaces
    - removes extra spaces just inside parentheses
    """
    s = str(x).strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\(\s*", "(", s)   # "( Iso Omena" -> "(Iso Omena"
    s = re.sub(r"\s*\)", ")", s)   # "Omena )" -> "Omena)"
    return s

# Explicit overrides: store name -> chain
# These are your K-Citymarkets that do NOT contain "Citymarket" in the "kauppa" column.
STORE_CHAIN_OVERRIDES = {
    "Espoo (Iso Omena)": "Citymarket",
    "Jyväskylä (Seppälä)": "Citymarket",
    "Kuopio (Päiväranta)": "Citymarket",
    "Pirkkala": "Citymarket",
    "Rovaniemi": "Citymarket",
    "Seinäjoki (Päivölä)": "Citymarket",
    "Turku (Kupittaa)": "Citymarket",
    "Vaasa (Kivihaka)": "Citymarket",
}

K_CHAINS = {"Citymarket", "K-Supermarket", "K-Market"}
S_CHAINS = {"Prisma", "S-Market", "Sale", "Alepa"}

ALLOWED_CHAINS = {
    "K-Ryhmä": sorted(list(K_CHAINS)),
    "S-Ryhmä": sorted(list(S_CHAINS)),
}

def get_chain(store: str) -> str:
    # 1) Normalize and try exact override first
    n = normalize_store_name(store)
    if n in STORE_CHAIN_OVERRIDES:
        return STORE_CHAIN_OVERRIDES[n]

    s = n.upper()

    # -------------------------------------------------
    # K-RYHMÄ (support abbreviations used in your data)
    # -------------------------------------------------
    # Citymarket: may appear as "K-Citymarket ..." OR "(CM ...)"
    if "K-CITYMARKET" in s or "KCITYMARKET" in s or "CITYMARKET" in s or re.search(r"(\bCM\b|\(CM\b)", s):
        return "Citymarket"

    # K-Supermarket: can appear as "K-Supermarket" or abbreviation "KSM"
    # IMPORTANT: do NOT treat plain "SM" as K-Supermarket (it conflicts with S-Market)
    if "K-SUPERMARKET" in s or re.search(r"(\bKSM\b|\(KSM\b|\bK[- ]?SUPERMARKET\b)", s):
        return "K-Supermarket"

    # K-Market: abbreviation "KM" is common in your store names, e.g. "(KM Erottaja)"
    if "K-MARKET" in s or re.search(r"(\bKM\b|\(KM\b|\bK[- ]?MARKET\b)", s):
        return "K-Market"

    # -------------------------------------------------
    # S-RYHMÄ
    # -------------------------------------------------
    if "PRISMA" in s:
        return "Prisma"

    # S-Market: can appear as "S-Market", "Smarket", or "(SM ...)" in some datasets
    if "S-MARKET" in s or "SMARKET" in s or re.search(r"(\bS[- ]?MARKET\b|\bSM\b|\(SM\b)", s):
        return "S-Market"

    if "ALEPA" in s:
        return "Alepa"

    if re.search(r"\bSALE\b", s):
        return "Sale"

    # Unknown stays unknown
    return "Muu"


def get_group(chain: str) -> str:
    if chain in K_CHAINS:
        return "K-Ryhmä"
    if chain in S_CHAINS:
        return "S-Ryhmä"
    return "Muu"

# =========================================================
#   DATA LOADER
# =========================================================
@st.cache_data(ttl=60)
def load_data():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    try:
        if os.path.exists("service_account.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
        else:
            creds_dict = dict(st.secrets["gcp_service_account"])
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)

        client = gspread.authorize(creds)
        sheet = client.open("Potwell Data").sheet1
        data = sheet.get_all_records()
        df = pd.DataFrame(data)

        if df.empty:
            return df

        # Required columns check
        required_cols = {"pvm", "hinta", "kauppa", "tuote"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns in sheet: {missing}")

        # Normalize store names BEFORE mapping
        df["kauppa"] = df["kauppa"].apply(normalize_store_name)

        # Type cleanup
        df["pvm"] = pd.to_datetime(df["pvm"], errors="coerce")
        df = df.dropna(subset=["pvm"])

        df["hinta"] = df["hinta"].astype(str).str.replace(",", ".", regex=False)
        df["hinta"] = pd.to_numeric(df["hinta"], errors="coerce")
        df.loc[df["hinta"] > 40, "hinta"] = df["hinta"] / 100.0

        # Chain/group mapping
        df["Ketju"] = df["kauppa"].apply(get_chain)
        df["Ryhmä"] = df["Ketju"].apply(get_group)

        return df

    except Exception:
        st.error("Data load failed. See details below.")
        st.code(traceback.format_exc())
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.stop()

# =========================================================
#   SIDEBAR
# =========================================================
with st.sidebar:
    if os.path.exists("potwell_logo_rgb_mv.jpg"):
        st.image("potwell_logo_rgb_mv.jpg")
    st.write("---")

    # Robust date range input (can return single date)
    min_date = df["pvm"].min().date()
    max_date = df["pvm"].max().date()
    date_value = st.date_input("Jakso", value=(min_date, max_date))
    if isinstance(date_value, (list, tuple)) and len(date_value) == 2:
        start_date, end_date = date_value
    else:
        start_date = end_date = date_value

    st.subheader("🏢 Kaupparyhmä")
    sel_group = st.selectbox("Valitse Ryhmä", ["Kaikki", "K-Ryhmä", "S-Ryhmä"])

    # Chains available (exclude Muu for clean UX)
    if sel_group == "Kaikki":
        chains_avail = sorted([c for c in df["Ketju"].unique() if c != "Muu"])
    else:
        chains_avail = sorted(df[df["Ketju"].isin(ALLOWED_CHAINS[sel_group])]["Ketju"].unique())

    sel_chain = st.selectbox("Valitse Ketju", ["Kaikki"] + chains_avail)

    # Filter for sidebar-dependent product/store lists
    df_sb = df.copy()
    if sel_group != "Kaikki":
        df_sb = df_sb[df_sb["Ketju"].isin(ALLOWED_CHAINS[sel_group])]
    if sel_chain != "Kaikki":
        df_sb = df_sb[df_sb["Ketju"] == sel_chain]

    all_p = sorted(df_sb["tuote"].dropna().unique())
    selected_products = st.multiselect("Tuotteet graafiin", all_p, default=[all_p[0]] if all_p else [])

    all_s = sorted(df_sb["kauppa"].dropna().unique())
    selected_stores_graph = st.multiselect("Kaupat graafiin", all_s, default=all_s)

    # OPTIONAL DEBUG (comment out when done)
    # st.write("DEBUG: Ketju counts")
    # st.dataframe(df["Ketju"].value_counts())
    # st.write("DEBUG: Muu stores (top 30)")
    # st.dataframe(df.loc[df["Ketju"]=="Muu","kauppa"].value_counts().head(30))

# =========================================================
#   MAIN DASHBOARD
# =========================================================
st.title("Hintaseuranta")

mask = (df["pvm"].dt.date >= start_date) & (df["pvm"].dt.date <= end_date)
df_filtered = df.loc[mask].copy()

# =========================================================
#   OSA 1: KPI & GRAAFI
# =========================================================
if not df_filtered.empty and selected_products and selected_stores_graph:
    graph_df = df_filtered[
        (df_filtered["tuote"].isin(selected_products)) &
        (df_filtered["kauppa"].isin(selected_stores_graph))
    ].copy()

    if not graph_df.empty:
        latest_date = graph_df["pvm"].max()
        latest_avg = graph_df.loc[graph_df["pvm"] == latest_date, "hinta"].mean()

        dates = sorted(graph_df["pvm"].unique())
        if len(dates) > 1:
            prev_date = dates[-2]
            prev_avg = graph_df.loc[graph_df["pvm"] == prev_date, "hinta"].mean()
            delta = latest_avg - prev_avg
        else:
            delta = 0

        k1, k2, k3 = st.columns(3)
        k1.metric("Keskihinta", f"{latest_avg:.2f} €", f"{delta:.2f} €", delta_color="inverse")
        k2.metric("Alin hinta", f"{graph_df['hinta'].min():.2f} €")
        k3.metric("Ylin hinta", f"{graph_df['hinta'].max():.2f} €")

        stats = (
            graph_df.groupby(["pvm", "tuote"])["hinta"]
            .agg(Keskiarvo="mean", Minimi="min", Maksimi="max")
            .reset_index()
        )
        melted = stats.melt(["pvm", "tuote"], var_name="Mittari", value_name="Hinta")

        chart = (
            alt.Chart(melted)
            .mark_line(strokeWidth=3)
            .encode(
                x=alt.X("pvm:T", axis=alt.Axis(format="%d.%m.", title=None)),
                y=alt.Y("Hinta:Q", title="Hinta (€)", scale=alt.Scale(zero=False)),
                color="tuote:N",
                strokeDash="Mittari:N",
            )
            + alt.Chart(melted)
            .mark_circle(size=80)
            .encode(
                x="pvm:T",
                y="Hinta:Q",
                color="tuote:N",
                shape="Mittari:N",
            )
        ).properties(height=400).interactive()

        st.altair_chart(chart, use_container_width=True)

st.write("---")

# =========================================================
#   OSA 2: HINTAMATRIISI (STRICT GROUP FILTER)
# =========================================================
st.subheader("📊 Hintamatriisi")

matrix_group = st.radio(
    "Valitse Ryhmä matriisiin:",
    ["K-Ryhmä", "S-Ryhmä"],
    horizontal=True,
    key="matrix_radio",
)

# STRICT: filter by allowed chains (prevents cross-group leakage)
m_df_raw = df[df["Ketju"].isin(ALLOWED_CHAINS[matrix_group])].copy()

if not m_df_raw.empty:
    m_dates = sorted(m_df_raw["pvm"].unique(), reverse=True)
    m_latest_date = m_dates[0]

    latest_m = (
        m_df_raw[m_df_raw["pvm"] == m_latest_date]
        .copy()
        .rename(columns={"hinta": "price_now"})
    )

    if len(m_dates) > 1:
        prev_m = (
            m_df_raw[m_df_raw["pvm"] == m_dates[1]][["kauppa", "tuote", "hinta"]]
            .rename(columns={"hinta": "price_prev"})
        )
        merged_m = pd.merge(latest_m, prev_m, on=["kauppa", "tuote"], how="left")
    else:
        merged_m = latest_m
        merged_m["price_prev"] = np.nan

    def format_m(row):
        p = row["price_now"]
        pr = row["price_prev"]
        if pd.isna(p):
            return None
        if pd.isna(pr):
            arr = ""
        else:
            arr = " ▲" if p > pr else " ▼" if p < pr else " ➖"
        return f"{p:.2f} €{arr}"

    merged_m["cell"] = merged_m.apply(format_m, axis=1)

    matrix = merged_m.pivot_table(
        index="tuote",
        columns=["Ketju", "kauppa"],
        values="cell",
        aggfunc="first",
    )

    matrix = matrix.dropna(how="all")
    matrix = matrix.dropna(axis=1, how="all")

    st.dataframe(
        matrix.style.map(
            lambda v: "color: #16a34a; font-weight: 700;" if "▲" in str(v)
            else "color: #dc2626; font-weight: 700;" if "▼" in str(v)
            else ""
        ),
        use_container_width=True,
        height=800
    )

if st.button("🔄 Päivitä"):
    st.rerun()

