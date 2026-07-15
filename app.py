import streamlit as st
import pandas as pd
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

# --- KONFIGURATION ---
st.set_page_config(page_title="WNBA Value Analyst", page_icon="🏀", layout="centered")
st.title("🏀 WNBA Value Analyst Pro")
st.caption("Mit Auto-Scanner für 'Out' & 'Day-to-Day' Ausfälle")

# --- HILFSFUNKTIONEN ---
@st.cache_data(ttl=3600)
def hole_live_news(team):
    try:
        query = urllib.parse.quote(f'"{team}" WNBA injury OR news')
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response: 
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        return [{"titel": i.find('title').text, "link": i.find('link').text} for i in root.findall('.//item')[:4]]
    except Exception:
        return []

def auto_detect_injuries(news_list, player_dict):
    """Scannt und unterscheidet zwischen 'Sicher Out' und 'Day-to-Day'"""
    out_list = []
    dtd_list = []
    
    # Trennung der Signalwörter
    out_kw = ['out', 'surgery', 'misses', 'miss', 'ruled out', 'will not play']
    dtd_kw = ['day-to-day', 'day to day', 'questionable', 'doubtful', 'gtd', 'game-time decision', 'sprain', 'injury']
    
    for item in news_list:
        titel = item.get('titel', '').lower()
        is_out = any(kw in titel for kw in out_kw)
        is_dtd = any(kw in titel for kw in dtd_kw)
        
        if is_out or is_dtd:
            for key in player_dict.keys():
                if "Generisch" in key: continue
                
                clean_name = key.replace('⭐', '').replace('🏀', '').split('(')[0].strip().lower()
                if clean_name in titel:
                    # Wenn "out" im Text steht, landet sie in der Out-Liste
                    if is_out and key not in out_list:
                        out_list.append(key)
                    # Wenn nur "day-to-day" etc. im Text steht, landet sie in der DTD-Liste
                    elif is_dtd and not is_out and key not in dtd_list and key not in out_list:
                        dtd_list.append(key)
                        
    return out_list, dtd_list

@st.cache_data
def lade_wnba_daten():
    if not os.path.exists('wnba_stats.csv'): return "FEHLT", None
    try:
        df = pd.read_csv('wnba_stats.csv', encoding='utf-8')
        
        if 'Team' not in df.columns and 'TEAM' not in [str(c).upper() for c in df.columns]:
            for i in range(5):
                row_vals = [str(x).strip().upper() for x in df.iloc[i].values]
                if 'TEAM' in row_vals and 'PTS' in row_vals:
                    df.columns = df.iloc[i] 
                    df = df[i+1:].reset_index(drop=True)
                    break
                    
        df.columns = [str(c).strip().upper() for c in df.columns]
        team_col = next((c for c in df.columns if c in ['TEAM', 'TEAM_NAME', 'NAME']), None)
        pts_col = next((c for c in df.columns if c in ['PTS', 'POINTS']), None)
        opp_col = next((c for c in df.columns if c in ['OPP_PTS', 'OPP_POINTS']), None)
        pace_col = next((c for c in df.columns if c in ['PACE', 'SPEED']), None)
            
        if not team_col or not pts_col: return None, None

        df[pts_col] = pd.to_numeric(df[pts_col], errors='coerce')
        if not opp_col:
            df['OPP_PTS'] = df[pts_col].mean()
            opp_col = 'OPP_PTS'
        if not pace_col:
            df['PACE'] = 80.0
            pace_col = 'PACE'
            
        clean_df = df[[team_col, pts_col, opp_col, pace_col]].copy().dropna()
        clean_df.columns = ['Team', 'PTS', 'OPP_PTS', 'PACE']
        return "OK", clean_df
    except: 
        return "ERROR", None

def berechne_hca(team_name):
    team_upper = str(team_name).upper()
    if any(x in team_upper for x in ['VEGAS', 'ACES', 'LVA']): return 3.0
    if any(x in team_upper for x in ['INDIANA', 'FEVER', 'IND']): return 2.5
    if any(x in team_upper for x in ['NEW YORK', 'LIBERTY', 'NYL']): return 2.5
    if any(x in team_upper for x in ['SEATTLE', 'STORM', 'SEA']): return 2.5
    if any(x in team_upper for x in ['CONNECTICUT', 'SUN', 'CON']): return 2.0
    if any(x in team_upper for x in ['MINNESOTA', 'LYNX', 'MIN']): return 2.0
    if any(x in team_upper for x in ['PHOENIX', 'MERCURY', 'PHO']): return 2.0
    return 1.5

# --- DATEN-CHECK ---
status, wnba_df = lade_wnba_daten()
if wnba_df is None: 
    st.error("Daten-Ladefehler. Bitte lade eine gültige wnba_stats.csv hoch.")
    st.stop()

# --- SPIELER DATENBANK (ATS Values) ---
wnba_player_values = {
    "⭐ A'ja Wilson (LVA)": 5.0, "⭐ Breanna Stewart (NYL)": 4.5, "⭐ Napheesa Collier (MIN)": 4.0,
    "⭐ Alyssa Thomas (CON)": 3.5, "⭐ Caitlin Clark (IND)": 3.5, "⭐ Sabrina Ionescu (NYL)": 3.0,
    "🏀 Kelsey Plum (LVA)": 2.5, "🏀 Jewell Loyd (SEA)": 2.5, "🏀 Arike Ogunbowale (DAL)": 2.5,
    "🏀 Jonquel Jones (NYL)": 2.5, "🏀 Kahleah Copper (PHO)": 2.5, "🏀 Brittney Griner (PHO)": 2.0,
    "🏀 Nneka Ogwumike (SEA)": 2.0, "🏀 Jackie Young (LVA)": 2.0, "🏀 Aliyah Boston (IND)": 1.5,
    "🏀 Chelsea Gray (LVA)": 1.5, "🏀 DeWanna Bonner (CON)": 1.5, "🏀 Rhyne Howard (ATL)": 1.5,
    "👤 Standard Starter (Generisch)": 1.5, "👤 Bankspieler (Generisch)": 0.5
}

# --- UI: PARAMETER ---
teams_list = sorted(wnba_df['Team'].tolist())
c1, c2 = st.columns(2)
wnba_home = c1.selectbox("Heimteam", teams_list, index=0)
wnba_away = c2.selectbox("Auswärtsteam", teams_list, index=1 if len(teams_list)>1 else 0)

# News laden und Scanner anwerfen (trennt jetzt Out & DTD)
news_home_data = hole_live_news(wnba_home)
news_away_data = hole_live_news(wnba_away)

auto_home_out, auto_home_dtd = auto_detect_injuries(news_home_data, wnba_player_values)
auto_away_out, auto_away_dtd = auto_detect_injuries(news_away_data, wnba_player_values)

st.write("#### ✈️ Schedule & Fatigue")
col_a, col_b = st.columns(2)
rest_home = col_a.slider("Pause Heimteam (Tage)", 0, 5, 2)
rest_away = col_b.slider("Pause Auswärtsteam (Tage)", 0, 5, 2)

st.write("#### 🚑 Verletzungs-Scanner (Auto-Fill)")
st.caption("Das System unterscheidet zwischen 'Sicher Out' (voller Malus) und 'Day-to-Day' (halber Malus).")

inj_col1, inj_col2 = st.columns(2)
with inj_col1:
    st.markdown(f"**{wnba_home}**")
    home_out = st.multiselect("Sicher Out (100% Malus)", list(wnba_player_values.keys()), default=auto_home_out, key="h_out")
    home_dtd = st.multiselect("Day-to-Day (50% Malus)", list(wnba_player_values.keys()), default=auto_home_dtd, key="h_dtd")

with inj_col2:
    st.markdown(f"**{wnba_away}**")
    away_out = st.multiselect("Sicher Out (100% Malus)", list(wnba_player_values.keys()), default=auto_away_out, key="a_out")
    away_dtd = st.multiselect("Day-to-Day (50% Malus)", list(wnba_player_values.keys()), default=auto_away_dtd, key="a_dtd")

# Malus berechnen: Out = 100%, DTD = 50%
inj_home = sum([wnba_player_values[s] for s in home_out]) + sum([wnba_player_values[s] * 0.5 for s in home_dtd])
inj_away = sum([wnba_player_values[s] for s in away_out]) + sum([wnba_player_values[s] * 0.5 for s in away_dtd])

if auto_home_out or auto_home_dtd or auto_away_out or auto_away_dtd:
    st.success("🤖 Scanner hat Status-Updates gefunden und automatisch eingeordnet!")
if inj_home > 0 or inj_away > 0:
    st.info(f"📊 Aktueller Verletzungs-Malus berechnet: Heim (-{inj_home:.2f} Pkt) | Auswärts (-{inj_away:.2f} Pkt)")

st.write("#### 💰 Buchmacher-Linien")
q_col1, q_col2 = st.columns(2)
b_spread = q_col1.number_input("Handicap Heimteam (z.B. -3.5)", value=-3.5, step=0.5)
b_total = q_col2.number_input("Over/Under Linie", value=165.5, step=0.5)

# --- BERECHNUNG ---
if st.button("🚀 Matchup analysieren", use_container_width=True):
    t_home = wnba_df[wnba_df['Team'] == wnba_home].iloc[0]
    t_away = wnba_df[wnba_df['Team'] == wnba_away].iloc[0]
        
    fatigue_home = 2.0 if rest_home == 0 else (1.0 if rest_home == 1 else 0)
    fatigue_away = 2.0 if rest_away == 0 else (1.0 if rest_away == 1 else 0)
    
    hca_points = berechne_hca(wnba_home)
        
    exp_pts_home = ((t_home['PTS'] + t_away['OPP_PTS']) / 2) + hca_points - fatigue_home - inj_home
    exp_pts_away = ((t_away['PTS'] + t_home['OPP_PTS']) / 2) - fatigue_away - inj_away
    
    model_margin = exp_pts_home - exp_pts_away
    model_total = exp_pts_home + exp_pts_away
    
    bookie_margin = -b_spread 
    edge_spread = model_margin - bookie_margin
    prob_home_cover = max(5.0, min(95.0, 50.0 + (edge_spread * 3.5)))
    
    edge_total = model_total - b_total
    prob_over = max(5.0, min(95.0, 50.0 + (edge_total * 2.5)))
    
    # --- AUSGABE BERECHNUNGEN ---
    st.divider()
    st.caption(f"🏟️ *Automatischer Home Court Advantage (HCA) für {wnba_home}: +{hca_points} Punkte eingerechnet.*")
    st.subheader(f"🎯 Spiel-Prognose: {exp_pts_home:.1f} - {exp_pts_away:.1f}")
    
    # Handicap
    st.write("### ⚖️ Handicap (Spread)")
    h_col1, h_col2 = st.columns(2)
    h_col1.metric("Dein Model-Spread", f"{model_margin*-1:.1f}")
    h_col2.metric("Buchmacher Handicap", f"{b_spread}")
    
    if prob_home_cover > 55.0:
        st.success(f"🔥 **Value auf {wnba_home} ({b_spread})** mit **{prob_home_cover:.1f}%** Wahrscheinlichkeit!")
    elif prob_home_cover < 45.0:
        st.success(f"🔥 **Value auf {wnba_away} ({(b_spread*-1):+})** mit **{100-prob_home_cover:.1f}%** Wahrscheinlichkeit!")
    else:
        st.warning(f"Kein klarer Value beim Handicap (Markt ist effizient). Wahrscheinlichkeit: {prob_home_cover:.1f}%")

    st.write("---")
    
    # Over/Under
    st.write("### 📈 Over / Under")
    o_col1, o_col2 = st.columns(2)
    o_col1.metric("Dein Model-Total", f"{model_total:.1f}")
    o_col2.metric("Buchmacher Linie", f"{b_total}")
    
    if prob_over > 55.0:
        st.success(f"🔥 **Value im OVER** mit **{prob_over:.1f}%** Wahrscheinlichkeit!")
    elif prob_over < 45.0:
        st.success(f"🔥 **Value im UNDER** mit **{100-prob_over:.1f}%** Wahrscheinlichkeit!")
    else:
        st.warning(f"Kein klarer Value beim Total (Markt ist effizient). Wahrscheinlichkeit OVER: {prob_over:.1f}%")

    # --- AUSGABE LIVE-NEWS ---
    st.divider()
    st.subheader("📰 Die aktuellsten News zum Spiel")
    n_col1, n_col2 = st.columns(2)
    
    with n_col1:
        st.markdown(f"**{wnba_home}**")
        if news_home_data:
            for n in news_home_data:
                st.markdown(f"- [{n['titel']}]({n['link']})")
        else:
            st.info("Keine aktuellen relevanten News gefunden.")
            
    with n_col2:
        st.markdown(f"**{wnba_away}**")
        if news_away_data:
            for n in news_away_data:
                st.markdown(f"- [{n['titel']}]({n['link']})")
        else:
            st.info("Keine aktuellen relevanten News gefunden.")
