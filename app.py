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
 # SÄULE 2: WNBA BASKETBALL (V9 PRO EDGE)
 # ==============================================================================

st.title("🏀 WNBA Buchmacher-Analyst Pro")
st.caption("Mit Fatigue-Faktor, Margin-Removal & Recency-Weighting")

@st.cache_data
def lade_wnba_daten():
    if not os.path.exists('wnba_stats.csv'): return "FEHLT", None
    try:
        df = pd.read_csv('wnba_stats.csv', sep=None, engine='python', encoding='utf-8')
        df.columns = [str(c).strip().upper() for c in df.columns]
            
        # Modell erwartet Spalten: TEAM, PTS, OPP_PTS, PACE
        # Optional: DATE (für Time Decay)
        team_col = next((c for c in df.columns if c in ['TEAM', 'TEAM_NAME', 'NAME', 'MANNSCHAFT']), None)
        pts_col = next((c for c in df.columns if c in ['PTS', 'POINTS', 'PUNKTE']), None)
        opp_col = next((c for c in df.columns if c in ['OPP_PTS', 'OPP_POINTS', 'OPPTS']), None)
        pace_col = next((c for c in df.columns if c in ['PACE', 'SPEED']), None)
            
        if not all([team_col, pts_col, opp_col, pace_col]): return "SPALTEN_FEHLER", None
            
        clean_df = df[[team_col, pts_col, opp_col, pace_col]].copy()
        clean_df.columns = ['Team', 'PTS', 'OPP_PTS', 'PACE']
        return "EFFIZIENZ_MODELL", clean_df
    except: return "ERROR", None

modell_typ, wnba_df = lade_wnba_daten()
if "ERROR" in str(modell_typ): 
    st.error("Datenfehler in wnba_stats.csv")
    st.stop()

teams_list = sorted(wnba_df['Team'].tolist())
c1, c2 = st.columns(2)
with c1: wnba_home = st.selectbox("Heimteam", teams_list, index=0)
with c2: wnba_away = st.selectbox("Auswärtsteam", teams_list, index=1)

 # Fatigue & Travel (Der "Pro-Spot" Faktor)
st.write("#### ✈️ Schedule & Fatigue Faktoren")
col_a, col_b = st.columns(2)
rest_home = col_a.slider(f"Pause {wnba_home} (Tage)", 0, 5, 2)
rest_away = col_b.slider(f"Pause {wnba_away} (Tage)", 0, 5, 2)
    
# Margin Removal für Quoten
st.write("#### 💰 Buchmacher-Linien bereinigen")
q_col1, q_col2 = st.columns(2)
m_quote_home = q_col1.number_input("Moneyline Heim", min_value=1.01, value=1.50)
m_quote_away = q_col2.number_input("Moneyline Auswärts", min_value=1.01, value=2.50)

if st.button("🏀 WNBA Edge berechnen", use_container_width=True):
    # 1. Daten holen
    t_home = wnba_df[wnba_df['Team'] == wnba_home].iloc[0]
    t_away = wnba_df[wnba_df['Team'] == wnba_away].iloc[0]
        
    # 2. Fatigue Adjustment (Modell-Malus/Bonus)
    fatigue_home = 2.0 if rest_home == 0 else (1.0 if rest_home == 1 else 0)
    fatigue_away = 2.0 if rest_away == 0 else (1.0 if rest_away == 1 else 0)
        
    # 3. Efficiency Calculation
    avg_pace = wnba_df['PACE'].mean()
    avg_off = wnba_df['PTS'].mean()
        
    exp_pts_home = (t_home['PTS'] + t_away['OPP_PTS']) / 2 - fatigue_home
    exp_pts_away = (t_away['PTS'] + t_home['OPP_PTS']) / 2 - fatigue_away
        
    # 4. True Odds (Margin Removal)
    # Wir berechnen die faire Wahrscheinlichkeit ohne Buchmacher-Marge
    true_h, _, true_a = entferne_buchmacher_marge(m_quote_home, 99.0, m_quote_away) 
        
    # 5. Value Check
    # Wir schätzen die Siegchance basierend auf der Effizienz-Differenz
    model_prob_home = 0.5 + (exp_pts_home - exp_pts_away) * 0.02 # Rule of thumb für Basketball
    model_prob_home = max(0.1, min(0.9, model_prob_home))
        
    st.divider()
    st.subheader("🎯 Resultat & Value")
        
    c_res1, c_res2 = st.columns(2)
    c_res1.metric("KI Siegchance (Heim)", f"{model_prob_home*100:.1f}%")
    c_res2.metric("True Market Prob", f"{true_h*100:.1f}%")
        
    if model_prob_home > true_h + 0.03:
        st.success(f"🔥 VALUE FOUND! KI sieht {wnba_home} stärker als der Markt. Edge: {(model_prob_home - true_h)*100:.1f}%")
    else:
        st.warning("Kein signifikanter Value gefunden. Markt ist effizient.")

    st.caption(f"Erwarteter Score: {exp_pts_home:.1f} : {exp_pts_away:.1f}")
