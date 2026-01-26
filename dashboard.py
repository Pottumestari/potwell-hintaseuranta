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

# [CSS Functions apply_login_css and apply_dashboard_css remain unchanged as per your file]
# ... (omitted for brevity, keep your original CSS functions here)

# [Authentication Logic check_password remains unchanged]
# ... (omitted for brevity, keep your original check_password function here)

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
        }
        </style>
    """, unsafe_allow_html=True)

def check_password():
    # (Your original password logic)
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if st.session_state.password_correct:
        return True
    
    # Placeholder for simplicity in this snippet - use your full original block here
    st.session_state.password_correct = True 
    return True

if not check_password():
    st.stop()

apply_dashboard_css()

# --- HELPER FUNCTIONS FOR FILTERING ---
def get_group(store_name):
    store_upper = store_name.upper()
    if any(x in store_upper for x in ["KM ", "SM ", "CM ", "CITYMARKET", "K-MARKET", "K-SUPERMARKET"]):
        return "K-Ryhmä"
    return "S-Ryhmä"

def get_chain(store_name):
    store_upper = store_name.upper()
    if "CM " in store_upper or "CITYMARKET" in store_upper: return "Citymarket"
    if "SM " in store_upper or "K-SUPERMARKET" in store_upper: return "K-Supermarket"
    if "KM " in store_upper or "K-MARKET" in store_upper: return "K-Market"
    if "PRISMA" in store_upper: return "Prisma"
    if "S-MARKET" in store_upper: return "S-Market"
    if "SALE" in store_upper: return "Sale"
    return "Muu"

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
            
            # Add helper columns for grouping
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
    
    st.write("---")
    
    # 1. Aikaväli
    st.subheader("📅 Aikaväli")
    min_date = df['pvm'].min().date()
    max_date = df['pvm'].max().date()
    start_date, end_date = st.date_input("Valitse jakso", [min_date, max_date])

    st.write("---")

    # 2. RYHMÄ & KETJU SLICERS (The new requested additions)
    st.subheader("🏢 Kaupparyhmä")
    selected_group = st.selectbox("Valitse Ryhmä", ["Kaikki", "K-Ryhmä", "S-Ryhmä"])
    
    # Filter available chains based on group
    if selected_group != "Kaikki":
        available_chains = sorted(df[df['Ryhmä'] == selected_group]['Ketju'].unique())
    else:
        available_chains = sorted(df['Ketju'].unique())
    
    selected_chain = st.selectbox("Valitse Ketju", ["Kaikki"] + available_chains)

    # 3. Apply these filters to Tuotteet and Kaupat selections
    filtered_df_sidebar = df.copy()
    if selected_group != "Kaikki":
        filtered_df_sidebar = filtered_df_sidebar[filtered_df_sidebar['Ryhmä'] == selected_group]
    if selected_chain != "Kaikki":
        filtered_df_sidebar = filtered_df_sidebar[filtered_df_sidebar['Ketju'] == selected_chain]

    st.subheader("📦 Tuotteet")
    all_products = sorted(filtered_df_sidebar['tuote'].unique())
    selected_products = st.multiselect("Valitse tuotteet", all_products, default=all_products[:2] if all_products else [])

    st.subheader("🏪 Kaupat (Graafi)")
    all_stores = sorted(filtered_df_sidebar['kauppa'].unique())
    selected_stores_graph = st.multiselect("Valitse kaupat", all_stores, default=all_stores)

# --- PÄÄNÄKYMÄ ---
st.title("Hintaseuranta")
mask = (df['pvm'].dt.date >= start_date) & (df['pvm'].dt.date <= end_date)
df_filtered_time = df[mask].copy()

# [KPI & Graph Logic remains largely the same, using filtered_df_sidebar selections]
if not df_filtered_time.empty and selected_products and selected_stores_graph:
    graph_df = df_filtered_time[
        (df_filtered_time['tuote'].isin(selected_products)) &
        (df_filtered_time['kauppa'].isin(selected_stores_graph))
    ].copy()
    
    if not graph_df.empty:
        # (Metric calculations and Altair Chart code from your original dashboard.py)
        # ... 
        st.write("### Hintakehitys")
        # [Insert your original chart rendering here]

st.write("---")

# ==========================================
# OSA 2: HINTAMATRIISI (With new Slicer)
# ==========================================
st.subheader("📊 Hintamatriisi")

# New slicer specifically for the matrix
matrix_group_filter = st.radio(
    "Näytä matriisissa:", 
    ["K-Ryhmä", "S-Ryhmä"], 
    horizontal=True
)

matrix_df_base = df[df['Ryhmä'] == matrix_group_filter].copy()

if matrix_df_base.empty:
    st.info(f"Ei dataa ryhmälle {matrix_group_filter}")
else:
    sorted_dates = sorted(matrix_df_base['pvm'].unique(), reverse=True)
    latest_date = sorted_dates[0]
    previous_date = sorted_dates[1] if len(sorted_dates) > 1 else None

    latest_df = matrix_df_base[matrix_df_base['pvm'] == latest_date].copy()
    latest_df = latest_df.rename(columns={'hinta': 'price_now'})

    if previous_date is not None:
        prev_df = matrix_df_base[matrix_df_base['pvm'] == previous_date][['kauppa', 'tuote', 'hinta']].copy()
        prev_df = prev_df.rename(columns={'hinta': 'price_prev'})
        merged_df = pd.merge(latest_df, prev_df, on=['kauppa', 'tuote'], how='left')
    else:
        merged_df = latest_df
        merged_df['price_prev'] = np.nan

    # Cell formatting function (Same as yours)
    def format_price_cell(row):
        price = row['price_now']
        prev = row['price_prev']
        if pd.isna(price): return None
        price_str = f"{price:.2f} €"
        if pd.notna(prev):
            if price > prev: arrow = " ▲"
            elif price < prev: arrow = " ▼"
            else: arrow = " ➖"
            return f"{price_str}{arrow}"
        return price_str

    merged_df['formatted_cell'] = merged_df.apply(format_price_cell, axis=1)

    # Use the existing Ketju logic for grouping in the matrix
    matrix_table = merged_df.pivot_table(
        index='tuote',
        columns=['Ketju', 'kauppa'],
        values='formatted_cell',
        aggfunc='first'
    )

    st.dataframe(
        matrix_table.style.map(lambda val: "color: #16a34a; font-weight: 700;" if "▲" in str(val) 
                               else "color: #dc2626; font-weight: 700;" if "▼" in str(val) else ""),
        use_container_width=True,
        height=600
    )

if st.button('🔄 Päivitä tiedot'):
    st.rerun()
