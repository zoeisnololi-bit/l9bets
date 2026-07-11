import streamlit as st
import pandas as pd
import glob
import math
import warnings
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET

warnings.filterwarnings('ignore')

# --- HILFSFUNKTION: HANDICAP STRING PARSER ---
def parse_handicap(hc_str):
    """Zerlegt Formate wie '0:1', '1:0' oder '0:-1.5' in (Heim_Bonus, Auswaerts_Bonus)"""
    try:
        parts = hc_str.split(":")
        if len(parts) == 2:
            return float(parts[0].strip()), float(parts[1].strip())
    except:
        pass
    return 0.0, 0.0

# --- EIGENE MATHEMATISCHE FUNKTIONEN ---
def poisson_pmf(k, lamb):
    if lamb <= 0: return 0
    try:
        return (lamb**k * math.exp(-lamb)) / math.factorial(k)
    except:
        return 0

def norm_sf(x, mu, sigma):
    if sigma <= 0: sigma = 0.01
    z = (x - mu) / sigma
    try:
        return 0.5 * math.erfc(z / math.sqrt(2))
    except:
        return 0.5

# --- LIVE NEWS FETCHER (FUSSBALL - DEUTSCH) ---
def hole_live_news(team1, team2=None):
    try:
        suchbegriff = f"{team1} {team2}" if team2 else team1
        encoded_query = urllib.parse.quote(suchbegriff)
        url = f"https://news.google.com/rss/search?q={encoded_query}+sport&hl=de&gl=DE&ceid=DE:de"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=4) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        news_liste = []
        for item in root.findall('.//item')[:4]:
            titel = item.find('title').text
            link = item.find('link').text
            if " - " in titel:
                titel = titel.rsplit(" - ", 1)[0]
            news_liste.append({"titel": titel, "link": link})
        return news_liste
    except:
        return []

# --- KI INJURY SCANNER (WNBA - ENGLISCH US) ---
def scanne_wnba_injuries(team):
    try:
        encoded_query = urllib.parse.quote(f"{team} WNBA injury report")
        url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en&gl=US&ceid=US:en"
        
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        with urllib.request.urlopen(req, timeout=4) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        gefundene_meldungen = []
        berechneter_malus = 0.0
        
        harte_ausfaelle = ["out", "injury", "injured", "miss", "missing", "broken", "acl", "surgery", "sidelined"]
        fragliche_ausfaelle = ["questionable", "doubtful", "game-time", "gtd", "status"]
        
        for item in root.findall('.//item')[:3]:
            titel_orig = item.find('title').text
            titel_lower = titel_orig.lower()
            link = item.find('link').text
            
            if any(k in titel_lower for k in harte_ausfaelle):
                berechneter_malus += 3.0
                gefundene_meldungen.append({"titel": titel_orig, "link": link, "typ": "🔴 Bestätigter Ausfall / Verletzung"})
            elif any(k in titel_lower for k in fragliche_ausfaelle):
                berechneter_malus += 1.5
                gefundene_meldungen.append({"titel": titel_orig, "link": link, "typ": "🟡 Fraglich / Einsatz unsicher"})
                
        berechneter_malus = min(berechneter_malus, 7.0)
        return gefundene_meldungen, berechneter_malus
    except:
        return [], 0.0

# --- STREAMLIT CONFIG ---
st.set_page_config(page_title="L9 Bets Beta", page_icon="📈", layout="centered")

# --- SPORTARTAUSWAHL ---
sportart = st.sidebar.radio("Sportart wählen", ["⚽ Fußball (Minor Leagues)", "🏀 WNBA Basketball (CSV)"])

# ==============================================================================
# SÄULE 1: FUSSBALL (INKLUSIVE AUTOMATISCHER FAIREN QUOTE)
# ==============================================================================
if sportart == "⚽ Fußball (Minor Leagues)":
    st.title("⚽ Tipico Fußball-Analyst Pro")

    @st.cache_data
    def lade_fussball_daten():
        csv_dateien = [f for f in glob.glob('*.csv') if f != 'wnba_stats.csv']
        if not csv_dateien: return None, None, None
        
        daten_liste = []
        for datei in csv_dateien:
            try:
                df_temp = pd.read_csv(datei, sep=None, engine='python', encoding='utf-8')
                df_temp.columns = [str(c).strip().upper() for c in df_temp.columns]
                
                div_col = next((c for c in df_temp.columns if c in ['DIV', 'LEAGUE', 'LIGA', 'COUNTRY']), None)
                home_col = next((c for c in df_temp.columns if c in ['HOMETEAM', 'HOME', 'HEIM']), None)
                away_col = next((c for c in df_temp.columns if c in ['AWAYTEAM', 'AWAY', 'AUSWAERTS']), None)
                fthg_col = next((c for c in df_temp.columns if c in ['FTHG', 'HG', 'GOALSHOME', 'HOME_GOALS']), None)
                ftag_col = next((c for c in df_temp.columns if c in ['FTAG', 'AG', 'GOALSAWAY', 'AWAY_GOALS']), None)
                hthg_col = next((c for c in df_temp.columns if c in ['HTHG', 'HT_HG']), None)
                htag_col = next((c for c in df_temp.columns if c in ['HTAG', 'HT_AG']), None)
                
                if not all([home_col, away_col, fthg_col, ftag_col]): continue
                    
                clean_df = pd.DataFrame()
                if div_col:
                    clean_df['Div'] = df_temp[div_col].astype(str).str.strip()
                else:
                    clean_df['Div'] = os.path.splitext(os.path.basename(datei))[0].upper()
                    
                clean_df['HomeTeam'] = df_temp[home_col].astype(str).str.strip()
                clean_df['AwayTeam'] = df_temp[away_col].astype(str).str.strip()
                clean_df['FTHG'] = pd.to_numeric(df_temp[fthg_col], errors='coerce')
                clean_df['FTAG'] = pd.to_numeric(df_temp[ftag_col], errors='coerce')
                
                if hthg_col:
                    clean_df['HTHG'] = pd.to_numeric(df_temp[hthg_col], errors='coerce')
                else:
                    clean_df['HTHG'] = (clean_df['FTHG'] * 0.42).round()
                    
                if htag_col:
                    clean_df['HTAG'] = pd.to_numeric(df_temp[htag_col], errors='coerce')
                else:
                    clean_df['HTAG'] = (clean_df['FTAG'] * 0.42).round()
                    
                daten_liste.append(clean_df.dropna())
            except: pass
            
        if not daten_liste: return None, None, None
        df_gesamt = pd.concat(daten_liste, ignore_index=True)
        
        liga_daten = {}
        alle_ligen = df_gesamt['Div'].unique()
        alle_teams = sorted(df_gesamt['HomeTeam'].unique().tolist())
        
        for liga in alle_ligen:
            df_liga = df_gesamt[df_gesamt['Div'] == liga]
            avg_fthg, avg_ftag = df_liga['FTHG'].mean(), df_liga['FTAG'].mean()
            avg_hthg, avg_htag = df_liga['HTHG'].mean(), df_liga['HTAG'].mean()
            
            team_stats = {}
            for team in df_liga['HomeTeam'].unique():
                home = df_liga[df_liga['HomeTeam'] == team]
                away = df_liga[df_liga['AwayTeam'] == team]
                team_stats[team] = {
                    'FT_HA': (home['FTHG'].mean() / avg_fthg) if avg_fthg > 0 else 1,
                    'FT_HD': (home['FTAG'].mean() / avg_ftag) if avg_ftag > 0 else 1,
                    'FT_AA': (away['FTAG'].mean() / avg_ftag) if avg_ftag > 0 else 1,
                    'FT_AD': (away['FTHG'].mean() / avg_fthg) if avg_fthg > 0 else 1,
                    'HT_HA': (home['HTHG'].mean() / avg_hthg) if avg_hthg > 0 else 1,
                    'HT_HD': (home['HTAG'].mean() / avg_htag) if avg_htag > 0 else 1,
                    'HT_AA': (away['HTAG'].mean() / avg_htag) if avg_htag > 0 else 1,
                    'HT_AD': (away['HTHG'].mean() / avg_hthg) if avg_hthg > 0 else 1,
                }
            liga_daten[liga] = {'avg_fthg': avg_fthg, 'avg_ftag': avg_ftag, 'avg_hthg': avg_hthg, 'avg_htag': avg_htag, 'team_stats': team_stats}
        return df_gesamt, liga_daten, alle_teams

    df_gesamt, liga_daten, alle_teams = lade_fussball_daten()
    if df_gesamt is None:
        st.error("❌ Keine Fußball-CSVs gefunden!")
        st.stop()

    st.caption(f"Aktive Ligen: {', '.join(list(liga_daten.keys()))}")

    col1, col2 = st.columns(2)
    with col1: home_team = st.selectbox("Heimteam", alle_teams)
    with col2: away_team = st.selectbox("Auswärtsteam", alle_teams)

    fb_hc_str = st.text_input("Fußball Handicap-Format (z.B. 0:1, 1:0, 0:-1.5)", value="0:1")

    if st.button("🚀 Fußball Komplettprognose", use_container_width=True):
        aktuelle_liga = next((l for l, d in liga_daten.items() if home_team in d['team_stats'] and away_team in d['team_stats']), None)
        if not aktuelle_liga:
            st.error("❌ Teams spielen nicht in derselben Liga.")
        else:
            liga = liga_daten[aktuelle_liga]
            s = liga['team_stats']
            
            ht_home_xg = s[home_team]['HT_HA'] * s[away_team]['HT_AD'] * liga['avg_hthg']
            ht_away_xg = s[away_team]['HT_AA'] * s[home_team]['HT_HD'] * liga['avg_htag']
            ft_home_xg = s[home_team]['FT_HA'] * s[away_team]['FT_AD'] * liga['avg_fthg']
            ft_away_xg = s[away_team]['FT_AA'] * s[home_team]['FT_HD'] * liga['avg_ftag']
            
            sh_home_xg, sh_away_xg = max(0.01, ft_home_xg - ht_home_xg), max(0.01, ft_away_xg - ht_away_xg)
            
            home_win, draw, away_win = 0, 0, 0
            ht_home_win, ht_draw, ht_away_win = 0, 0, 0
            hc_home_win, hc_draw, hc_away_win = 0, 0, 0
            over25, btts_yes = 0, 0
            
            hc_home_bonus, hc_away_bonus = parse_handicap(fb_hc_str)
            
            for i in range(6):
                p_ht_h = poisson_pmf(i, ht_home_xg)
                for j in range(6):
                    p_ht = p_ht_h * poisson_pmf(j, ht_away_xg)
                    
                    if i > j: ht_home_win += p_ht
                    elif i == j: ht_draw += p_ht
                    else: ht_away_win += p_ht
                    
                    for k in range(6):
                        p_sh_h = poisson_pmf(k, sh_home_xg)
                        for l in range(6):
                            p_full = p_ht * p_sh_h * poisson_pmf(l, sh_away_xg)
                            
                            f_h, f_a = i + k, j + l
                            
                            if f_h > f_a: home_win += p_full
                            elif f_h == f_a: draw += p_full
                            else: away_win += p_full
                            
                            v_h = f_h + hc_home_bonus
                            v_a = f_a + hc_away_bonus
                            if abs(v_h - v_a) < 1e-5: hc_draw += p_full
                            elif v_h > v_a: hc_home_win += p_full
                            else: hc_away_win += p_full
                            
                            if (f_h + f_a) > 2.5: over25 += p_full
                            if f_h > 0 and f_a > 0: btts_yes += p_full

            st.divider()
            
            # Helper für Division-Safe faire Quote
            def fq(p): return f"Fair: {1/max(0.0001, p):.2f}"
            
            # 1. Vollzeit 3-Way & Doppelte Chance
            st.subheader(f"📊 Vollzeit-Prognose ({aktuelle_liga})")
            c1, c2, c3 = st.columns(3)
            c1.metric("Sieg 1", f"{home_win*100:.1f}%", fq(home_win))
            c2.metric("Remis X", f"{draw*100:.1f}%", fq(draw))
            c3.metric("Sieg 2", f"{away_win*100:.1f}%", fq(away_win))
            
            st.markdown("**Doppelte Chance:**")
            dc1, dc2, dc3 = st.columns(3)
            dc1.metric("1X (Heim oder Remis)", f"{(home_win + draw)*100:.1f}%", fq(home_win + draw))
            dc2.metric("12 (Kein Remis)", f"{(home_win + away_win)*100:.1f}%", fq(home_win + away_win))
            dc3.metric("X2 (Remis oder Auswärts)", f"{(draw + away_win)*100:.1f}%", fq(draw + away_win))
            
            # 2. Halbzeit-Prognosen
            st.write("---")
            st.subheader("⏱️ Halbzeit-Prognose (1. Halbzeit)")
            hc1, hc2, hc3 = st.columns(3)
            hc1.metric("HT Sieg 1", f"{ht_home_win*100:.1f}%", fq(ht_home_win))
            hc2.metric("HT Remis X", f"{ht_draw*100:.1f}%", fq(ht_draw))
            hc3.metric("HT Sieg 2", f"{ht_away_win*100:.1f}%", fq(ht_away_win))
            
            # 3. Handicap Prognose
            st.write("---")
            st.subheader(f"🎯 Handicap-Prognose (Format: {fb_hc_str})")
            hcc1, hcc2, hcc3 = st.columns(3)
            hcc1.metric("HC Sieg 1", f"{hc_home_win*100:.1f}%", fq(hc_home_win))
            if hc_draw > 0.005:
                hcc2.metric("HC Remis X", f"{hc_draw*100:.1f}%", fq(hc_draw))
            else:
                hcc2.metric("HC Remis X", "0.0% (2-Way)", "Fair: N/A")
            hcc3.metric("HC Sieg 2", f"{hc_away_win*100:.1f}%", fq(hc_away_win))

            # Tore Märkte
            st.write("---")
            c4, c5 = st.columns(2)
            c4.metric("Über 2.5 Tore", f"{over25*100:.1f}%", fq(over25))
            c5.metric("Beide treffen (BTTS)", f"{btts_yes*100:.1f}%", fq(btts_yes))
            
            st.write("---")
            st.write("📰 **Live-News für dieses Match:**")
            news = hole_live_news(home_team, away_team)
            if news:
                for n in news: st.markdown(f"- [{n['titel']}]({n['link']})")
            else: st.caption("Keine News im Feed.")

# ==============================================================================
# SÄULE 2: WNBA BASKETBALL
# ==============================================================================
else:
    st.title("🏀 WNBA Buchmacher-Analyst (KI-Injury Update)")

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
