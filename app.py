import streamlit as st
import pandas as pd
import glob
import math
import warnings
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import datetime
import numpy as np

warnings.filterwarnings('ignore')

# --- HILFSFUNKTIONEN (SHARED) ---
def poisson_pmf(k, lamb):
    if lamb <= 0: return 0
    try: return (lamb**k * math.exp(-lamb)) / math.factorial(k)
    except: return 0

def weighted_avg(values, weights):
    mask = ~np.isnan(values) & ~np.isnan(weights)
    v, w = values[mask], weights[mask]
    if len(w) == 0 or np.sum(w) == 0: return 0.0
    return np.average(v, weights=w)

def entferne_buchmacher_marge(q1, qx, q2):
    """Berechnet faire Wahrscheinlichkeiten durch Entfernen der Buchmacher-Marge."""
    if q1 <= 0 or qx <= 0 or q2 <= 0: return 0, 0, 0
    impl_1, impl_x, impl_2 = 1/q1, 1/qx, 1/q2
    marge = impl_1 + impl_x + impl_2
    return (impl_1/marge), (impl_x/marge), (impl_2/marge)

def hole_live_news(team1, team2=None):
    try:
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(f'{team1} {team2}')}+sport&hl=de&gl=DE&ceid=DE:de"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response: xml_data = response.read()
        root = ET.fromstring(xml_data)
        return [{"titel": i.find('title').text, "link": i.find('link').text} for i in root.findall('.//item')[:3]]
    except: return []

# --- STREAMLIT KONFIGURATION ---
st.set_page_config(page_title="Pro Wett-Analyst", page_icon="📈", layout="centered")

st.sidebar.title("Navigation")
sportart = st.sidebar.radio("Sportart wählen", ["🏀 WNBA (Spread Pro)"])


# ==============================================================================
# SÄULE 2: WNBA
# ==============================================================================
st.title("🏀 WNBA Spread & Value Master")
    
    @st.cache_data
    def lade_wnba_daten():
        if not os.path.exists('wnba_stats.csv'): return "FEHLT", None
        df = pd.read_csv('wnba_stats.csv', sep=None, engine='python', encoding='utf-8')
        df.columns = [str(c).strip().upper() for c in df.columns]
        return "OK", df

    modell_typ, wnba_df = lade_wnba_daten()
    if "OK" not in str(modell_typ): st.error("Datei wnba_stats.csv nicht gefunden."); st.stop()

    c1, c2 = st.columns(2)
    teams = sorted(wnba_df['TEAM'].unique().tolist())
    h = c1.selectbox("Heimteam", teams)
    a = c2.selectbox("Auswärtsteam", teams)

    r1, r2 = st.columns(2)
    rest_h = r1.slider("Pause Heim (Tage)", 0, 5, 2)
    rest_a = r2.slider("Pause Auswärts (Tage)", 0, 5, 2)
    
    b_spread = st.number_input("Spread vom Buchmacher (z.B. -3.5)", value=-3.5)

    if st.button("🚀 WNBA Edge & Spread berechnen"):
        t_h = wnba_df[wnba_df['TEAM'] == h].iloc[0]
        t_a = wnba_df[wnba_df['TEAM'] == a].iloc[0]
        
        # Fatigue Modifikator
        f_h = 2.5 if rest_h == 0 else 0
        f_a = 2.5 if rest_a == 0 else 0
        
        exp_h = t_h['PTS'] - t_h['OPP_PTS'] + f_a - f_h
        exp_a = t_a['PTS'] - t_a['OPP_PTS'] + f_h - f_a
        model_spread = (exp_h + exp_a) / 2
        
        st.divider()
        st.metric("Dein berechneter Spread", f"{model_spread:.1f} Pkt")
        st.metric("Buchmacher-Linie", f"{b_spread:.1f} Pkt")
        
        diff = model_spread - b_spread
        if abs(diff) > 1.5:
            st.success(f"🔥 VALUE FOUND! Edge: {abs(diff):.1f} Punkte.")
        else:
            st.warning("Markt effizient.")

    st.write("---")
    st.write("📰 **Live News:**")
    for n in hole_live_news(h, a):
        st.markdown(f"- [{n['titel']}]({n['link']})")
