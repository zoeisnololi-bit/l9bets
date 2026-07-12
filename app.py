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

# --- HILFSFUNKTIONEN MATHEMATIK & HANDICAP ---
def parse_handicap(hc_str):
    try:
        parts = hc_str.split(":")
        if len(parts) == 2:
            return float(parts[0].strip()), float(parts[1].strip())
    except: pass
    return 0.0, 0.0

def poisson_pmf(k, lamb):
    if lamb <= 0: return 0
    try: return (lamb**k * math.exp(-lamb)) / math.factorial(k)
    except: return 0

def norm_sf(x, mu, sigma):
    if sigma <= 0: sigma = 0.01
    z = (x - mu) / sigma
    try: return 0.5 * math.erfc(z / math.sqrt(2))
    except: return 0.5

def weighted_avg(values, weights):
    mask = ~np.isnan(values) & ~np.isnan(weights)
    v, w = values[mask], weights[mask]
    if len(w) == 0 or np.sum(w) == 0: return 0.0
    return np.average(v, weights=w)

def berechne_match_matrix_dixon_coles(xg_home, xg_away, rho=0.13):
    matrix = np.zeros((6, 6))
    for i in range(6):
        for j in range(6):
            matrix[i, j] = poisson_pmf(i, xg_home) * poisson_pmf(j, xg_away)
            
    korrektur_00 = 1 - (xg_home * xg_away * rho)
    korrektur_10 = 1 + (xg_away * rho)
    korrektur_01 = 1 + (xg_home * rho)
    korrektur_11 = 1 - rho

    matrix[0, 0] = max(0, matrix[0, 0] * korrektur_00)
    matrix[1, 0] = max(0, matrix[1, 0] * korrektur_10)
    matrix[0, 1] = max(0, matrix[0, 1] * korrektur_01)
    matrix[1, 1] = max(0, matrix[1, 1] * korrektur_11)
    
    summe = np.sum(matrix)
    if summe > 0: matrix = matrix / summe
    return matrix

def entferne_buchmacher_marge(q1, qx, q2):
    """Berechnet die True Odds durch Entfernen der Buchmacher-Marge (Vig)"""
    if q1 <= 0 or qx <= 0 or q2 <= 0: return 0, 0, 0
    impl_1, impl_x, impl_2 = 1/q1, 1/qx, 1/q2
    marge = impl_1 + impl_x + impl_2
    return (impl_1/marge), (impl_x/marge), (impl_2/marge)

# --- LIVE NEWS FETCHER ---
def hole_live_news(team1, team2=None):
    try:
        suchbegriff = f"{team1} {team2}" if team2 else team1
        encoded_query = urllib.parse.quote(suchbegriff)
        url = f"https://news.google.com/rss/search?q={encoded_query}+sport&hl=de&gl=DE&ceid=DE:de"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        news_liste = []
        for item in root.findall('.//item')[:4]:
            titel = item.find('title').text
            link = item.find('link').text
            if " - " in titel: titel = titel.rsplit(" - ", 1)[0]
            news_liste.append({"titel": titel, "link": link})
        return news_liste
    except: return []

def scanne_wnba_injuries(team):
    try:
        encoded_query = urllib.parse.quote(f"{team} WNBA injury report")
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en&gl=US&ceid=US:en"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=4) as response: xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        gefundene_meldungen, berechneter_malus = [], 0.0
        harte_ausfaelle = ["out", "injury", "injured", "miss", "missing", "broken", "acl", "surgery", "sidelined"]
        fragliche_ausfaelle = ["questionable", "doubtful", "game-time", "gtd", "status"]
        
        for item in root.findall('.//item')[:3]:
            titel_orig = item.find('title').text
            titel_lower = titel_orig.lower()
            link = item.find('link').text
            
            if any(k in titel_lower for k in harte_ausfaelle):
                berechneter_malus += 3.0
                gefundene_meldungen.append({"titel": titel_orig, "link": link, "typ": "🔴 Bestätigter Ausfall"})
            elif any(k in titel_lower for k in fragliche_ausfaelle):
                berechneter_malus += 1.5
                gefundene_meldungen.append({"titel": titel_orig, "link": link, "typ": "🟡 Fraglich"})
                
        return gefundene_meldungen, min(berechneter_malus, 7.0)
    except: return [], 0.0

# --- STREAMLIT CONFIG ---
st.set_page_config(page_title="L9 Bet System", page_icon="📈", layout="centered")

sportart = st.sidebar.radio("Sportart wählen", ["⚽ Fußball (Minor Leagues)", "🏀 WNBA Basketball (CSV)"])

if sportart == "⚽ Fußball (Minor Leagues)":
    st.title("⚽ L9 Bet System")
    st.caption("Mit Dixon-Coles, Time Decay & Torschuss-Varianz-Minimierung")

    @st.cache_data
    def lade_fussball_daten():
        csv_dateien = [f for f in glob.glob('*.csv') if f != 'wnba_stats.csv']
        if not csv_dateien: return None, None, None
        
        daten_liste = []
        heute = pd.Timestamp(datetime.date.today())
        
        for datei in csv_dateien:
            try:
                df_temp = pd.read_csv(datei, sep=None, engine='python', encoding='utf-8')
                df_temp.columns = [str(c).strip().upper() for c in df_temp.columns]
                
                div_col = next((c for c in df_temp.columns if c in ['DIV', 'LEAGUE', 'LIGA', 'COUNTRY']), None)
                date_col = next((c for c in df_temp.columns if c in ['DATE', 'DATUM']), None)
                home_col = next((c for c in df_temp.columns if c in ['HOMETEAM', 'HOME', 'HEIM']), None)
                away_col = next((c for c in df_temp.columns if c in ['AWAYTEAM', 'AWAY', 'AUSWAERTS']), None)
                fthg_col = next((c for c in df_temp.columns if c in ['FTHG', 'HG', 'GOALSHOME', 'HOME_GOALS']), None)
                ftag_col = next((c for c in df_temp.columns if c in ['FTAG', 'AG', 'GOALSAWAY', 'AWAY_GOALS']), None)
                
                # Torschüsse für xG-Proxy
                hst_col = next((c for c in df_temp.columns if c in ['HST', 'HS', 'HOME_SHOTS_TARGET']), None)
                ast_col = next((c for c in df_temp.columns if c in ['AST', 'AS', 'AWAY_SHOTS_TARGET']), None)
                
                if not all([home_col, away_col, fthg_col, ftag_col]): continue
                    
                clean_df = pd.DataFrame()
                clean_df['Div'] = df_temp[div_col].astype(str).str.strip() if div_col else os.path.splitext(os.path.basename(datei))[0].upper()
                clean_df['HomeTeam'] = df_temp[home_col].astype(str).str.strip()
                clean_df['AwayTeam'] = df_temp[away_col].astype(str).str.strip()
                clean_df['FTHG'] = pd.to_numeric(df_temp[fthg_col], errors='coerce')
                clean_df['FTAG'] = pd.to_numeric(df_temp[ftag_col], errors='coerce')
                
                # Torschüsse parsen (Fallback: Tore * 2.5, falls in Liga nicht erfasst)
                clean_df['HST'] = pd.to_numeric(df_temp[hst_col], errors='coerce') if hst_col else clean_df['FTHG'] * 2.5
                clean_df['AST'] = pd.to_numeric(df_temp[ast_col], errors='coerce') if ast_col else clean_df['FTAG'] * 2.5
                clean_df['HST'].fillna(clean_df['FTHG'] * 2.5, inplace=True)
                clean_df['AST'].fillna(clean_df['FTAG'] * 2.5, inplace=True)
                
                if date_col:
                    clean_df['Date'] = pd.to_datetime(df_temp[date_col], dayfirst=True, errors='coerce')
                    clean_df['Tage'] = (heute - clean_df['Date']).dt.days.fillna(60)
                    clean_df['Weight'] = np.exp(-0.005 * clean_df['Tage'])
                else: clean_df['Weight'] = 1.0
                    
                daten_liste.append(clean_df.dropna(subset=['FTHG', 'FTAG', 'HomeTeam', 'AwayTeam']))
            except: pass
            
        if not daten_liste: return None, None, None
        df_gesamt = pd.concat(daten_liste, ignore_index=True)
        
        liga_daten = {}
        alle_ligen = df_gesamt['Div'].unique()
        alle_teams = sorted(df_gesamt['HomeTeam'].unique().tolist())
        
        for liga in alle_ligen:
            df_liga = df_gesamt[df_gesamt['Div'] == liga]
            
            avg_fthg = weighted_avg(df_liga['FTHG'], df_liga['Weight'])
            avg_ftag = weighted_avg(df_liga['FTAG'], df_liga['Weight'])
            avg_hst = weighted_avg(df_liga['HST'], df_liga['Weight'])
            avg_ast = weighted_avg(df_liga['AST'], df_liga['Weight'])
            
            team_stats = {}
            for team in df_liga['HomeTeam'].unique():
                home = df_liga[df_liga['HomeTeam'] == team]
                away = df_liga[df_liga['AwayTeam'] == team]
                
                h_fthg = weighted_avg(home['FTHG'], home['Weight'])
                h_ftag = weighted_avg(home['FTAG'], home['Weight'])
                a_ftag = weighted_avg(away['FTAG'], away['Weight'])
                a_fthg = weighted_avg(away['FTHG'], away['Weight'])
                
                h_hst = weighted_avg(home['HST'], home['Weight'])
                h_ast = weighted_avg(home['AST'], home['Weight'])
                a_ast = weighted_avg(away['AST'], away['Weight'])
                a_hst = weighted_avg(away['HST'], away['Weight'])
                
                team_stats[team] = {
                    'FT_HA': (h_fthg / avg_fthg) if avg_fthg > 0 else 1,
                    'FT_HD': (h_ftag / avg_ftag) if avg_ftag > 0 else 1,
                    'FT_AA': (a_ftag / avg_ftag) if avg_ftag > 0 else 1,
                    'FT_AD': (a_fthg / avg_fthg) if avg_fthg > 0 else 1,
                    # Torschuss (Shots on Target) Ratings
                    'SOT_HA': (h_hst / avg_hst) if avg_hst > 0 else 1,
                    'SOT_HD': (h_ast / avg_ast) if avg_ast > 0 else 1,
                    'SOT_AA': (a_ast / avg_ast) if avg_ast > 0 else 1,
                    'SOT_AD': (a_hst / avg_hst) if avg_hst > 0 else 1,
                }
            liga_daten[liga] = {'avg_fthg': avg_fthg, 'avg_ftag': avg_ftag, 'team_stats': team_stats}
        return df_gesamt, liga_daten, alle_teams

    df_gesamt, liga_daten, alle_teams = lade_fussball_daten()
    if df_gesamt is None:
        st.error("❌ Keine Fußball-CSVs gefunden!")
        st.stop()

    st.caption(f"Aktive Ligen: {', '.join([str(k) for k in liga_daten.keys()])}")

    col1, col2 = st.columns(2)
    with col1: home_team = st.selectbox("Heimteam", alle_teams)
    with col2: away_team = st.selectbox("Auswärtsteam", alle_teams)

    st.write("#### 💰 Tipico Quoten-Eingabe (Für Value-Check)")
    q1, q2, q3 = st.columns(3)
    with q1: quote_1 = st.number_input("Quote 1 (Heim)", min_value=1.01, value=2.00, step=0.05)
    with q2: quote_x = st.number_input("Quote X (Remis)", min_value=1.01, value=3.40, step=0.05)
    with q3: quote_2 = st.number_input("Quote 2 (Auswärts)", min_value=1.01, value=3.50, step=0.05)

    if st.button("🚀 Match analysieren & Value finden", use_container_width=True):
        aktuelle_liga = next((l for l, d in liga_daten.items() if home_team in d['team_stats'] and away_team in d['team_stats']), None)
        if not aktuelle_liga: st.error("❌ Teams spielen nicht in derselben Liga.")
        else:
            liga = liga_daten[aktuelle_liga]
            s = liga['team_stats']
            
            # --- BLENDED RATINGS (75% Tore, 25% Torschüsse) ---
            eff_ha = (s[home_team]['FT_HA'] * 0.75) + (s[home_team]['SOT_HA'] * 0.25)
            eff_ad = (s[away_team]['FT_AD'] * 0.75) + (s[away_team]['SOT_AD'] * 0.25)
            eff_aa = (s[away_team]['FT_AA'] * 0.75) + (s[away_team]['SOT_AA'] * 0.25)
            eff_hd = (s[home_team]['FT_HD'] * 0.75) + (s[home_team]['SOT_HD'] * 0.25)
            
            ft_home_xg = max(0.1, eff_ha * eff_ad * liga['avg_fthg'])
            ft_away_xg = max(0.1, eff_aa * eff_hd * liga['avg_ftag'])
            
            ft_matrix = berechne_match_matrix_dixon_coles(ft_home_xg, ft_away_xg)
            
            home_win, draw, away_win = 0, 0, 0
            over25, btts_yes = 0, 0
            
            for i in range(6):
                for j in range(6):
                    p = ft_matrix[i, j]
                    if i > j: home_win += p
                    elif i == j: draw += p
                    else: away_win += p
                    if (i + j) > 2.5: over25 += p
                    if i > 0 and j > 0: btts_yes += p

            # True Odds & Value Check
            true_prob_1, true_prob_x, true_prob_2 = entferne_buchmacher_marge(quote_1, quote_x, quote_2)
            
            st.divider()
            st.subheader(f"📊 KI-Prognose vs. Buchmacher ({aktuelle_liga})")
            
            # Value Indikatoren
            val_1 = home_win / true_prob_1 if true_prob_1 > 0 else 0
            val_x = draw / true_prob_x if true_prob_x > 0 else 0
            val_2 = away_win / true_prob_2 if true_prob_2 > 0 else 0
            
            def render_metric(label, ki_prob, true_prob, value_ratio, quote):
                edge_text = f"🔥 EDGE! (+{(value_ratio-1)*100:.1f}%)" if value_ratio > 1.05 else ("⚠️ Kein Value" if value_ratio < 0.95 else "⚖️ Fair")
                st.metric(label, f"{ki_prob*100:.1f}% (KI)", f"{edge_text} | Wahre Quote: {1/max(0.0001, ki_prob):.2f}")

            c1, c2, c3 = st.columns(3)
            with c1: render_metric("Sieg 1", home_win, true_prob_1, val_1, quote_1)
            with c2: render_metric("Remis X", draw, true_prob_x, val_x, quote_x)
            with c3: render_metric("Sieg 2", away_win, true_prob_2, val_2, quote_2)
            
            st.write("---")
            c4, c5 = st.columns(2)
            c4.metric("Über 2.5 Tore", f"{over25*100:.1f}%", f"Fair: {1/max(0.0001, over25):.2f}")
            c5.metric("Beide treffen (BTTS)", f"{btts_yes*100:.1f}%", f"Fair: {1/max(0.0001, btts_yes):.2f}")

            if val_1 > 1.05 or val_x > 1.05 or val_2 > 1.05:
                st.success("✅ **System hat mathematischen Value gefunden!** Das Buchmacher-Modell unterschätzt diese Wahrscheinlichkeit, weil es Torschuss-Dominanz oder Formkurven ignoriert.")
                
            st.write("📰 **Live-News für dieses Match:**")
            news = hole_live_news(home_team, away_team)
            if news:
                for n in news: st.markdown(f"- [{n['titel']}]({n['link']})")
            else: st.caption("Keine News im Feed.")

# ==============================================================================
# SÄULE 2: WNBA BASKETBALL
# ==============================================================================
else:
    st.title("🏀 WNBA L9 Bet System")

    @st.cache_data
    def lade_wnba_daten():
        if not os.path.exists('wnba_stats.csv'): return "FEHLT", None
        try:
            df = pd.read_csv('wnba_stats.csv', sep=None, engine='python', encoding='utf-8')
            df.columns = [str(c).strip().upper() for c in df.columns]
            team_col = next((c for c in df.columns if c in ['TEAM', 'TEAM_NAME', 'NAME', 'MANNSCHAFT']), None)
            if not team_col: return "SPALTEN_FEHLER", None
                
            clean_df = pd.DataFrame()
            clean_df['Team'] = df[team_col].astype(str).str.strip()
            
            pts_col = next((c for c in df.columns if c in ['PTS', 'POINTS', 'PUNKTE']), None)
            opp_col = next((c for c in df.columns if c in ['OPP_PTS', 'OPP_POINTS', 'OPPTS']), None)
            pace_col = next((c for c in df.columns if c in ['PACE', 'SPEED']), None)
            
            if pts_col and opp_col and pace_col:
                clean_df['PTS'] = pd.to_numeric(df[pts_col], errors='coerce')
                clean_df['OPP_PTS'] = pd.to_numeric(df[opp_col], errors='coerce')
                clean_df['PACE'] = pd.to_numeric(df[pace_col], errors='coerce')
                return "EFFIZIENZ_MODELL", clean_df.dropna()
                
            wl_col = next((c for c in df.columns if c in ['W/L%', 'WIN%', 'PCT', 'WL%']), None)
            if wl_col:
                clean_df['WIN_PCT'] = pd.to_numeric(df[wl_col], errors='coerce')
                if clean_df['WIN_PCT'].max() > 1.0: clean_df['WIN_PCT'] /= 100.0
                return "BILANZ_MODELL", clean_df.dropna()
            return "SPALTEN_FEHLER", None
        except: return "ERROR", None

    modell_typ, wnba_df = lade_wnba_daten()
    if "ERROR" in str(modell_typ) or modell_typ in ["FEHLT", "SPALTEN_FEHLER"]:
        st.error(f"❌ WNBA Datenfehler: {modell_typ}")
        st.stop()

    teams_list = sorted(wnba_df['Team'].tolist())
    col1, col2 = st.columns(2)
    with col1: wnba_home = st.selectbox("Heimteam (WNBA)", teams_list, index=0)
    with col2: wnba_away = st.selectbox("Auswärtsteam (WNBA)", teams_list, index=1 if len(teams_list) > 1 else 0)

    news_home, auto_malus_home = scanne_wnba_injuries(wnba_home)
    news_away, auto_malus_away = scanne_wnba_injuries(wnba_away)

    with st.expander("🚨 KI-Verletzungs-Scanner & News (Live US-Märkte)", expanded=True):
        c_h, c_a = st.columns(2)
        with c_h:
            malus_home = st.number_input(f"Punkte-Abzug {wnba_home}", value=auto_malus_home, step=0.5, key="mh")
            if news_home:
                for n in news_home: st.caption(f"🔴 [{n['titel'][:40]}...]({n['link']})")
        with c_a:
            malus_away = st.number_input(f"Punkte-Abzug {wnba_away}", value=auto_malus_away, step=0.5, key="ma")
            if news_away:
                for n in news_away: st.caption(f"🔴 [{n['titel'][:40]}...]({n['link']})")

    st.write("---")
    st.write("#### Deine Tipico Buchmacher-Lines eintragen:")
    cx, cy = st.columns(2)
    with cx: tipico_total = st.number_input("Tipico Over/Under Linie (z.B. 162.5)", value=161.5, step=0.5)
    with cy: wnba_hc_str = st.text_input("Handicap-Format (z.B. 0:-3.5 oder -3.5:0)", value="-3.5:0")

    if st.button("🏀 WNBA Value berechnen", use_container_width=True):
        if modell_typ == "EFFIZIENZ_MODELL":
            avg_pts, avg_pace = wnba_df['PTS'].mean(), wnba_df['PACE'].mean()
            t_home = wnba_df[wnba_df['Team'] == wnba_home].iloc[0]
            t_away = wnba_df[wnba_df['Team'] == wnba_away].iloc[0]
            exp_pace = (t_home['PACE'] * t_away['PACE']) / avg_pace
            exp_pts_home = exp_pace * ((t_home['PTS']/t_home['PACE']) * (t_away['OPP_PTS']/t_away['PACE'])) / (avg_pts/avg_pace)
            exp_pts_away = exp_pace * ((t_away['PTS']/t_away['PACE']) * (t_home['OPP_PTS']/t_home['PACE'])) / (avg_pts/avg_pace)
        else:
            t_home = wnba_df[wnba_df['Team'] == wnba_home].iloc[0]
            t_away = wnba_df[wnba_df['Team'] == wnba_away].iloc[0]
            total_exp = 161.8
            diff_exp = 13.5 * (t_home['WIN_PCT'] - t_away['WIN_PCT']) + 2.5
            exp_pts_home = (total_exp / 2) + (diff_exp / 2)
            exp_pts_away = (total_exp / 2) - (diff_exp / 2)

        exp_pts_home -= malus_home
        exp_pts_away -= malus_away
        total_exp = exp_pts_home + exp_pts_away
        diff_exp = exp_pts_home - exp_pts_away
        
        sigma_spread, sigma_total = 10.5, 14.0
        
        hc_h_bonus, hc_a_bonus = parse_handicap(wnba_hc_str)
        netto_hc_hurde = hc_a_bonus - hc_h_bonus
        
        prob_home_win = norm_sf(0, diff_exp, sigma_spread)
        prob_over = norm_sf(tipico_total, total_exp, sigma_total)
        prob_hc_cover = norm_sf(netto_hc_hurde, diff_exp, sigma_spread)

        st.divider()
        st.subheader("🎯 Value-Prognose für deine Wetten")
        st.caption(f"Erwarteter Endstand: **{exp_pts_home:.1f} : {exp_pts_away:.1f}** (Gesamtpunkte: {total_exp:.1f})")
        
        c1, c2 = st.columns(2)
        c1.metric("Siegchance Heim (ML)", f"{prob_home_win*100:.1f}%", f"Fair: {1/max(0.0001, prob_home_win):.2f}")
        c2.metric("Siegchance Auswärts (ML)", f"{(1-prob_home_win)*100:.1f}%", f"Fair: {1/max(0.0001, 1-prob_home_win):.2f}")
        
        st.write("---")
        if prob_over > 0.53:
            st.success(f"🔥 **Value auf ÜBER {tipico_total}!** Chance: **{prob_over*100:.1f}%** (Fair: {1/prob_over:.2f})")
        elif prob_over < 0.47:
            st.success(f"🔥 **Value auf UNTER {tipico_total}!** Chance: **{(1-prob_over)*100:.1f}%** (Fair: {1/(1-prob_over):.2f})")
            
        if prob_hc_cover > 0.53:
            st.success(f"🔥 **Value auf Handicap {wnba_home} ({wnba_hc_str})!** Chance: **{prob_hc_cover*100:.1f}%**")
        elif prob_hc_cover < 0.47:
            st.success(f"🔥 **Value auf Handicap {wnba_away} (Gegenhandicap)!** Chance: **{(1-prob_hc_cover)*100:.1f}%**")
