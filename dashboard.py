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
#   CSS: LOGIN (dark) vs DASHBOARD (light)  (ORIGINAL)
# =========================================================
def apply_login_css():
    st.markdown("""
        <style>
        .stApp {
            background: radial-gradient(circle at 50% 10%, rgb(25, 25, 30) 0%, rgb(5, 5, 5) 100%);
            color: #e0e0e0;
        }

        /* INPUT FIELDS STYLING (login) */
        div[data-testid="stTextInput"] input {
            background-color: rgba(255, 255, 255, 0.05) !important;
            color: #e0e0e0 !important;
            border: 1px solid rgba(255, 255, 255, 0.12) !important;
            border-radius: 10px !important;
            padding: 10px 12px !important;
        }
        div[data-testid="stTextInput"] input:focus {
            border-color: rgba(14, 165, 183, 0.9) !important;
            box-shadow: 0 0 10px rgba(14, 165, 183, 0.25) !important;
        }
        </style>
    """, unsafe_allow_html=True)


def apply_dashboard_css():
    st.markdown("""
        <style>
        /* Vaaleampi tausta vain dashboardille */
        .stApp {
            background: radial-gradient(circle at 50% 10%, rgb(245, 246, 250) 0%, rgb(232, 235, 242) 100%);
            color: #111827;
        }

        /* Yleinen typografia */
        h1, h2, h3, h4, h5, h6, p, div, span, label {
            color: #111827;
        }

        /* Sidebar vaaleaksi */
        section[data-testid="stSidebar"] {
            background: rgba(255, 255, 255, 0.75);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border-right: 1px solid rgba(17, 24, 39, 0.08);
        }

        /* Inputit dashboardilla */
        div[data-testid="stTextInput"] input,
        div[data-testid="stNumberInput"] input,
        div[data-testid="stDateInput"] input,
        div[data-testid="stMultiSelect"] div[role="combobox"],
        div[data-testid="stSelectbox"] div[role="combobox"] {
            background-color: rgba(255, 255, 255, 0.95) !important;
            color: #111827 !important;
            border: 1px solid rgba(17, 24, 39, 0.15) !important;
            border-radius: 8px !important;
        }

        /* Fokus */
        div[data-testid="stTextInput"] input:focus,
        div[data-testid="stNumberInput"] input:focus,
        div[data-testid="stDateInput"] input:focus {
            border-color: #00d4ff !important;
            box-shadow: 0 0 10px rgba(0, 212, 255, 0.15) !important;
        }

        /* Streamlit dataframet vaalealle paremmin */
        div[data-testid="stDataFrame"] {
            background: rgba(255,255,255,0.85) !important;
            border-radius: 12px;
            padding: 6px;
            border: 1px solid rgba(17, 24, 39, 0.08);
        }

        /* Altair/Chart container */
        div[data-testid="stAltairChart"] {
            background: rgba(255,255,255,0.85) !important;
            border-radius: 12px;
            padding: 12px;
            border: 1px solid rgba(17, 24, 39, 0.08);
        }
        </style>
    """, unsafe_allow_html=True)


# =========================================================
#   AUTHENTICATION LOGIC (ORIGINAL)
# =========================================================
def check_password():
    apply_login_css()

    CORRECT_PASSWORD = "Potwell25!"

    # Init session state
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if "login_success_anim" not in st.session_state:
        st.session_state.login_success_anim = False
    if "login_error_anim" not in st.session_state:
        st.session_state.login_error_anim = False

    # If already logged in, allow dashboard to render
    if st.session_state.password_correct:
        return True

    # --- LOGIN SCREEN CSS (Only active when logged out) ---
    st.markdown("""
    <style>
    /* Hide Sidebar on Login */
    [data-testid="stSidebar"] { display: none; }

    /* Card centered */
    div[data-testid="stAppViewContainer"] .main .block-container {
        max-width: 520px !important;
        padding: 60px 44px !important;
        margin: 10vh auto 0 auto !important;
        background: rgba(255, 255, 255, 0.03) !important;
        backdrop-filter: blur(20px);
        -webkit-backdrop-filter: blur(20px);
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 24px !important;
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5) !important;
    }

    /* Typography */
    h2 { text-align: center; font-weight: 600; letter-spacing: 2px; font-size: 28px; margin-bottom: 0px; color: #e5e7eb; }
    p  { text-align: center; color: #9ca3af; font-size: 12px; margin-top: -10px; margin-bottom: 40px; }

    /* Form width = input width */
    div[data-testid="stForm"]{
        max-width: 420px !important;
        margin: 0 auto !important;
    }

    /* Password field container */
    div[data-testid="stForm"] div[data-testid="stTextInput"] { width: 100% !important; }
    div[data-testid="stForm"] div[data-testid="stTextInput"] > div {
        border: 1px solid rgba(255,255,255,0.14) !important;
        border-radius: 12px !important;
        background: rgba(255,255,255,0.06) !important;
        padding: 2px !important;
    }

    /* Input itself */
    div[data-testid="stForm"] div[data-testid="stTextInput"] input {
        border: none !important;
        outline: none !important;
        background: transparent !important;
        color: #000000 !important;
        padding: 12px 12px !important;
    }
    div[data-testid="stForm"] div[data-testid="stTextInput"] input::placeholder {
        color: #6b7280 !important;
    }
    div[data-testid="stForm"] div[data-testid="stTextInput"]:focus-within > div {
        border-color: rgba(14, 165, 183, 0.9) !important;
        box-shadow: 0 0 12px rgba(14, 165, 183, 0.22) !important;
    }

    /* Hide Streamlit's form hint */
    div[data-testid="stTextInput"] [data-testid="InputInstructions"] { display: none !important; }
    div[data-testid="stTextInput"] [data-testid="stInputInstructions"] { display: none !important; }
    div[data-testid="stTextInput"] div[aria-live="polite"] { display: none !important; }

    /* Center submit button */
    div[data-testid="stFormSubmitButton"]{
        display: flex !important;
        justify-content: center !important;
        margin-top: 14px !important;
    }
    div[data-testid="stFormSubmitButton"] > button {
        width: auto !important;
        min-width: 180px !important;
        padding: 12px 22px !important;
        border-radius: 12px !important;
        border: none !important;
        font-weight: 800 !important;
        letter-spacing: 1px !important;
        background: linear-gradient(135deg, #19b8d6 0%, #0ea5b7 60%, #0891b2 100%) !important;
        color: #061018 !important;
        transition: transform 0.15s ease, box-shadow 0.15s ease !important;
    }
    div[data-testid="stFormSubmitButton"] > button:hover {
        box-shadow: 0 10px 25px rgba(14, 165, 183, 0.25) !important;
        transform: translateY(-1px) scale(1.01);
    }

    /* LOCK */
    .lock-container { position: relative; width: 60px; height: 60px; margin: 0 auto 30px auto; }
    .lock-body {
        width: 40px; height: 30px; background: #444; position: absolute; bottom: 0; left: 50%;
        transform: translateX(-50%); border-radius: 6px; transition: background 0.35s ease, box-shadow 0.35s ease;
    }
    .lock-shackle {
        width: 24px; height: 30px; border: 4px solid #444; border-bottom: 0; border-radius: 15px 15px 0 0;
        position: absolute; top: 2px; left: 50%; transform: translateX(-50%);
        transition: transform 0.45s ease, border-color 0.35s ease; transform-origin: 100% 100%;
    }

    /* Success (GREEN) */
    .success .lock-shackle { transform: translateX(-50%) rotateY(180deg) translateX(15px); border-color: #22c55e; }
    .success .lock-body { background: #22c55e; box-shadow: 0 0 22px rgba(34, 197, 94, 0.55); }

    /* Error (RED) */
    .error .lock-shackle { border-color: #ef4444; }
    .error .lock-body { background: #ef4444; box-shadow: 0 0 22px rgba(239, 68, 68, 0.45); }

    /* Shake animation */
    @keyframes shake {
      0%{transform:translateX(-50%) translateX(0)}
      15%{transform:translateX(-50%) translateX(-6px)}
      30%{transform:translateX(-50%) translateX(6px)}
      45%{transform:translateX(-50%) translateX(-5px)}
      60%{transform:translateX(-50%) translateX(5px)}
      75%{transform:translateX(-50%) translateX(-3px)}
      100%{transform:translateX(-50%) translateX(0)}
    }
    .shake { animation: shake 0.5s ease-in-out 1; }

    /* Status messages */
    .status-msg { text-align: center; font-family: monospace; letter-spacing: 2px; margin-top: 18px; font-size: 13px; }
    .status-success { color: #22c55e; }
    .status-error { color: #ef4444; }
    </style>
    """, unsafe_allow_html=True)

    # --- LOGIN CONTENT ---
    st.markdown("## POTWELL HINTASEURANTA")
    st.markdown("<p>Restricted Access Area</p>", unsafe_allow_html=True)

    # Lock classes based on state
    lock_classes = []
    if st.session_state.login_success_anim:
        lock_classes.append("success")
    if st.session_state.login_error_anim:
        lock_classes.append("error")
        lock_classes.append("shake")
    lock_class_str = " ".join(lock_classes)

    st.markdown(f"""
        <div class="lock-container {lock_class_str}">
            <div class="lock-shackle"></div>
            <div class="lock-body"></div>
        </div>
    """, unsafe_allow_html=True)

    # If success animation is active, show it briefly then enter dashboard
    if st.session_state.login_success_anim:
        st.markdown('<div class="status-msg status-success">SALASANA OIKEIN</div>', unsafe_allow_html=True)
        time.sleep(0.8)
        st.session_state.password_correct = True
        st.session_state.login_success_anim = False
        st.rerun()

    # Normal login form
    with st.form("login_form", clear_on_submit=False):
        password = st.text_input(
            "SYÖTÄ SALASANA",
            type="password",
            key="login_pass",
            label_visibility="collapsed",
            placeholder="SYÖTÄ SALASANA"
        )
        submitted = st.form_submit_button("KIRJAUDU")

    if submitted:
        if password == CORRECT_PASSWORD:
            st.session_state.login_error_anim = False
            st.session_state.login_success_anim = True
            st.rerun()
        else:
            st.session_state.login_success_anim = False
            st.session_state.login_error_anim = True
            st.rerun()

    # Wrong password message + reset so shake can re-trigger next time
    if st.session_state.login_error_anim:
        st.markdown('<div class="status-msg status-error">VÄÄRÄ SALASANA</div>', unsafe_allow_html=True)
        time.sleep(0.6)
        st.session_state.login_error_anim = False
        st.rerun()

    return False


if not check_password():
    st.stop()

apply_dashboard_css()

# =========================================================
#   STORE / CHAIN / GROUP MAPPING
#   Your convention:
#     SM = K-Supermarket
#     KM = K-Market
#   S-Group recognized only from explicit words (Prisma, S-Market, Sale, Alepa)
# =========================================================
def normalize_store_name(x: str) -> str:
    s = str(x).strip()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\(\s*", "(", s)
    s = re.sub(r"\s*\)", ")", s)
    return s

# Citymarkets in your data are plain location names (no "Citymarket" text)
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
S_CHAIN_ORDER = ["Prisma", "S-Market", "Sale", "Alepa"]

ALLOWED_CHAINS = {
    "K-Ryhmä": K_CHAIN_ORDER,
    "S-Ryhmä": S_CHAIN_ORDER,
}

def get_chain(store: str) -> str:
    n = normalize_store_name(store)
    u = n.upper()

    if n in CITYMARKET_OVERRIDES:
        return "Citymarket"

    # Your abbreviations (inside parentheses)
    if re.search(r"\(\s*SM\b", u):
        return "K-Supermarket"
    if re.search(r"\(\s*KM\b", u):
        return "K-Market"

    # If some names contain chain text
    if "CITYMARKET" in u or re.search(r"\(\s*CM\b", u):
        return "Citymarket"
    if "K-SUPERMARKET" in u or re.search(r"\bK[- ]?SUPERMARKET\b", u):
        return "K-Supermarket"
    if "K-MARKET" in u or re.search(r"\bK[- ]?MARKET\b", u):
        return "K-Market"

    # S-Group ONLY when explicitly written (prevents conflict with your SM=K-supermarket rule)
    if "PRISMA" in u:
        return "Prisma"
    if "ALEPA" in u:
        return "Alepa"
    if re.search(r"\bSALE\b", u):
        return "Sale"
    if "S-MARKET" in u or "SMARKET" in u or re.search(r"\bS[- ]?MARKET\b", u):
        return "S-Market"

    return "Muu"

def get_group(chain: str) -> str:
    if chain in K_CHAIN_ORDER:
        return "K-Ryhmä"
    if chain in S_CHAIN_ORDER:
        return "S-Ryhmä"
    return "Muu"

def reorder_matrix_columns(matrix: pd.DataFrame, chain_order: list[str]) -> pd.DataFrame:
    if matrix is None or matrix.empty:
        return matrix
    if not isinstance(matrix.columns, pd.MultiIndex) or matrix.columns.nlevels < 2:
        return matrix

    order_map = {c: i for i, c in enumerate(chain_order)}
    cols = list(matrix.columns)

    def sort_key(col):
        ketju = col[0]
        kauppa = col[1]
        return (order_map.get(ketju, 999), str(kauppa))

    return matrix.loc[:, sorted(cols, key=sort_key)]

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

        required_cols = {"pvm", "hinta", "kauppa", "tuote"}
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns in sheet: {missing}")

        # Normalize EAN column name (EAN/Ean/ean); if not present create empty
        ean_candidates = [c for c in df.columns if str(c).strip().lower() == "ean"]
        if ean_candidates:
            df = df.rename(columns={ean_candidates[0]: "ean"})
        else:
            df["ean"] = ""

        df["kauppa"] = df["kauppa"].apply(normalize_store_name)

        df["pvm"] = pd.to_datetime(df["pvm"], errors="coerce")
        df = df.dropna(subset=["pvm"])

        df["hinta"] = df["hinta"].astype(str).str.replace(",", ".", regex=False)
        df["hinta"] = pd.to_numeric(df["hinta"], errors="coerce")

        # If prices sometimes stored as cents
        df.loc[df["hinta"] > 40, "hinta"] = df["hinta"] / 100.0

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

    min_date = df["pvm"].min().date()
    max_date = df["pvm"].max().date()

    date_value = st.date_input("Jakso", value=(min_date, max_date))
    if isinstance(date_value, (list, tuple)) and len(date_value) == 2:
        start_date, end_date = date_value
    else:
        start_date = end_date = date_value

    st.subheader("🏢 Kaupparyhmä")
    sel_group = st.selectbox("Valitse Ryhmä", ["Kaikki", "K-Ryhmä", "S-Ryhmä"])

    # Chains available for selected group (exclude "Muu")
    if sel_group == "Kaikki":
        chains_avail = sorted([c for c in df["Ketju"].unique() if c != "Muu"])
    else:
        chains_avail = sorted(df[df["Ketju"].isin(ALLOWED_CHAINS[sel_group])]["Ketju"].unique())

    sel_chain = st.selectbox("Valitse Ketju", ["Kaikki"] + chains_avail)

    # Sidebar-driven filtering for product/store pickers
    df_sb = df.copy()
    if sel_group != "Kaikki":
        df_sb = df_sb[df_sb["Ketju"].isin(ALLOWED_CHAINS[sel_group])]
    if sel_chain != "Kaikki":
        df_sb = df_sb[df_sb["Ketju"] == sel_chain]

    all_p = sorted(df_sb["tuote"].dropna().unique())
    selected_products = st.multiselect("Tuotteet graafiin", all_p, default=[all_p[0]] if all_p else [])

    all_s = sorted(df_sb["kauppa"].dropna().unique())
    selected_stores_graph = st.multiselect("Kaupat graafiin", all_s, default=all_s)

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
#   OSA 2: HINTAMATRIISI (tuote + ean) + ORDERED CHAINS
# =========================================================
st.subheader("📊 Hintamatriisi")

matrix_group = st.radio(
    "Valitse Ryhmä matriisiin:",
    ["K-Ryhmä", "S-Ryhmä"],
    horizontal=True,
    key="matrix_radio",
)

# STRICT: prevent leakage by filtering by allowed chains
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
            m_df_raw[m_df_raw["pvm"] == m_dates[1]][["kauppa", "tuote", "ean", "hinta"]]
            .rename(columns={"hinta": "price_prev"})
        )
        merged_m = pd.merge(latest_m, prev_m, on=["kauppa", "tuote", "ean"], how="left")
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

    # Pivot: tuote + ean on rows, columns are (Ketju, kauppa)
    matrix = merged_m.pivot_table(
        index=["tuote", "ean"],
        columns=["Ketju", "kauppa"],
        values="cell",
        aggfunc="first",
    )

    # Clean up
    matrix = matrix.dropna(how="all")
    matrix = matrix.dropna(axis=1, how="all")

    # Order chains in columns (K: Citymarket -> K-Supermarket -> K-Market)
    matrix = reorder_matrix_columns(matrix, chain_order=ALLOWED_CHAINS[matrix_group])

    # Show EAN as normal column right after tuote
    matrix = matrix.reset_index()

    price_cols = [c for c in matrix.columns if c not in ["tuote", "ean"]]

    st.dataframe(
        matrix.style.map(
            lambda v: "color: #16a34a; font-weight: 700;" if "▲" in str(v)
            else "color: #dc2626; font-weight: 700;" if "▼" in str(v)
            else "",
            subset=price_cols
        ),
        use_container_width=True,
        height=800
    )

if st.button("🔄 Päivitä"):
    st.rerun()
