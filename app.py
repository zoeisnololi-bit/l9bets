import streamlit as st
import pandas as pd
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import datetime
import math

# --- KONFIGURATION ---
st.set_page_config(page_title="WNBA Value Analyst", page_icon="🏀", layout="centered")
st.title("🏀 WNBA Value Analyst Pro")
st.caption("Advanced Math: Ratings, Pace-Simulation, Formkurve & Normalverteilung")

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
    out_list, dtd_list = [], []
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
                    if is_out and key not in out_list:
                        out_list.append(key)
                    elif is_dtd and not is_out and key not in dtd_list and key not in out_list:
                        dtd_list.append(key)
    return out_list, dtd_list

@st.cache_data(ttl=3600*12) 
def hole_team_context(team_name):
    """Zieht Ruhetage UND die Formkurve (letzte 5 Spiele) von ESPN"""
    try:
        url_teams = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams"
        req = urllib.request.Request(url_teams, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            data = json.loads(response.read())
            
        team_id = None
        for element in data.get('sports', [])[0].get('leagues', [])[0].get('teams', []):
            t = element['team']
            if team_name.lower() in t['displayName'].lower() or team_name.lower() in t['name'].lower():
                team_id = t['id']
                break
                
        if not team_id: return 2, None, None
            
        url_sched = f"https://site.api.espn.com/apis/site/v2/sports/basketball/wnba/teams/{team_id}/schedule"
        req_sched = urllib.request.Request(url_sched, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_sched, timeout=4) as response:
            sched_data = json.loads(response.read())
            
        today_date = datetime.datetime.utcnow().date()
        last_game_date = None
        recent_pts, recent_opp = [], []
        
        # Spiele durchgehen und sortieren
        events = sched_data.get('events', [])
        for event in reversed(events): # Von neu nach alt
            game_date = datetime.datetime.strptime(event['date'], "%Y-%m-%dT%H:%M:%SZ").date()
            if game_date < today_date:
                if last_game_date is None or game_date > last_game_date:
                    last_game_date = game_date
                
                # Scores extrahieren für die Formkurve
                competitors = event.get('competitions', [{}])[0].get('competitors', [])
                if len(competitors) == 2:
                    t_score = o_score = 0
                    for c in competitors:
                        val = float(c.get('score', {}).get('value', 0))
                        if c.get('id') == team_id: t_score = val
                        else: o_score = val
                    if t_score > 0 and o_score > 0:
                        recent_pts.append(t_score)
                        recent_opp.append(o_score)
                        
                if len(recent_pts) >= 5: # Nur die letzten 5 Spiele
                    break
                    
        rest_days = min((today_date - last_game_date).days, 5) if last_game_date else 2
        
        avg_recent_pts = sum(recent_pts) / len(recent_pts) if recent_pts else None
        avg_recent_opp = sum(recent_opp) / len(recent_opp) if recent_opp else None
        
        return rest_days, avg_recent_pts, avg_recent_opp
    except Exception:
        return 2, None, None

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
        if not opp_col: df['OPP_PTS'] = df[pts_col].mean()
        else: opp_col = 'OPP_PTS'
        if not pace_col: df['PACE'] = 80.0
        else: pace_col = 'PACE'
            
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

def get_win_probability(edge, std_dev):
    """Berechnet die faire Wahrscheinlichkeit basierend auf Normalverteilung (Gauß)"""
    # math.erf ist die Error-Function zur Berechnung der kumulativen Verteilungsfunktion
    return 0.5 * (1.0 + math.erf(edge / (std_dev * math.sqrt(2.0)))) * 100.0

# --- DATEN-CHECK ---
status, wnba_df = lade_wnba_daten()
if wnba_df is None: 
    st.error("Daten-Ladefehler. Bitte lade eine gültige wnba_stats.csv hoch.")
    st.stop()

# --- SPIELER DATENBANK ---
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

# Daten im Hintergrund laden
news_home_data = hole_live_news(wnba_home)
news_away_data = hole_live_news(wnba_away)

auto_home_out, auto_home_dtd = auto_detect_injuries(news_home_data, wnba_player_values)
auto_away_out, auto_away_dtd = auto_detect_injuries(news_away_data, wnba_player_values)

auto_rest_home, form_pts_home, form_opp_home = hole_team_context(wnba_home)
auto_rest_away, form_pts_away, form_opp_away = hole_team_context(wnba_away)

st.write("#### ✈️ Schedule & Fatigue")
col_a, col_b = st.columns(2)
rest_home = col_a.slider("Pause Heimteam (Tage)", 0, 5, auto_rest_home)
rest_away = col_b.slider("Pause Auswärtsteam (Tage)", 0, 5, auto_rest_away)

st.write("#### 🚑 Verletzungs-Scanner")
inj_col1, inj_col2 = st.columns(2)
with inj_col1:
    st.markdown(f"**{wnba_home}**")
    home_out = st.multiselect("Sicher Out (100%)", list(wnba_player_values.keys()), default=auto_home_out, key="h_out")
    home_dtd = st.multiselect("Day-to-Day (50%)", list(wnba_player_values.keys()), default=auto_home_dtd, key="h_dtd")

with inj_col2:
    st.markdown(f"**{wnba_away}**")
    away_out = st.multiselect("Sicher Out (100%)", list(wnba_player_values.keys()), default=auto_away_out, key="a_out")
    away_dtd = st.multiselect("Day-to-Day (50%)", list(wnba_player_values.keys()), default=auto_away_dtd, key="a_dtd")

inj_home = sum([wnba_player_values[s] for s in home_out]) + sum([wnba_player_values[s] * 0.5 for s in home_dtd])
inj_away = sum([wnba_player_values[s] for s in away_out]) + sum([wnba_player_values[s] * 0.5 for s in away_dtd])

st.write("#### 💰 Buchmacher-Linien")
q_col1, q_col2 = st.columns(2)
b_spread_str = q_col1.text_input("Europäisches Handicap (z.B. 0:3.5)", value="0:3.5")
b_total = q_col2.number_input("Over/Under Linie", value=165.5, step=0.5)

# --- BERECHNUNG ---
if st.button("🚀 Profi-Matchup analysieren", use_container_width=True):
    
    try:
        h_str, a_str = b_spread_str.split(':')
        h_headstart = float(h_str.replace(',', '.'))
        a_headstart = float(a_str.replace(',', '.'))
        b_spread = h_headstart - a_headstart 
    except ValueError:
        st.error("Fehler: Bitte gib das Handicap im korrekten Format ein, z.B. 0:3.5")
        st.stop()
    
    t_home = wnba_df[wnba_df['Team'] == wnba_home].iloc[0]
    t_away = wnba_df[wnba_df['Team'] == wnba_away].iloc[0]
    
    # 1. FORMGEWICHTUNG (70% Saison / 30% Letzte 5 Spiele)
    weight_recent = 0.30
    weight_season = 0.70
    
    adj_pts_home = (t_home['PTS'] * weight_season + form_pts_home * weight_recent) if form_pts_home else t_home['PTS']
    adj_opp_home = (t_home['OPP_PTS'] * weight_season + form_opp_home * weight_recent) if form_opp_home else t_home['OPP_PTS']
    
    adj_pts_away = (t_away['PTS'] * weight_season + form_pts_away * weight_recent) if form_pts_away else t_away['PTS']
    adj_opp_away = (t_away['OPP_PTS'] * weight_season + form_opp_away * weight_recent) if form_opp_away else t_away['OPP_PTS']

    # 2. EFFIZIENZ (Offensive/Defensive Ratings)
    home_off_rtg = (adj_pts_home / t_home['PACE']) * 100
    home_def_rtg = (adj_opp_home / t_home['PACE']) * 100
    away_off_rtg = (adj_pts_away / t_away['PACE']) * 100
    away_def_rtg = (adj_opp_away / t_away['PACE']) * 100

    game_pace = (t_home['PACE'] + t_away['PACE']) / 2
        
    fatigue_home = 2.0 if rest_home == 0 else (1.0 if rest_home == 1 else 0)
    fatigue_away = 2.0 if rest_away == 0 else (1.0 if rest_away == 1 else 0)
    hca_points = berechne_hca(wnba_home)
        
    # Erwartete Punkte auf Basis von Pace & Ratings simulieren
    exp_pts_home = ((home_off_rtg + away_def_rtg) / 2) * (game_pace / 100) + hca_points - fatigue_home - inj_home
    exp_pts_away = ((away_off_rtg + home_def_rtg) / 2) * (game_pace / 100) - fatigue_away - inj_away
    
    model_margin = exp_pts_home - exp_pts_away
    model_total = exp_pts_home + exp_pts_away
    
    bookie_margin = -b_spread 
    edge_spread = model_margin - bookie_margin
    edge_total = model_total - b_total
    
    # 3. WAHRSCHEINLICHKEIT (Gaußsche Normalverteilung)
    # WNBA Standardabweichung (Spread ca. 11.0 | Total ca. 14.0)
    prob_home_cover = get_win_probability(edge_spread, std_dev=11.0)
    prob_over = get_win_probability(edge_total, std_dev=14.0)
    
    # --- AUSGABE ---
    st.divider()
    
    form_msg = "✅ Formkurve (letzte 5 Spiele) erfolgreich via ESPN abgerufen & integriert." if form_pts_home and form_pts_away else "⚠️ Formkurve konnte nicht abgerufen werden (Nutze reinen Saison-Schnitt)."
    st.caption(f"🏟️ *{form_msg} | HCA {wnba_home}: +{hca_points} Pkt | Game Pace: {game_pace:.1f}*")
    
    st.subheader(f"🎯 Spiel-Prognose: {exp_pts_home:.1f} - {exp_pts_away:.1f}")
    
    st.write("### ⚖️ Handicap (Spread)")
    h_col1, h_col2 = st.columns(2)
    model_h_str = f"0:{model_margin:.1f}" if model_margin > 0 else f"{model_margin*-1:.1f}:0"
    h_col1.metric("Dein Model-Handicap", model_h_str)
    h_col2.metric("Buchmacher Handicap", b_spread_str)
    
    # Neue Schwellenwerte für "Value" (ab 54% ist es bei 1.90er Quoten profitabel)
    if prob_home_cover >= 54.0:
        st.success(f"🔥 **Value auf {wnba_home} (bei {b_spread_str})** | Wahrscheinlichkeit: **{prob_home_cover:.1f}%**")
    elif prob_home_cover <= 46.0:
        st.success(f"🔥 **Value auf {wnba_away} (bei {b_spread_str})** | Wahrscheinlichkeit: **{100-prob_home_cover:.1f}%**")
    else:
        st.warning(f"Kein klarer Value (Markt ist extrem scharf). Wahrscheinlichkeit Heim-Sieg (inkl. HC): {prob_home_cover:.1f}%")

    st.write("---")
    
    st.write("### 📈 Over / Under")
    o_col1, o_col2 = st.columns(2)
    o_col1.metric("Dein Model-Total", f"{model_total:.1f}")
    o_col2.metric("Buchmacher Linie", f"{b_total}")
    
    if prob_over >= 54.0:
        st.success(f"🔥 **Value im OVER** | Wahrscheinlichkeit: **{prob_over:.1f}%**")
    elif prob_over <= 46.0:
        st.success(f"🔥 **Value im UNDER** | Wahrscheinlichkeit: **{100-prob_over:.1f}%**")
    else:
        st.warning(f"Kein klarer Value. Wahrscheinlichkeit OVER: {prob_over:.1f}%")

    # --- LIVE NEWS ---
    st.divider()
    st.subheader("📰 Die aktuellsten News zum Spiel")
    n_col1, n_col2 = st.columns(2)
    with n_col1:
        st.markdown(f"**{wnba_home}**")
        if news_home_data:
            for n in news_home_data: st.markdown(f"- [{n['titel']}]({n['link']})")
        else: st.info("Keine News.")
    with n_col2:
        st.markdown(f"**{wnba_away}**")
        if news_away_data:
            for n in news_away_data: st.markdown(f"- [{n['titel']}]({n['link']})")
        else: st.info("Keine News.")
