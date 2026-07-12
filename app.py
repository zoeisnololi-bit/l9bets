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
sportart = st.sidebar.radio("Sportart wählen", ["⚽ Fußball (xG Pro)", "🏀 WNBA (Spread Pro)"])

# ==============================================================================
# SÄULE 1: FUSSBALL
# ==============================================================================
if sportart == "⚽ Fußball (xG Pro)":
    st.title("⚽ Tipico Analyst Pro (xG & Edge)")
    
    @st.cache_data
    def lade_fussball_daten():
        csv_dateien = [f for f in glob.glob('*.csv') if f != 'wnba_stats.csv']
        if not csv_dateien: return None, None, None
        
        daten_liste = []
        heute = pd.Timestamp(datetime.date.today())
        
        for datei in csv_dateien:
            try:
                df = pd.read_csv(datei, sep=None, engine='python', encoding='utf-8')
                df.columns = [str(c).strip().upper() for c in df.columns]
                # Spalten mappen
                d = {'DIV': 'DIV', 'HOME': 'HOMETEAM', 'AWAY': 'AWAYTEAM', 'FTHG': 'FTHG', 'FTAG': 'FTAG'}
                
                # Einfache Validierung
                if 'HOMETEAM' not in df.columns or 'FTHG' not in df.columns: continue
                
                # Torschüsse (Fallback)
                hst = df['HST'] if 'HST' in df.columns else df['FTHG'] * 2.5
                ast = df['AST'] if 'AST' in df.columns else df['FTAG'] * 2.5
                
                clean = pd.DataFrame({'Div': df.get('DIV', 'Unknown'), 'HomeTeam': df['HOMETEAM'], 'AwayTeam': df['AWAYTEAM'],
                                      'FTHG': pd.to_numeric(df['FTHG']), 'FTAG': pd.to_numeric(df['FTAG']),
                                      'HST': pd.to_numeric(hst), 'AST': pd.to_numeric(ast), 'Weight': 1.0})
                daten_liste.append(clean)
            except: pass
        
        df_gesamt = pd.concat(daten_liste, ignore_index=True)
        liga_daten = {}
        for liga in df_gesamt['Div'].unique():
            df_l = df_gesamt[df_gesamt['Div'] == liga]
            avg_fthg, avg_ftag = df_l['FTHG'].mean(), df_l['FTAG'].mean()
            team_stats = {}
            for t in df_l['HomeTeam'].unique():
                h = df_l[df_l['HomeTeam'] == t]
                a = df_l[df_l['AwayTeam'] == t]
                team_stats[t] = {
                    'FT_HA': h['FTHG'].mean() / avg_fthg, 'FT_HD': h['FTAG'].mean() / avg_ftag,
                    'FT_AA': a['FTAG'].mean() / avg_ftag, 'FT_AD': a['FTHG'].mean() / avg_fthg,
                    'SOT_HA': h['HST'].mean() / h['HST'].mean(), 'SOT_HD': h['AST'].mean() / a['AST'].mean() # Vereinfacht
                }
            liga_daten[liga] = {'avg_fthg': avg_fthg, 'avg_ftag': avg_ftag, 'team_stats': team_stats}
        return df_gesamt, liga_daten

    df_g, liga_d = lade_fussball_daten()
    if df_g is None: st.error("Keine Fußball-Daten gefunden."); st.stop()

    # UI
    l_key = st.selectbox("Liga", list(liga_d.keys()))
    h_team = st.selectbox("Heimteam", sorted(df_g['HomeTeam'].unique()))
    a_team = st.selectbox("Auswärtsteam", sorted(df_g['AwayTeam'].unique()))
    
    q1, qx, q2 = st.columns(3)
    quote_1 = q1.number_input("Quote 1", 1.01, value=2.0)
    quote_x = qx.number_input("Quote X", 1.01, value=3.4)
    quote_2 = q2.number_input("Quote 2", 1.01, value=3.5)

    if st.button("🚀 Match analysieren"):
        st.subheader("Analyseergebnis")
        true_1, true_x, true_2 = entferne_buchmacher_marge(quote_1, quote_x, quote_2)
        st.write(f"Fairer Marktanteil (Heim): {true_1*100:.1f}%")
        st.success("Analysiere Value basierend auf xG-Verhältnis...")

# ==============================================================================
# SÄULE 2: WNBA
# ==============================================================================
else:
    st.title("🏀 WNBA Spread & Value Master")
    
    @st.cache_data
def lade_wnba_daten():
    if not os.path.exists('wnba_stats.csv'):
        return None, "Datei 'wnba_stats.csv' nicht gefunden."
    
    # Einlesen der neuen CSV
    df = pd.read_csv('wnba_stats.csv', encoding='utf-8')
    
    # Wir machen alle Spaltennamen groß, um Fehler zu vermeiden
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    # Sicherstellen, dass die wichtigsten Spalten für das Modell da sind
    # Die Tabelle aus 444.PNG hat 'TEAM' und 'PTS'
    if 'TEAM' not in df.columns or 'PTS' not in df.columns:
        return None, f"Fehlende Spalten! Gefunden: {list(df.columns)}"
    
    # Wir fügen eine "Opponent PTS" Schätzung hinzu (da die Tabelle nur Team-Points hat)
    # Da wir keine direkten Opponent-Stats haben, nutzen wir 
    # den Durchschnitt der Liga als Proxy für die Defensive-Stärke
    df['OPP_PTS'] = df['PTS'].mean() 
    
    return df, None

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
