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
    page_title="Potwell Intelligence",
    page_icon="🥔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- MODERN DARK THEME & ANIMATION CSS ---
st.markdown("""
    <style>
    /* GLOBAL DARK THEME */
    .stApp {
        background: radial-gradient(circle at 10% 20%, rgb(30, 30, 35) 0%, rgb(10, 10, 15) 90%);
        color: #e0e0e0;
    }
    
    /* LOGIN CARD CONTAINER */
    .login-container {
        display: flex;
        justify-content: center;
        align-items: center;
        height: 70vh;
        flex-direction: column;
    }
    
    .glass-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(15px);
        -webkit-backdrop-filter: blur(15px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        padding: 50px;
        border-radius: 20px;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        width: 100%;
        max-width: 450px;
        text-align: center;
    }

    /* INPUT FIELDS */
    div[data-testid="stTextInput"] input {
        background-color: rgba(255, 255, 255, 0.07) !important;
        color: white !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        border-radius: 8px !important;
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: #00d4ff !important;
        box-shadow: 0 0 10px rgba(0, 212, 255, 0.3) !important;
    }
    div[data-testid="stTextInput"] label {
        color: #aaaaaa !important;
    }

    /* METRICS & CARDS IN DASHBOARD */
    div[data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: white;
    }
    div[data-testid="stMetricLabel"] {
        color: #bbbbbb !important;
    }
    
    /* ANIMATION: LOCK OPENING */
    .lock-container {
        position: relative;
        width: 80px;
        height: 80px;
        margin: 0 auto 20px auto;
    }
    
    .lock-body {
        width: 50px;
        height: 40px;
        background: #e0e0e0;
        position: absolute;
        bottom: 0;
        left: 50%;
        transform: translateX(-50%);
        border-radius: 5px;
        transition: background 0.5s ease;
    }
    
    .lock-shackle {
        width: 30px;
        height: 40px;
        border: 5px solid #e0e0e0;
        border-bottom: 0;
        border-radius: 15px 15px 0 0;
        position: absolute;
        top: 5px;
        left: 50%;
        transform: translateX(-50%);
        transition: transform 0.5s ease, border-color 0.5s ease;
        transform-origin: 100% 100%;
    }
    
    /* SUCCESS STATE */
    .unlocked .lock-shackle {
        transform: translateX(-50%) rotateY(180deg) translateX(15px);
        border-color: #00d4ff;
    }
    .unlocked .lock-body {
        background: #00d4ff;
        box-shadow: 0 0 20px rgba(0, 212, 255, 0.6);
    }
    
    .success-text {
        color: #00d4ff;
        font-family: 'Courier New', monospace;
        letter-spacing: 2px;
        margin-top: 15px;
        font-size: 1.2rem;
        opacity: 0;
        animation: fadeIn 0.5s forwards 0.5s;
    }

    @keyframes fadeIn {
        to { opacity: 1; }
    }
    </style>
""", unsafe_allow_html=True)

# --- AUTHENTICATION WITH NEW ANIMATION ---
def check_password():
    CORRECT_PASSWORD = "Potwell25!"

    # Initialize Session State
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if "login_success_anim" not in st.session_state:
        st.session_state.login_success_anim = False

    # If already logged in, return True
    if st.session_state.password_correct:
        return True

    # CONTAINER FOR LOGIN UI
    placeholder = st.empty()

    with placeholder.container():
        st.markdown('<div class="login-container"><div class="glass-card">', unsafe_allow_html=True)
        
        st.markdown("## POTWELL INTELLIGENCE")
        st.markdown("<p style='color: #888; font-size: 0.9rem;'>Restricted Access Area</p>", unsafe_allow_html=True)
        
        # Determine visual state (Locked vs Unlocked)
        lock_class = "unlocked" if st.session_state.login_success_anim else ""
        
        # HTML for Lock Animation
        st.markdown(f"""
            <div class="lock-container {lock_class}">
                <div class="lock-shackle"></div>
                <div class="lock-body"></div>
            </div>
        """, unsafe_allow_html=True)

        # Show Login Form if not yet successful
        if not st.session_state.login_success_anim:
            password = st.text_input("ENTER PASSKEY", type="password", key="login_pass")
            
            if st.button("AUTHENTICATE"):
                if password == CORRECT_PASSWORD:
                    st.session_state.login_success_anim = True
                    st.rerun()  # Rerun to trigger animation state
                else:
                    st.error("ACCESS DENIED")
        else:
            # Success State Display
            st.markdown('<div class="success-text">ACCESS GRANTED</div>', unsafe_allow_html=True)
            st.markdown('</div></div>', unsafe_allow_html=True) # Close divs
            time.sleep(2.5) # Wait for animation
            st.session_state.password_correct = True
            st.rerun()

        st.markdown('</div></div>', unsafe_allow_html=True) # Close divs if loop didn't break

    return False

if not check_password():
    st.stop()

# =========================================================
#   DASHBOARD CONTENT (Only runs after login)
# =========================================================

# --- DATA LOADER ---
@st.cache_data(ttl=60)
def load_data():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    try:
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
    st.warning("⚠️ Connection established, but data stream is empty. Check source.")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### 🎛 CONTROL PANEL")
    st.write("---")
    
    if not df['pvm'].isnull().all():
        min_date = df['pvm'].min().date()
        max_date = df['pvm'].max().date()
        
        start_date, end_date = st.date_input(
            "Time Horizon",
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
        "Product Filter", 
        all_products, 
        default=[all_products[0]] if len(all_products) > 0 else []
    )
    
    all_stores = sorted(df['kauppa'].unique())
    selected_stores_graph = st.multiselect(
        "Store Filter",
        all_stores,
        default=all_stores 
    )

# --- MAIN DASHBOARD ---
try:
    last_update = df['pvm'].max().strftime('%d.%m.%Y')
except:
    last_update = "N/A"

col1, col2 = st.columns([3, 1])
with col1:
    st.title("MARKET INTELLIGENCE")
    st.caption(f"LIVE DATA STREAM | UPDATED: {last_update}")

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
        with kpi1: st.metric("Average Price", f"{latest_avg:.2f} €")
        with kpi2: st.metric("Lowest Detected", f"{min_price:.2f} €")
        with kpi3: st.metric("Highest Detected", f"{max_price:.2f} €")
        
        st.markdown("###")

        # ALTAIR CHART (Dark Mode Optimized)
        stats_df = graph_df.groupby(['pvm', 'tuote'])['hinta'].mean().reset_index()

        base = alt.Chart(stats_df).encode(
            x=alt.X('pvm:T', axis=alt.Axis(format='%d.%m', title=None, domainColor='#444', tickColor='#444', labelColor='#aaa')),
            y=alt.Y('hinta:Q', title=None, axis=alt.Axis(gridColor='#333', domainColor='#444', labelColor='#aaa')),
            color=alt.Color('tuote:N', legend=alt.Legend(title=None, labelColor='#aaa')),
            tooltip=['pvm', 'tuote', 'hinta']
        )

        chart = base.mark_line(strokeWidth=3).properties(
            height=400,
            background='transparent' # Allows global dark theme to show through
        ).configure_view(
            strokeWidth=0
        ).interactive()

        st.altair_chart(chart, use_container_width=True)
    else:
        st.info("No data for selected criteria.")

# --- MATRIX TABLE ---
st.subheader("PRICE MATRIX")

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

    # Simplified Chain Logic for display
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

    # Styling for Dark Mode
    def style_matrix(val):
        if isinstance(val, str):
            if "▲" in val: return "color: #ff4b4b; font-weight: bold;" # Red for increase
            if "▼" in val: return "color: #00d4ff; font-weight: bold;" # Cyan for decrease
        return "color: #ddd;"

    st.dataframe(matrix_df.style.map(style_matrix), use_container_width=True, height=600)

if st.button('REFRESH DATA'):
    st.rerun()
