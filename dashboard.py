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

# --- GLOBAL STYLES (Dark Theme Base) ---
st.markdown("""
    <style>
    .stApp {
        background: radial-gradient(circle at 50% 10%, rgb(25, 25, 30) 0%, rgb(5, 5, 5) 100%);
        color: #e0e0e0;
    }
    
    /* INPUT FIELDS STYLING */
    div[data-testid="stTextInput"] input {
        background-color: rgba(255, 255, 255, 0.05) !important;
        color: black !important;
        border: 1px solid rgba(255, 255, 255, 0.1) !important;
        border-radius: 8px !important;
        padding: 10px !important;
    }
    div[data-testid="stTextInput"] input:focus {
        border-color: #00d4ff !important;
        box-shadow: 0 0 10px rgba(0, 212, 255, 0.2) !important;
    }
    </style>
""", unsafe_allow_html=True)

# --- AUTHENTICATION LOGIC ---
def check_password():
    CORRECT_PASSWORD = "Potwell25!"

    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if "login_success_anim" not in st.session_state:
        st.session_state.login_success_anim = False

    if st.session_state.password_correct:
        return True

    # --- LOGIN SCREEN CSS (Only active when logged out) ---
    st.markdown("""
        <style>
        /* Hide Sidebar on Login */
        [data-testid="stSidebar"] { display: none; }
        
        /* CENTER THE LOGIN CARD */
        div.block-container {
            max-width: 500px;
            padding: 60px 40px;
            margin: auto;
            margin-top: 10vh;
            
            /* GLASS EFFECT */
            background: rgba(255, 255, 255, 0.03);
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 24px;
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.5);
        }
        
        /* Typography Alignment */
        h2 { text-align: center; font-weight: 300; letter-spacing: 2px; font-size: 28px; margin-bottom: 0px; }
        p { text-align: center; color: #666; font-size: 12px; margin-top: -10px; margin-bottom: 40px; }
        
        /* Button Styling */
        div.stButton > button {
            width: 100%;
            background-color: #00d4ff !important;
            color: #000 !important;
            border: none;
            font-weight: bold;
            letter-spacing: 1px;
            padding: 12px;
            transition: all 0.3s ease;
        }
        div.stButton > button:hover {
            box-shadow: 0 0 15px #00d4ff;
            transform: scale(1.02);
        }
        
        /* LOCK ANIMATION STYLES */
        .lock-container { position: relative; width: 60px; height: 60px; margin: 0 auto 30px auto; }
        .lock-body {
            width: 40px; height: 30px; background: #444; position: absolute; bottom: 0; left: 50%; 
            transform: translateX(-50%); border-radius: 4px; transition: background 0.5s ease;
        }
        .lock-shackle {
            width: 24px; height: 30px; border: 4px solid #444; border-bottom: 0; border-radius: 15px 15px 0 0;
            position: absolute; top: 2px; left: 50%; transform: translateX(-50%); 
            transition: transform 0.5s ease, border-color 0.5s ease; transform-origin: 100% 100%;
        }
        
        /* Unlocked State */
        .unlocked .lock-shackle { transform: translateX(-50%) rotateY(180deg) translateX(15px); border-color: #00d4ff; }
        .unlocked .lock-body { background: #00d4ff; box-shadow: 0 0 20px rgba(0, 212, 255, 0.6); }
        .success-msg { text-align: center; color: #00d4ff; font-family: monospace; letter-spacing: 2px; margin-top: 20px; }
        </style>
    """, unsafe_allow_html=True)

    # --- LOGIN CONTENT ---
    
    # 1. Title & Subtitle
    st.markdown("## POTWELL HINTASEURANTA")
    st.markdown("<p>Restricted Access Area</p>", unsafe_allow_html=True)

    # 2. Lock Animation Container
    lock_state = "unlocked" if st.session_state.login_success_anim else ""
    st.markdown(f"""
        <div class="lock-container {lock_state}">
            <div class="lock-shackle"></div>
            <div class="lock-body"></div>
        </div>
    """, unsafe_allow_html=True)

    # 3. Input & Interaction
    if not st.session_state.login_success_anim:
        # Create a placeholder to clear the form after success
        form_placeholder = st.empty()
        
        with form_placeholder.container():
            password = st.text_input("SYÖTÄ SALASANA", type="password", key="login_pass", label_visibility="collapsed", placeholder="SYÖTÄ SALASANA")
            
            if st.button("KIRJAUDU"):
                if password == CORRECT_PASSWORD:
                    st.session_state.login_success_anim = True
                    st.rerun()
                else:
                    st.error("VÄÄRÄ SALASANA")
    else:
        # 4. Success Message
        st.markdown('<div class="success-msg">SALASANA OIKEIN</div>', unsafe_allow_html=True)
        time.sleep(2)
        st.session_state.password_correct = True
        st.rerun()

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
        # TARKISTUS: Käytetäänkö paikallista tiedostoa vai Streamlit Cloudin salaisuuksia
        if os.path.exists("service_account.json"):
            creds = ServiceAccountCredentials.from_json_keyfile_name("service_account.json", scope)
        else:
            # Streamlit Cloud secrets
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
            
            # --- HINNAN KORJAUS ---
            # 1. Muutetaan kaikki merkkijonoiksi ja korvataan pilkut pisteillä
            df['hinta'] = df['hinta'].astype(str).str.replace(',', '.', regex=False)
            
            # 2. Muutetaan numeroiksi
            df['hinta'] = pd.to_numeric(df['hinta'], errors='coerce')
            
            # 3. ÄLYKÄS KORJAUS:
            # Jos hinta on yli 40€/kg (epärealistista perunalle/porkkanalle), 
            # oletetaan että desimaalipilkku on kadonnut ja jaetaan 100:lla.
            # Esim. 84.0 -> 0.84
            df.loc[df['hinta'] > 40, 'hinta'] = df['hinta'] / 100
            
        return df
    except Exception as e:
        return pd.DataFrame()

# --- DATA ---
df = load_data()

if df.empty:
    st.warning("Ei dataa tai yhteys Google Sheetsiin puuttuu. Tarkista 'service_account.json' tai pilven asetukset.")
    st.stop()

# --- SIVUPALKKI ---
with st.sidebar:
    if os.path.exists("potwell_logo_rgb_mv.jpg"):
        st.image("potwell_logo_rgb_mv.jpg")
    else:
        st.header("🥔 Valinnat")
    
    st.write("---")
    
    # 1. Aikaväli
    if not df['pvm'].isnull().all():
        min_date = df['pvm'].min().date()
        max_date = df['pvm'].max().date()
        
        st.subheader("📅 Aikaväli")
        start_date, end_date = st.date_input(
            "Valitse tarkastelujakso",
            [min_date, max_date],
            min_value=min_date,
            max_value=max_date
        )
        
        mask = (df['pvm'].dt.date >= start_date) & (df['pvm'].dt.date <= end_date)
        df_filtered_time = df[mask].copy()
    else:
        st.error("Päivämäärätiedot puuttuvat tai ovat virheellisiä.")
        st.stop()
    
    st.write("---")

    # 2. Tuotteet
    st.subheader("📦 Tuotteet")
    all_products = sorted(df['tuote'].unique())
    selected_products = st.multiselect(
        "Valitse analysoitavat tuotteet", 
        all_products, 
        default=[all_products[0]] if len(all_products) > 0 else []
    )
    
    # 3. Kaupat
    st.subheader("🏪 Kaupat (Graafi)")
    all_stores = sorted(df['kauppa'].unique())
    selected_stores_graph = st.multiselect(
        "Valitse kaupat graafiin",
        all_stores,
        default=all_stores 
    )

    st.caption(f"Versio 2.0 (Cloud) | Data: {max_date.strftime('%d.%m.%Y')}")

# --- PÄÄNÄKYMÄ ---

# Haetaan viimeisin päivitysaika suoraan datasta
try:
    last_update = df['pvm'].max()
    update_str = last_update.strftime('%d.%m.%Y')
except:
    update_str = "Ei tiedossa"

col1, col2 = st.columns([3, 1])
with col1:
    st.title("Hintaseuranta")
    st.markdown(f"🗓️ *Data päivitetty viimeksi: {update_str}*")
    st.markdown(f"**Markkinakatsaus ajalle:** {start_date.strftime('%d.%m.')} - {end_date.strftime('%d.%m.%Y')}")

# ==========================================
# OSA 1: KPI & GRAAFI
# ==========================================

if not df_filtered_time.empty and selected_products and selected_stores_graph:
    
    graph_df = df_filtered_time[
        (df_filtered_time['tuote'].isin(selected_products)) & 
        (df_filtered_time['kauppa'].isin(selected_stores_graph))
    ].copy()

    if not graph_df.empty:
        # KPI LASKENTA
        latest_avg = graph_df[graph_df['pvm'] == graph_df['pvm'].max()]['hinta'].mean()
        
        dates = sorted(graph_df['pvm'].unique())
        if len(dates) > 1:
            prev_date_graph = dates[-2]
            prev_avg = graph_df[graph_df['pvm'] == prev_date_graph]['hinta'].mean()
            delta = latest_avg - prev_avg
        else:
            delta = 0

        kpi1, kpi2, kpi3 = st.columns(3)
        with kpi1:
            st.metric("Keskihinta (Valitut)", f"{latest_avg:.2f} €", f"{delta:.2f} €", delta_color="inverse")
        with kpi2:
            min_price = graph_df['hinta'].min()
            st.metric("Jakson alin hinta", f"{min_price:.2f} €")
        with kpi3:
            max_price = graph_df['hinta'].max()
            st.metric("Jakson ylin hinta", f"{max_price:.2f} €")
        
        st.markdown("###")

        # GRAAFI
        stats_df = graph_df.groupby(['pvm', 'tuote'])['hinta'].agg(
            Keskiarvo='mean',
            Minimi='min',
            Maksimi='max'
        ).reset_index()

        melted_df = stats_df.melt(['pvm', 'tuote'], var_name='Mittari', value_name='Hinta')

        base = alt.Chart(melted_df).encode(
            x=alt.X('pvm:T', axis=alt.Axis(format='%d.%m.', title=None, grid=False, tickCount=10)),
            y=alt.Y('Hinta:Q', title='Hinta (€)', scale=alt.Scale(zero=False, padding=0.5), axis=alt.Axis(grid=True, gridDash=[2,2], gridColor='#eee')),
            color=alt.Color('tuote:N', title='Tuote'),
            tooltip=['pvm', 'tuote', 'Mittari', alt.Tooltip('Hinta', format='.2f')]
        )

        lines = base.mark_line(strokeWidth=3).encode(
            strokeDash=alt.StrokeDash('Mittari', legend=alt.Legend(title='Tieto'))
        )
        
        points = base.mark_circle(size=80, opacity=1, stroke='white', strokeWidth=1.5).encode(
            shape=alt.Shape('Mittari') 
        )

        chart = (lines + points).properties(
            height=400,
            title=alt.TitleParams("Hintakehitys", anchor='start', fontSize=18, color='#555')
        ).configure_view(
            strokeWidth=0
        ).interactive()

        with st.container():
            st.altair_chart(chart, use_container_width=True)

        with st.expander("📋 Tarkastele graafin dataa taulukkona"):
            display_stats = stats_df.copy()
            display_stats.columns = ['Päivämäärä', 'Tuote', 'Keskiarvo (€)', 'Minimi (€)', 'Maksimi (€)']
            
            st.dataframe(
                display_stats, 
                use_container_width=True,
                column_config={
                    "Päivämäärä": st.column_config.DateColumn("Päivämäärä", format="DD.MM.YYYY"),
                    "Keskiarvo (€)": st.column_config.NumberColumn(format="%.2f €"),
                    "Minimi (€)": st.column_config.NumberColumn(format="%.2f €"),
                    "Maksimi (€)": st.column_config.NumberColumn(format="%.2f €"),
                }
            )

    else:
        st.info("Valitse vasemmalta tuotteet ja kaupat nähdäksesi kuvaajan.")
else:
    st.info("Tarkista valinnat sivupalkista.")

st.write("---")

# ==========================================
# OSA 2: HINTAMATRIISI
# ==========================================

st.subheader("📊 Hintamatriisi")
st.caption("Taulukko on ryhmitelty kauppaketjun mukaan: K-Citymarket ➝ K-Supermarket ➝ K-Market.")

if df.empty:
    st.write("Ei dataa matriisille.")
else:
    # --- 1. DATAN VALMISTELU ---
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

    # --- 2. HINTASOLUJEN MUOTOILU ---
    def format_price_cell(row):
        price = row['price_now']
        prev = row['price_prev']
        if pd.isna(price): return None
        
        price_str = f"{price:.2f} €"
        
        arrow = ""
        if pd.notna(prev):
            if price > prev: arrow = " ▲"
            elif price < prev: arrow = " ▼"
            elif price == prev: arrow = " ➖"
            
        return f"{price_str}{arrow}"

    merged_df['formatted_cell'] = merged_df.apply(format_price_cell, axis=1)

    # --- 3. KAUPPOJEN RYHMITTELY (KETJUT) ---
    def detect_chain(store_name):
        # Logiikka: Jos nimessä on SM -> Supermarket, KM -> Market, muuten oletetaan Citymarket
        if "KM " in store_name: return "3. K-Market"
        if "SM " in store_name: return "2. K-Supermarket"
        # Oletus: Isot kaupat (esim. "Espoo (Iso Omena)") ovat Citymarketeja
        return "1. K-Citymarket"

    merged_df['Ketju'] = merged_df['kauppa'].apply(detect_chain)

    # --- 4. MATRIISIN LUONTI (MULTI-INDEX) ---
    # Luodaan matriisi, jossa sarakkeilla on kaksi tasoa: [Ketju, Kauppa]
    matrix_df = merged_df.pivot_table(
        index='tuote',
        columns=['Ketju', 'kauppa'],
        values='formatted_cell',
        aggfunc='first'
    )

    # --- 5. EAN-SARAKKEEN LISÄYS ---
    if 'ean' in df.columns:
        # Haetaan EANit
        ean_map = df[['tuote', 'ean']].drop_duplicates(subset=['tuote'], keep='last').set_index('tuote')
        
        # Jotta EAN sopii MultiIndex-taulukkoon, sille pitää antaa myös "yläotsikko"
        # Käytetään yläotsikkona " Tuotetiedot" (välilyönti alussa varmistaa että se on eka)
        ean_header = pd.MultiIndex.from_tuples([(" Tuotetiedot", "EAN")]) 
        ean_df = pd.DataFrame(ean_map['ean'], index=matrix_df.index)
        ean_df.columns = ean_header
        
        # Yhdistetään EAN + Matriisi
        final_df = pd.concat([ean_df, matrix_df], axis=1)
        
        # Siistitään NaN-arvot tyhjiksi stringeiksi EAN-sarakkeessa
        final_df[(" Tuotetiedot", "EAN")] = final_df[(" Tuotetiedot", "EAN")].fillna('')
    else:
        final_df = matrix_df

    # --- 6. VÄRITYSLOGIIKKA JA NÄYTTÖ ---
    def color_arrows(val):
        if isinstance(val, str):
            if "▲" in val:
                return "color: #28a745; font-weight: bold;"  # Vihreä
            elif "▼" in val:
                return "color: #dc3545; font-weight: bold;"  # Punainen
        return ""

    # Näytetään taulukko
    st.dataframe(
        final_df.style.map(color_arrows), 
        use_container_width=True, 
        height=800
    )

if st.button('🔄 Päivitä tiedot'):
    st.rerun()




