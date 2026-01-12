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
#   AUTHENTICATION LOGIC
# =========================================================
def check_password():
    apply_login_css()  # Login-teema käyttöön aina kun ollaan tässä vaiheessa

    CORRECT_PASSWORD = "Potwell25!"

    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False
    if "login_success_anim" not in st.session_state:
        st.session_state.login_success_anim = False
    if "login_error_anim" not in st.session_state:
        st.session_state.login_error_anim = False

    if st.session_state.password_correct:
        return True

    # --- LOGIN SCREEN CSS (Only active when logged out) ---
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

    /* Make the whole login form exactly same width as input (this guarantees perfect centering) */
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
    color: #6b7280 !important;  /* neutral gray */
   }
    div[data-testid="stForm"] div[data-testid="stTextInput"]:focus-within > div {
        border-color: rgba(14, 165, 183, 0.9) !important;
        box-shadow: 0 0 12px rgba(14, 165, 183, 0.22) !important;
    }

/* Lock login form width to match input exactly */
div[data-testid="stForm"]{
    max-width: 420px !important;
    margin: 0 auto !important;
}

/* Hide Streamlit's "Press Enter to submit form" hint */
div[data-testid="stTextInput"] [data-testid="InputInstructions"] { display: none !important; }
div[data-testid="stTextInput"] [data-testid="stInputInstructions"] { display: none !important; }
/* fallback for different Streamlit versions */
div[data-testid="stTextInput"] div[aria-live="polite"] { display: none !important; }

/* Center the *form submit* button (Streamlit uses stFormSubmitButton wrapper) */
div[data-testid="stFormSubmitButton"]{
    display: flex !important;
    justify-content: center !important;
    margin-top: 14px !important;
}

/* Style submit button (not full width) */
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

    if not st.session_state.login_success_anim:
        form_placeholder = st.empty()
        with form_placeholder.container():

            with st.form("login_form", clear_on_submit=False):
                password = st.text_input(
                    "SYÖTÄ SALASANA",
                    type="password",
                    key="login_pass",
                    label_visibility="collapsed",
                    placeholder="SYÖTÄ SALASANA"
                )

                submitted = st.form_submit_button("KIRJAUDU")

            # Handle submit (button click OR Enter)
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

# Tästä eteenpäin ollaan sisällä -> vaihdetaan dashboardin vaaleampi teema
apply_dashboard_css()

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
            df['hinta'] = df['hinta'].astype(str).str.replace(',', '.', regex=False)
            df['hinta'] = pd.to_numeric(df['hinta'], errors='coerce')

            # Älykäs korjaus: jos > 40 €/kg, oletetaan desimaali puuttuu -> /100
            df.loc[df['hinta'] > 40, 'hinta'] = df['hinta'] / 100

        return df
    except Exception:
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
try:
    last_update = df['pvm'].max()
    update_str = last_update.strftime('%d.%m.%Y')
except Exception:
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

        stats_df = graph_df.groupby(['pvm', 'tuote'])['hinta'].agg(
            Keskiarvo='mean',
            Minimi='min',
            Maksimi='max'
        ).reset_index()

        melted_df = stats_df.melt(['pvm', 'tuote'], var_name='Mittari', value_name='Hinta')

        base = alt.Chart(melted_df).encode(
            x=alt.X('pvm:T', axis=alt.Axis(format='%d.%m.', title=None, grid=False, tickCount=10)),
            y=alt.Y('Hinta:Q', title='Hinta (€)', scale=alt.Scale(zero=False, padding=0.5),
                    axis=alt.Axis(grid=True, gridDash=[2, 2], gridColor='#d1d5db')),
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
            title=alt.TitleParams("Hintakehitys", anchor='start', fontSize=18, color='#374151')
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
    sorted_dates = sorted(df['pvm'].unique(), reverse=True)
    latest_date = sorted_dates[0]
    previous_date = sorted_dates[1] if len(sorted_dates) > 1 else None

    latest_df = df[df['pvm'] == latest_date].copy()
    latest_df = latest_df.rename(columns={'hinta': 'price_now'})

    if previous_date is not None:
        prev_df = df[df['pvm'] == previous_date][['kauppa', 'tuote', 'hinta']].copy()
        prev_df = prev_df.rename(columns={'hinta': 'price_prev'})
        merged_df = pd.merge(latest_df, prev_df, on=['kauppa', 'tuote'], how='left')
    else:
        merged_df = latest_df
        merged_df['price_prev'] = np.nan

    def format_price_cell(row):
        price = row['price_now']
        prev = row['price_prev']
        if pd.isna(price):
            return None

        price_str = f"{price:.2f} €"
        arrow = ""

        if pd.notna(prev):
            if price > prev:
                arrow = " ▲"
            elif price < prev:
                arrow = " ▼"
            else:
                arrow = " ➖"

        return f"{price_str}{arrow}"

    merged_df['formatted_cell'] = merged_df.apply(format_price_cell, axis=1)

    def detect_chain(store_name):
        if "KM " in store_name:
            return "3. K-Market"
        if "SM " in store_name:
            return "2. K-Supermarket"
        return "1. K-Citymarket"

    merged_df['Ketju'] = merged_df['kauppa'].apply(detect_chain)

    matrix_df = merged_df.pivot_table(
        index='tuote',
        columns=['Ketju', 'kauppa'],
        values='formatted_cell',
        aggfunc='first'
    )

    if 'ean' in df.columns:
        ean_map = df[['tuote', 'ean']].drop_duplicates(subset=['tuote'], keep='last').set_index('tuote')

        ean_header = pd.MultiIndex.from_tuples([(" Tuotetiedot", "EAN")])
        ean_df = pd.DataFrame(ean_map['ean'], index=matrix_df.index)
        ean_df.columns = ean_header

        final_df = pd.concat([ean_df, matrix_df], axis=1)
        final_df[(" Tuotetiedot", "EAN")] = final_df[(" Tuotetiedot", "EAN")].fillna('')
    else:
        final_df = matrix_df

    def color_arrows(val):
        if isinstance(val, str):
            if "▲" in val:
                return "color: #16a34a; font-weight: 700;"
            if "▼" in val:
                return "color: #dc2626; font-weight: 700;"
            if "➖" in val:
                return "color: #6b7280; font-weight: 700;"
        return ""

    st.dataframe(
        final_df.style.map(color_arrows),
        use_container_width=True,
        height=800
    )

if st.button('🔄 Päivitä tiedot'):
    st.rerun()








