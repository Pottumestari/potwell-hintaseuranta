import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
import os
import time
import datetime
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
        div[data-testid="stTextInput"] input:focus {
            border-color: rgba(14, 165, 183, 0.9) !important;
            box-shadow: 0 0 10px rgba(14, 165, 183, 0.25) !important;
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
        h1, h2, h3, h4, h5, h6, p, div, span, label {
            color: #111827;
        }
        section[data-testid="stSidebar"] {
            background: rgba(255, 255, 255, 0.75);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            border-right: 1px solid rgba(17, 24, 39, 0.08);
        }
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
        div[data-testid="stDataFrame"] {
            background: rgba(255,255,255,0.85) !important;
            border-radius: 12px;
            padding: 6px;
            border: 1px solid rgba(17, 24, 39, 0.08);
        }
        div[data-testid="stAltairChart"] {
            background: rgba(255,255,255,0.85) !important;
            border-radius: 12px;
            padding: 12px;
            border: 1px solid rgba(17, 24, 39, 0.08);
        }
        </style>
    """, unsafe_allow_html=True)

# =========================================================
#   AUTHENTICATION LOGIC (Kept exactly as provided)
# =========================================================
def check_password():
    apply_login_css()
    CORRECT_PASSWORD = "Potwell25!"
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if "login_success_anim" not in st.session_state:
        st.session_state.login_success_anim = False
    if "login_error_anim" not in st.session_state:
        st.session_state.login_error_anim = False
    if st.session_state.password_correct:
        return True

    st.markdown("""
    <style>
    [data-testid="stSidebar"] { display: none; }
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
    h2 { text-align: center; font-weight: 600; letter-spacing: 2px; font-size: 28px; margin-bottom: 0px; color: #e5e7eb; }
    p  { text-align: center; color: #9ca3af; font-size: 12px; margin-top: -10px; margin-bottom: 40px; }
    div[data-testid="stForm"]{ max-width: 420px !important; margin: 0 auto !important; }
    div[data-testid="stForm"] div[data-testid="stTextInput"] input { color: #000000 !important; }
    div[data-testid="stFormSubmitButton"] > button {
        background: linear-gradient(135deg, #19b8d6 0%, #0ea5b7 60%, #0891b2 100%) !important;
    }
    .lock-container { position: relative; width: 60px; height: 60px; margin: 0 auto 30px auto; }
    .lock-body { width: 40px; height: 30px; background: #444; position: absolute; bottom: 0; left: 50%; transform: translateX(-50%); border-radius: 6px; }
    .lock-shackle { width: 24px; height: 30px; border: 4px solid #444; border-bottom: 0; border-radius: 15px 15px 0 0; position: absolute; top: 2px; left: 50%; transform: translateX(-50%); }
    .success .lock-shackle { transform: translateX(-50%) rotateY(180deg) translateX(15px); border-color: #22c55e; }
    .success .lock-body { background: #22c55e; }
    .error .lock-body { background: #ef4444; }
    @keyframes shake { 0%{transform:translateX(-50%) translateX(0)} 15%{transform:translateX(-50%) translateX(-6px)} 100%{transform:translateX(-50%) translateX(0)} }
    .shake { animation: shake 0.5s ease-in-out 1; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("## POTWELL HINTASEURANTA")
    st.markdown("<p>Restricted Access Area</p>", unsafe_allow_html=True)
    
    lock_class_str = ("success" if st.session_state.login_success_anim else "") + (" error shake" if st.session_state.login_error_anim else "")
    st.markdown(f'<div class="lock-container {lock_class_str}"><div class="lock-shackle"></div><div class="lock-body"></div></div>', unsafe_allow_html=True)

    if st.session_state.login_success_anim:
        time.sleep(0.8)
        st.session_state.password_correct = True
        st.session_state.login_success_anim = False
        st.rerun()

    with st.form("login_form"):
        password = st.text_input("SYÖTÄ SALASANA", type="password", label_visibility="collapsed", placeholder="SYÖTÄ SALASANA")
        if st.form_submit_button("KIRJAUDU"):
            if password == CORRECT_PASSWORD:
                st.session_state.login_success_anim = True
                st.rerun()
            else:
                st.session_state.login_error_anim = True
                st.rerun()
    
    if st.session_state.login_error_anim:
        time.sleep(0.6)
        st.session_state.login_error_anim = False
        st.rerun()
    return False

if not check_password():
    st.stop()

apply_dashboard_css()

# --- DATA LOADER ---
@st.cache_data(ttl=60)
def load_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
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
        if not df.empty:
            df['pvm'] = pd.to_datetime(df['pvm'])
            df['hinta'] = df['hinta'].astype(str).str.replace(',', '.', regex=False)
            df['hinta'] = pd.to_numeric(df['hinta'], errors='coerce')
            df.loc[df['hinta'] > 40, 'hinta'] = df['hinta'] / 100
            
            # Helper for Grouping
            def get_group(store):
                s = store.upper()
                return "K-Ryhmä" if any(x in s for x in ["KM ", "SM ", "CM ", "CITYMARKET", "K-MARKET", "K-SUPERMARKET"]) else "S-Ryhmä"
            
            def get_chain(store):
                s = store.upper()
                if "CM " in s or "CITYMARKET" in s: return "Citymarket"
                if "SM " in s or "K-SUPERMARKET" in s: return "K-Supermarket"
                if "KM " in s or "K-MARKET" in s: return "K-Market"
                if "PRISMA" in s: return "Prisma"
                if "S-MARKET" in s: return "S-Market"
                if "SALE" in s: return "Sale"
                return "Muu"

            df['Ryhmä'] = df['kauppa'].apply(get_group)
            df['Ketju'] = df['kauppa'].apply(get_chain)
        return df
    except Exception:
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.warning("Ei dataa. Tarkista yhteys.")
    st.stop()

# --- SIVUPALKKI ---
with st.sidebar:
    if os.path.exists("potwell_logo_rgb_mv.jpg"):
        st.image("potwell_logo_rgb_mv.jpg")
    else:
        st.header("🥔 Valinnat")
    st.write("---")

    # 1. Aikaväli
    min_date = df['pvm'].min().date()
    max_date = df['pvm'].max().date()
    st.subheader("📅 Aikaväli")
    start_date, end_date = st.date_input("Valitse tarkastelujakso", [min_date, max_date], min_value=min_date, max_value=max_date)
    mask = (df['pvm'].dt.date >= start_date) & (df['pvm'].dt.date <= end_date)
    df_filtered_time = df[mask].copy()
    st.write("---")

    # 2. RYHMÄ & KETJU SLICERS (New requirement)
    st.subheader("🏢 Kaupparyhmä")
    sel_group = st.selectbox("Valitse Ryhmä", ["Kaikki", "K-Ryhmä", "S-Ryhmä"])
    
    # Filter chains based on group
    if sel_group != "Kaikki":
        chains_avail = sorted(df[df['Ryhmä'] == sel_group]['Ketju'].unique())
    else:
        chains_avail = sorted(df['Ketju'].unique())
    sel_chain = st.selectbox("Valitse Ketju", ["Kaikki"] + chains_avail)

    # Filter data for next selections
    df_sidebar_filter = df_filtered_time.copy()
    if sel_group != "Kaikki":
        df_sidebar_filter = df_sidebar_filter[df_sidebar_filter['Ryhmä'] == sel_group]
    if sel_chain != "Kaikki":
        df_sidebar_filter = df_sidebar_filter[df_sidebar_filter['Ketju'] == sel_chain]

    # 3. Tuotteet (Affecting graphs)
    st.subheader("📦 Tuotteet")
    all_products = sorted(df_sidebar_filter['tuote'].unique())
    selected_products = st.multiselect("Valitse analysoitavat tuotteet", all_products, default=[all_products[0]] if all_products else [])

    # 4. Kaupat (Affecting graphs)
    st.subheader("🏪 Kaupat (Graafi)")
    all_stores = sorted(df_sidebar_filter['kauppa'].unique())
    selected_stores_graph = st.multiselect("Valitse kaupat graafiin", all_stores, default=all_stores)
    st.caption(f"Versio 2.0 (Cloud) | Data: {max_date.strftime('%d.%m.%Y')}")

# --- PÄÄNÄKYMÄ ---
update_str = df['pvm'].max().strftime('%d.%m.%Y')
col1, col2 = st.columns([3, 1])
with col1:
    st.title("Hintaseuranta")
    st.markdown(f"🗓️ *Data päivitetty viimeksi: {update_str}*")
    st.markdown(f"**Markkinakatsaus ajalle:** {start_date.strftime('%d.%m.')} - {end_date.strftime('%d.%m.%Y')}")

# --- OSA 1: KPI & GRAAFI (ORIGINAL LOGIC) ---
if not df_filtered_time.empty and selected_products and selected_stores_graph:
    graph_df = df_filtered_time[(df_filtered_time['tuote'].isin(selected_products)) & (df_filtered_time['kauppa'].isin(selected_stores_graph))].copy()
    if not graph_df.empty:
        latest_avg = graph_df[graph_df['pvm'] == graph_df['pvm'].max()]['hinta'].mean()
        dates = sorted(graph_df['pvm'].unique())
        delta = latest_avg - graph_df[graph_df['pvm'] == dates[-2]]['hinta'].mean() if len(dates) > 1 else 0

        kpi1, kpi2, kpi3 = st.columns(3)
        kpi1.metric("Keskihinta (Valitut)", f"{latest_avg:.2f} €", f"{delta:.2f} €", delta_color="inverse")
        kpi2.metric("Jakson alin hinta", f"{graph_df['hinta'].min():.2f} €")
        kpi3.metric("Jakson ylin hinta", f"{graph_df['hinta'].max():.2f} €")

        stats_df = graph_df.groupby(['pvm', 'tuote'])['hinta'].agg(Keskiarvo='mean', Minimi='min', Maksimi='max').reset_index()
        melted_df = stats_df.melt(['pvm', 'tuote'], var_name='Mittari', value_name='Hinta')

        chart = (alt.Chart(melted_df).encode(
            x=alt.X('pvm:T', axis=alt.Axis(format='%d.%m.', title=None, grid=False)),
            y=alt.Y('Hinta:Q', title='Hinta (€)', scale=alt.Scale(zero=False, padding=0.5)),
            color=alt.Color('tuote:N'),
            tooltip=['pvm', 'tuote', 'Mittari', alt.Tooltip('Hinta', format='.2f')]
        ).mark_line(strokeWidth=3).encode(strokeDash='Mittari') + alt.Chart(melted_df).mark_circle(size=80).encode(x='pvm:T', y='Hinta:Q', color='tuote:N', shape='Mittari')).properties(height=400, title="Hintakehitys").interactive()
        
        st.altair_chart(chart, use_container_width=True)
        with st.expander("📋 Tarkastele graafin dataa taulukkona"):
            st.dataframe(stats_df, use_container_width=True)
else:
    st.info("Valitse tuotteet ja kaupat sivupalkista.")

st.write("---")

# --- OSA 2: HINTAMATRIISI (With Slicer) ---
st.subheader("📊 Hintamatriisi")
matrix_sel = st.radio("Valitse Ryhmä matriisiin:", ["K-Ryhmä", "S-Ryhmä"], horizontal=True)

m_df = df[df['Ryhmä'] == matrix_sel].copy()
if not m_df.empty:
    sorted_dates = sorted(m_df['pvm'].unique(), reverse=True)
    latest_df = m_df[m_df['pvm'] == sorted_dates[0]].rename(columns={'hinta': 'price_now'})
    if len(sorted_dates) > 1:
        prev_df = m_df[m_df['pvm'] == sorted_dates[1]][['kauppa', 'tuote', 'hinta']].rename(columns={'hinta': 'price_prev'})
        merged_df = pd.merge(latest_df, prev_df, on=['kauppa', 'tuote'], how='left')
    else:
        merged_df = latest_df; merged_df['price_prev'] = np.nan

    def format_cell(row):
        p, prev = row['price_now'], row['price_prev']
        if pd.isna(p): return None
        arr = " ▲" if p > prev else " ▼" if p < prev else " ➖" if pd.notna(prev) else ""
        return f"{p:.2f} €{arr}"

    merged_df['formatted_cell'] = merged_df.apply(format_cell, axis=1)
    matrix = merged_df.pivot_table(index='tuote', columns=['Ketju', 'kauppa'], values='formatted_cell', aggfunc='first')
    
    st.dataframe(matrix.style.map(lambda v: "color: #16a34a; font-weight: 700;" if "▲" in str(v) else "color: #dc2626; font-weight: 700;" if "▼" in str(v) else ""), use_container_width=True, height=800)

if st.button('🔄 Päivitä tiedot'):
    st.rerun()
