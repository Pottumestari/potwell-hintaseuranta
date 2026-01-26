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
            
            def get_chain(store):
                s = str(store).upper()
                if any(x in s for x in ["CM ", "CITYMARKET"]): return "Citymarket"
                if any(x in s for x in ["SM ", "K-SUPERMARKET"]): return "K-Supermarket"
                if any(x in s for x in ["KM ", "K-MARKET"]): return "K-Market"
                if "PRISMA" in s: return "Prisma"
                if "S-MARKET" in s: return "S-Market"
                if "SALE" in s: return "Sale"
                return "Citymarket"

            def get_group(chain):
                if chain in ["Citymarket", "K-Supermarket", "K-Market"]:
                    return "K-Ryhmä"
                return "S-Ryhmä"

            df['Ketju'] = df['kauppa'].apply(get_chain)
            df['Ryhmä'] = df['Ketju'].apply(get_group)
            
        return df
    except Exception:
        return pd.DataFrame()

df = load_data()
if df.empty:
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    if os.path.exists("potwell_logo_rgb_mv.jpg"):
        st.image("potwell_logo_rgb_mv.jpg")
    st.write("---")
    min_date, max_date = df['pvm'].min().date(), df['pvm'].max().date()
    start_date, end_date = st.date_input("Jakso", [min_date, max_date])
    
    st.subheader("🏢 Kaupparyhmä")
    sel_group = st.selectbox("Valitse Ryhmä", ["Kaikki", "K-Ryhmä", "S-Ryhmä"])
    chains_avail = sorted(df[df['Ryhmä'] == sel_group]['Ketju'].unique()) if sel_group != "Kaikki" else sorted(df['Ketju'].unique())
    sel_chain = st.selectbox("Valitse Ketju", ["Kaikki"] + chains_avail)

    df_sb = df.copy()
    if sel_group != "Kaikki": df_sb = df_sb[df_sb['Ryhmä'] == sel_group]
    if sel_chain != "Kaikki": df_sb = df_sb[df_sb['Ketju'] == sel_chain]

    all_p = sorted(df_sb['tuote'].unique())
    selected_products = st.multiselect("Tuotteet graafiin", all_p, default=[all_p[0]] if all_p else [])
    
    all_s = sorted(df_sb['kauppa'].unique())
    selected_stores_graph = st.multiselect("Kaupat graafiin", all_s, default=all_s)

# --- MAIN DASHBOARD ---
st.title("Hintaseuranta")
mask = (df['pvm'].dt.date >= start_date) & (df['pvm'].dt.date <= end_date)
df_filtered = df[mask].copy()

# --- OSA 1: KPI & GRAAFI ---
if not df_filtered.empty and selected_products and selected_stores_graph:
    graph_df = df_filtered[(df_filtered['tuote'].isin(selected_products)) & (df_filtered['kauppa'].isin(selected_stores_graph))].copy()
    if not graph_df.empty:
        latest_avg = graph_df[graph_df['pvm'] == graph_df['pvm'].max()]['hinta'].mean()
        dates = sorted(graph_df['pvm'].unique())
        delta = latest_avg - graph_df[graph_df['pvm'] == dates[-2]]['hinta'].mean() if len(dates) > 1 else 0

        k1, k2, k3 = st.columns(3)
        k1.metric("Keskihinta", f"{latest_avg:.2f} €", f"{delta:.2f} €", delta_color="inverse")
        k2.metric("Alin hinta", f"{graph_df['hinta'].min():.2f} €")
        k3.metric("Ylin hinta", f"{graph_df['hinta'].max():.2f} €")

        stats = graph_df.groupby(['pvm', 'tuote'])['hinta'].agg(Keskiarvo='mean', Minimi='min', Maksimi='max').reset_index()
        melted = stats.melt(['pvm', 'tuote'], var_name='Mittari', value_name='Hinta')

        chart = (alt.Chart(melted).encode(
            x=alt.X('pvm:T', axis=alt.Axis(format='%d.%m.', title=None)),
            y=alt.Y('Hinta:Q', title='Hinta (€)', scale=alt.Scale(zero=False)),
            color='tuote:N',
            strokeDash='Mittari'
        ).mark_line(strokeWidth=3).encode(strokeDash='Mittari') + alt.Chart(melted).mark_circle(size=80).encode(x='pvm:T', y='Hinta:Q', color='tuote:N', shape='Mittari')).properties(height=400).interactive()
        st.altair_chart(chart, use_container_width=True)

st.write("---")

# --- OSA 2: HINTAMATRIISI (FULL FIX) ---
st.subheader("📊 Hintamatriisi")
matrix_group = st.radio("Valitse Ryhmä matriisiin:", ["K-Ryhmä", "S-Ryhmä"], horizontal=True, key="matrix_radio")

# CRITICAL FIX: We filter the data BEFORE creating the latest/previous dataframes
# This ensures that products from the other group are completely excluded.
m_df_raw = df[df['Ryhmä'] == matrix_group].copy()

if not m_df_raw.empty:
    m_dates = sorted(m_df_raw['pvm'].unique(), reverse=True)
    m_latest_date = m_dates[0]
    
    # Only products and stores from the selected group are pulled here
    latest_m = m_df_raw[m_df_raw['pvm'] == m_latest_date].copy().rename(columns={'hinta': 'price_now'})
    
    if len(m_dates) > 1:
        prev_m = m_df_raw[m_df_raw['pvm'] == m_dates[1]][['kauppa', 'tuote', 'hinta']].rename(columns={'hinta': 'price_prev'})
        merged_m = pd.merge(latest_m, prev_m, on=['kauppa', 'tuote'], how='left')
    else:
        merged_m = latest_m; merged_m['price_prev'] = np.nan

    def format_m(row):
        p, pr = row['price_now'], row['price_prev']
        if pd.isna(p): return None
        arr = " ▲" if p > pr else " ▼" if p < pr else " ➖" if pd.notna(pr) else ""
        return f"{p:.2f} €{arr}"

    merged_m['cell'] = merged_m.apply(format_m, axis=1)
    
    # Pivot logic
    matrix = merged_m.pivot_table(index='tuote', columns=['Ketju', 'kauppa'], values='cell', aggfunc='first')
    
    # Final cleanup: drop rows that have no data for the visible columns
    matrix = matrix.dropna(how='all')

    st.dataframe(
        matrix.style.map(lambda v: "color: #16a34a; font-weight: 700;" if "▲" in str(v) 
                         else "color: #dc2626; font-weight: 700;" if "▼" in str(v) else ""), 
        use_container_width=True, height=800
    )

if st.button('🔄 Päivitä'): st.rerun()
