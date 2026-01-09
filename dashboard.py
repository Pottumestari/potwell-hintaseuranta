import streamlit as st
import pandas as pd
import altair as alt
import numpy as np
import os
import time
import datetime
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- ASETUKSET ---
st.set_page_config(
    page_title="Potwell Hintaseuranta",
    page_icon="🥔",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- MUKAUTETTU CSS (MODERNI ILME) ---
st.markdown("""
    <style>
    .stApp {
        background-color: #f8f9fa;
    }
    h1, h2, h3 {
        color: #2c3e50;
        font-family: 'Segoe UI', sans-serif;
    }
    div[data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
        border: 1px solid #e0e0e0;
    }
    .streamlit-expanderHeader {
        background-color: white;
        border-radius: 5px;
    }
    .block-container {
        padding-top: 2rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- TURVALLISUUS ---
def check_password():
    CORRECT_PASSWORD = "Potwell25!"

    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    def password_entered():
        if st.session_state["password_input"] == CORRECT_PASSWORD:
            st.session_state.password_correct = True
            st.session_state.intro_shown = False 
            del st.session_state["password_input"]
        else:
            st.session_state.password_correct = False
            st.error("Väärä salasana")

    if not st.session_state.password_correct:
        st.markdown("### 🔒 Kirjaudu sisään")
        st.text_input("Salasana:", type="password", on_change=password_entered, key="password_input")
        return False
    return True

if not check_password():
    st.stop()

# --- MR. POTWELL ANIMAATIO ---
if "intro_shown" not in st.session_state:
    st.session_state.intro_shown = False

if not st.session_state.intro_shown:
    placeholder = st.empty()
    
    mr_potato_html = """
    <style>
        @keyframes jumpUp {
            0% { bottom: -500px; transform: translateX(-50%) scale(0.8); }
            20% { bottom: 20px; transform: translateX(-50%) scale(1.1); }
            30% { bottom: -10px; transform: translateX(-50%) scale(0.95); }
            40% { bottom: 0px; transform: translateX(-50%) scale(1); }
            80% { bottom: 0px; opacity: 1; }
            100% { bottom: -500px; opacity: 0; }
        }
        
        @keyframes wiggle {
            0%, 100% { transform: rotate(-5deg); }
            50% { transform: rotate(5deg); }
        }

        .anim-container {
            position: fixed;
            bottom: -500px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 99999;
            text-align: center;
            animation: jumpUp 5s ease-in-out forwards;
            pointer-events: none;
        }

        .mr-potato {
            position: relative;
            display: inline-block;
            width: 200px;
            height: 250px;
        }
        
        .body {
            font-size: 180px;
            position: absolute;
            bottom: 0;
            left: 50%;
            transform: translateX(-50%);
            z-index: 1;
            filter: drop-shadow(0 10px 10px rgba(0,0,0,0.3));
        }

        .hat {
            font-size: 80px;
            position: absolute;
            top: -20px;
            left: 55%;
            transform: translateX(-50%) rotate(-10deg);
            z-index: 3;
            animation: wiggle 1s infinite ease-in-out;
        }

        .eyes {
            font-size: 50px;
            position: absolute;
            top: 70px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 2;
        }

        .mustache {
            font-size: 50px;
            position: absolute;
            top: 100px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 2;
            color: #333;
        }

        .shoes {
            font-size: 60px;
            position: absolute;
            bottom: -10px;
            left: 50%;
            transform: translateX(-50%);
            z-index: 3;
        }

        .speech-bubble {
            background: #ffffff;
            border: 4px solid #2c3e50;
            border-radius: 30px;
            padding: 15px 30px;
            font-size: 22px;
            font-weight: 800;
            color: #2c3e50;
            font-family: 'Segoe UI', sans-serif;
            position: relative;
            margin-bottom: 20px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.15);
            display: inline-block;
            white-space: nowrap;
        }
        
        .speech-bubble:after {
            content: '';
            position: absolute;
            bottom: -20px;
            left: 50%;
            border: 20px solid transparent;
            border-top-color: #2c3e50;
            border-bottom: 0;
            border-left: 0;
            margin-left: -10px;
            margin-bottom: -20px;
        }
    </style>
    
    <div class="anim-container">
        <div class="speech-bubble">OSASIT KIRJOITTAA SALASANAN OIKEIN !</div>
        <div class="mr-potato">
            <div class="hat">🎩</div>
            <div class="eyes">👀</div>
            <div class="mustache">〰️</div>
            <div class="body">🥔</div>
            <div class="shoes">👞</div>
        </div>
    </div>
    """
    
    with placeholder.container():
        st.markdown(mr_potato_html, unsafe_allow_html=True)
        time.sleep(5) 
        
    placeholder.empty()
    st.session_state.intro_shown = True

# --- TYÖKALUT (GOOGLE SHEETS) ---
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

st.subheader("📊 Hintamatriisi (Kaikki tuotteet)")
st.caption("Tämä taulukko näyttää uusimman hinnan kaikista tietokannan tuotteista verrattuna edelliseen mittaukseen.")

if df.empty:
    st.write("Ei dataa matriisille.")
else:
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
        
        price_str = f"{price:.2f} €"
        
        # Nuolet (▲/▼)
        arrow = ""
        if pd.notna(prev):
            if price > prev: arrow = " ▲"
            elif price < prev: arrow = " ▼"
            elif price == prev: arrow = " ➖"
            
        return f"{price_str}{arrow}"

    merged_df['formatted_cell'] = merged_df.apply(format_price_cell, axis=1)

    # 1. Luodaan matriisi (Pivot)
    matrix_df = merged_df.pivot_table(
        index='tuote',
        columns='kauppa',
        values='formatted_cell',
        aggfunc='first'
    )

    # 2. Haetaan EAN-koodit erikseen ja liitetään ne matriisiin
    if 'ean' in df.columns:
        ean_map = df[['tuote', 'ean']].drop_duplicates(subset=['tuote'], keep='last').set_index('tuote')
        
        # Yhdistetään EAN matriisiin
        matrix_df = matrix_df.join(ean_map)
        
        # 3. Järjestetään sarakkeet: EAN ensin, sitten kaupat aakkosjärjestyksessä
        store_cols = sorted([c for c in matrix_df.columns if c != 'ean'])
        
        # Asetetaan uusi järjestys: [ean, kauppa1, kauppa2...]
        matrix_df = matrix_df[['ean'] + store_cols]
        
        # Siistitään EAN-sarakkeen puuttuvat arvot tyhjiksi
        matrix_df['ean'] = matrix_df['ean'].fillna('')

    # VÄRITYSLOGIIKKA
    def color_arrows(val):
        if isinstance(val, str):
            if "▲" in val:
                return "color: #28a745; font-weight: bold;"  # Vihreä
            elif "▼" in val:
                return "color: #dc3545; font-weight: bold;"  # Punainen
        return ""

    # KÄYTETÄÄN STYLE.MAP VÄRITYKSEEN
    st.dataframe(
        matrix_df.style.map(color_arrows), 
        use_container_width=True, 
        height=700
    )

if st.button('🔄 Päivitä tiedot'):
    st.rerun()

