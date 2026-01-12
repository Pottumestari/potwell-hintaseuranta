import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
import os
import time
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- CONFIGURATION ---
st.set_page_config(
    page_title="Potwell Hintaseuranta",
    page_icon="🥔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- GLOBAL STYLES & ANIMATIONS ---
st.markdown("""
    <style>
    /* 1. GLOBAL DARK THEME BACKGROUND */
    .stApp {
        background: radial-gradient(circle at 50% 10%, rgb(20, 20, 25) 0%, rgb(0, 0, 0) 100%);
        color: #e0e0e0;
    }

    /* 2. INPUT FIELD STYLING (Professional Dark) */
    div[data-testid="stTextInput"] input {
        background-color: rgba(255, 255, 255, 0.07) !important;
        color: white !important;
        border: 1px solid rgba(255, 255, 255, 0.15) !important;
        border-radius: 6px !important;
        padding: 12px !important;
        text-align: center; /* Center text input */
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: #666 !important;
        box-shadow: 0 0 10px rgba(255, 255, 255, 0.1) !important;
    }
    
    /* 3. BUTTON STYLING (Centered & Dark Theme) */
    div.stButton {
        text-align: center; /* Centers the button container */
        margin-top: 20px;
    }
    div.stButton > button {
        background-color: #1a1a1a !important; /* Dark Grey */
        color: #ddd !important;
        border: 1px solid #444 !important;
        padding: 10px 40px !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
        letter-spacing: 1px !important;
        transition: all 0.3s ease !important;
        margin: 0 auto !important; /* Force center */
        display: block !important;
    }
    div.stButton > button:hover {
        background-color: #333 !important;
        border-color: #888 !important;
        color: white !important;
        transform: scale(1.02);
    }

    /* 4. LOGIN CARD CONTAINER */
    .login-wrapper {
        max-width: 450px;
        margin: 10vh auto;
        padding: 50px;
        background: rgba(255, 255, 255, 0.02);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-radius: 20px;
        box-shadow: 0 20px 40px rgba(0,0,0,0.6);
        text-align: center;
    }
    
    /* 5. LOCK ANIMATIONS */
    @keyframes shake {
        0% { transform: translateX(0); }
        20% { transform: translateX(-10px); }
        40% { transform: translateX(10px); }
        60% { transform: translateX(-10px); }
        80% { transform: translateX(10px); }
        100% { transform: translateX(0); }
    }
    
    .lock-container {
        position: relative;
        width: 60px;
        height: 70px;
        margin: 0 auto 20px auto;
        transition: all 0.3s ease;
    }
    
    .lock-body {
        width: 44px;
        height: 35px;
        background: #555;
        position: absolute;
        bottom: 0;
        left: 50%;
        transform: translateX(-50%);
        border-radius: 4px;
        transition: background 0.3s;
    }
    
    .lock-shackle {
        width: 26px;
        height: 30px;
        border: 5px solid #555;
        border-bottom: 0;
        border-radius: 15px 15px 0 0;
        position: absolute;
        top: 0;
        left: 50%;
        transform: translateX(-50%);
        transition: border-color 0.3s;
    }

    /* ERROR STATE (RED & SHAKE) */
    .shake-anim {
        animation: shake 0.4s ease-in-out;
    }
    .error-lock .lock-body { background: #d32f2f !important; } /* Red Body */
    .error-lock .lock-shackle { border-color: #d32f2f !important; } /* Red Shackle */
    
    .error-text {
        color: #d32f2f;
        font-family: 'Segoe UI', sans-serif;
        font-size: 14px;
        font-weight: bold;
        letter-spacing: 1px;
        margin-bottom: 15px;
        margin-top: -10px;
        animation: fadeIn 0.5s;
    }

    /* SUCCESS STATE (GREEN/CYAN) */
    .success-lock .lock-body { background: #00e676 !important; }
    .success-lock .lock-shackle { border-color: #00e676 !important; }
    
    h2 { font-weight: 300; letter-spacing: 2px; font-size: 24px; margin-bottom: 5px; color: #fff; }
    p.subtitle { color: #666; font-size: 12px; margin-bottom: 30px; text-transform: uppercase; letter-spacing: 1px; }

    </style>
""", unsafe_allow_html=True)

# --- AUTHENTICATION LOGIC ---
def check_password():
    CORRECT_PASSWORD = "Potwell25!"

    # Initialize Session State
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if "login_failed" not in st.session_state:
        st.session_state.login_failed = False

    # If already logged in, skip everything
    if st.session_state.password_correct:
        return True

    # --- HIDE SIDEBAR DURING LOGIN ---
    st.markdown("""<style>[data-testid="stSidebar"] { display: none; }</style>""", unsafe_allow_html=True)

    # --- RENDER LOGIN UI ---
    
    # 1. Container Start
    st.markdown('<div class="login-wrapper">', unsafe_allow_html=True)
    st.markdown("<h2>POTWELL HINTASEURANTA</h2>", unsafe_allow_html=True)
    st.markdown('<p class="subtitle">Restricted Access Area</p>', unsafe_allow_html=True)

    # 2. Logic for Lock Visuals (Normal vs Error)
    lock_class = ""
    error_message_html = ""
    
    if st.session_state.login_failed:
        lock_class = "error-lock shake-anim"
        error_message_html = '<div class="error-text">VÄÄRÄ SALASANA</div>'

    # 3. Lock Icon HTML
    st.markdown(f"""
        <div class="lock-container {lock_class}">
            <div class="lock-shackle"></div>
            <div class="lock-body"></div>
        </div>
        {error_message_html}
    """, unsafe_allow_html=True)
    
    # 4. Input Form (Using standard Streamlit widgets styled via CSS)
    # Note: We use a placeholder to clear the form upon success
    
    password = st.text_input("SALASANA", type="password", label_visibility="collapsed", placeholder="Syötä salasana")
    
    if st.button("KIRJAUDU"):
        if password == CORRECT_PASSWORD:
            st.session_state.password_correct = True
            st.session_state.login_failed = False
            st.rerun()
        else:
            st.session_state.login_failed = True
            st.rerun()

    # 5. Container End
    st.markdown('</div>', unsafe_allow_html=True)

    return False

# --- STOP EXECUTION IF NOT LOGGED IN ---
if not check_password():
    st.stop()


# =========================================================
#   DASHBOARD CONTENT (STARTS HERE)
# =========================================================

# --- DATA LOADER ---
@st.cache_data(ttl=60)
def load_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
        # Check local vs cloud
        if os.path.exists("service_account.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
        else:
            if "gcp_service_account" in st.secrets:
                creds_dict = dict(st.secrets["gcp_service_account"])
                creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            else:
                return pd.DataFrame()
            
        client = gspread.authorize(creds)
        sheet = client.open("Potwell Data").sheet1 
        data = sheet.get_all_records()
        
        df = pd.DataFrame(data)
        if not df.empty:
            df['pvm'] = pd.to_datetime(df['pvm'])
            df['hinta'] = df['hinta'].astype(str).str.replace(',', '.', regex=False)
            df['hinta'] = pd.to_numeric(df['hinta'], errors='coerce')
            df.loc[df['hinta'] > 40, 'hinta'] = df['hinta'] / 100
            
        return df
    except Exception as e:
        return pd.DataFrame()

df = load_data()

if df.empty:
    st.warning("⚠️ Yhteys muodostettu, mutta dataa ei löytynyt. Tarkista Google Sheet.")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### 🎛 HALLINTAPANEELI")
    st.write("---")
    
    if not df['pvm'].isnull().all():
        min_date = df['pvm'].min().date()
        max_date = df['pvm'].max().date()
        
        start_date, end_date = st.date_input(
            "Aikaväli",
            [min_date, max_date],
            min_value=min_date,
            max_value=max_date
        )
        mask = (df['pvm'].dt.date >= start_date) & (df['pvm'].dt.date <= end_date)
        df_filtered_time = df[mask].copy()
    else:
        st.stop()
    
    st.write("---")
    
    all_products = sorted(df['tuote'].unique())
    selected_products = st.multiselect(
        "Suodata tuotteet", 
        all_products, 
        default=[all_products[0]] if len(all_products) > 0 else []
    )
    
    all_stores = sorted(df['kauppa'].unique())
    selected_stores_graph = st.multiselect(
        "Suodata kaupat",
        all_stores,
        default=all_stores 
    )

# --- MAIN DASHBOARD ---
try:
    last_update = df['pvm'].max().strftime('%d.%m.%Y')
except:
    last_update = "Ei tiedossa"

col1, col2 = st.columns([3, 1])
with col1:
    st.title("MARKKINAKATSAUS")
    st.caption(f"LIVE DATA | PÄIVITETTY: {last_update}")

# --- METRICS & CHART ---
if not df_filtered_time.empty and selected_products and selected_stores_graph:
    
    graph_df = df_filtered_time[
        (df_filtered_time['tuote'].isin(selected_products)) & 
        (df_filtered_time['kauppa'].isin(selected_stores_graph))
    ].copy()

    if not graph_df.empty:
        latest_avg = graph_df[graph_df['pvm'] == graph_df['pvm'].max()]['hinta'].mean()
        min_price = graph_df['hinta'].min()
        max_price = graph_df['hinta'].max()

        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1: st.metric("Keskihinta", f"{latest_avg:.2f} €")
        with kpi2: st.metric("Alin havaittu", f"{min_price:.2f} €")
        with kpi3: st.metric("Ylin havaittu", f"{max_price:.2f} €")
        
        st.markdown("###")

        # ALTAIR CHART
        stats_df = graph_df.groupby(['pvm', 'tuote'])['hinta'].mean().reset_index()

        base = alt.Chart(stats_df).encode(
            x=alt.X('pvm:T', axis=alt.Axis(format='%d.%m', title=None, domainColor='#444', tickColor='#444', labelColor='#aaa')),
            y=alt.Y('hinta:Q', title=None, axis=alt.Axis(gridColor='#333', domainColor='#444', labelColor='#aaa')),
            color=alt.Color('tuote:N', legend=alt.Legend(title=None, labelColor='#aaa')),
            tooltip=['pvm', 'tuote', 'hinta']
        )

        chart = base.mark_line(strokeWidth=3).properties(
            height=400,
            background='transparent'
        ).configure_view(
            strokeWidth=0
        ).interactive()

        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("Ei dataa valituilla ehdoilla.")

# --- MATRIX TABLE ---
st.subheader("HINTAMATRIISI")

if not df.empty:
    sorted_dates = sorted(df['pvm'].unique(), reverse=True)
    latest_date = sorted_dates[0]
    previous_date = sorted_dates[1] if len(sorted_dates) > 1 else None

    latest_df = df[df['pvm'] == latest_date].copy()
    latest_df = latest_df.rename(columns={'hinta': 'price_now'})

    if previous_date:
        prev_df = df[df['pvm'] == previous_date][['kauppa', 'tuote', 'hinta']].copy()
        prev_df = prev_df.rename(columns={'hinta': 'price_prev'})
        merged_df = pd.merge(latest_df, prev_df, on=['kauppa', 'tuote'], how='left')
    else:
        merged_df = latest_df
        merged_df['price_prev'] = np.nan

    def format_price_cell(row):
        price = row['price_now']
        prev = row['price_prev']
        if pd.isna(price): return None
        arrow = ""
        if pd.notna(prev):
            if price > prev: arrow = " ▲"
            elif price < prev: arrow = " ▼"
        return f"{price:.2f} €{arrow}"

    merged_df['formatted_cell'] = merged_df.apply(format_price_cell, axis=1)

    def detect_chain(s):
        if "KM " in s: return "K-Market"
        if "SM " in s: return "K-Supermarket"
        return "K-Citymarket"

    merged_df['Chain'] = merged_df['kauppa'].apply(detect_chain)

    matrix_df = merged_df.pivot_table(
        index='tuote',
        columns=['Chain', 'kauppa'],
        values='formatted_cell',
        aggfunc='first'
    )

    def style_matrix(val):
        if isinstance(val, str):
            if "▲" in val: return "color: #ff4b4b; font-weight: bold;" # Red
            if "▼" in val: return "color: #00e676; font-weight: bold;" # Green
        return "color: #ddd;"

    st.dataframe(matrix_df.style.map(style_matrix), use_container_width=True, height=600)

if st.button('PÄIVITÄ TIEDOT'):
    st.rerun()
