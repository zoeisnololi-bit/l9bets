import streamlit as st
import pandas as pd
import glob
from scipy.stats import poisson, norm
import warnings
warnings.filterwarnings('ignore')

# --- CONFIG ---
st.set_page_config(page_title="L9 Bets", page_icon="📈", layout="centered")

# --- SPORTARTAUSWAHL ---
sportart = st.sidebar.radio("Sportart wählen", ["⚽ Fußball (Minor Leagues)", "🏀 WNBA Basketball"])

# ==============================================================================
# SÄULE 1: FUSSBALL (POISSON-MODELL)
# ==============================================================================
if sportart == "⚽ Fußball (Minor Leagues)":
    st.title("⚽ Tipico Fußball-Analyst (Minor Leagues)")
    st.markdown("Fokus: Griechenland, Dänemark, Irland, Mexiko, Schweden, Norwegen")

    @st.cache_data
    def lade_fussball_daten():
        csv_dateien = glob.glob('*.csv')
        if not csv_dateien: return None, None, None
        daten_liste = []
        for datei in csv_dateien:
            try:
                df_temp = pd.read_csv(datei, encoding='utf-8')
                benoetigte = ['Div', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'HTHG', 'HTAG']
                df_temp = df_temp[[c for c in benoetigte if c in df_temp.columns]]
                daten_liste.append(df_temp)
            except: pass
        if not daten_liste: return None, None, None
        df_gesamt = pd.concat(daten_liste, ignore_index=True).dropna()
        
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
        st.error("❌ Keine CSV-Dateien im Ordner gefunden! Lade die Dateien für Griechenland (G1), Schweden, Norwegen etc. hoch.")
        st.stop()

    col1, col2 = st.columns(2)
    with col1: home_team = st.selectbox("Heimteam", alle_teams)
    with col2: away_team = st.selectbox("Auswärtsteam", alle_teams)

    if st.button("🚀 Fußball Prognose berechnen", use_container_width=True):
        aktuelle_liga = next((l for l, d in liga_daten.items() if home_team in d['team_stats'] and away_team in d['team_stats']), None)
        if not aktuelle_liga:
            st.error("❌ Teams spielen nicht in derselben Liga oder Daten fehlen.")
        else:
            liga = liga_daten[aktuelle_liga]
            s = liga['team_stats']
            
            ht_home_xg = s[home_team]['HT_HA'] * s[away_team]['HT_AD'] * liga['avg_hthg']
            ht_away_xg = s[away_team]['HT_AA'] * s[home_team]['HT_HD'] * liga['avg_htag']
            ft_home_xg = s[home_team]['FT_HA'] * s[away_team]['FT_AD'] * liga['avg_fthg']
            ft_away_xg = s[away_team]['FT_AA'] * s[home_team]['FT_HD'] * liga['avg_ftag']
            
            sh_home_xg, sh_away_xg = max(0.01, ft_home_xg - ht_home_xg), max(0.01, ft_away_xg - ht_away_xg)
            
            home_win, draw, away_win, over25, btts_yes = 0, 0, 0, 0, 0
            for i in range(6):
                p_ht_h = poisson.pmf(i, ht_home_xg)
                for j in range(6):
                    p_ht = p_ht_h * poisson.pmf(j, ht_away_xg)
                    for k in range(6):
                        p_sh_h = poisson.pmf(k, sh_home_xg)
                        for l in range(6):
                            p_full = p_ht * p_sh_h * poisson.pmf(l, sh_away_xg)
                            f_h, f_a = i + k, j + l
                            if f_h > f_a: home_win += p_full
                            elif f_h == f_a: draw += p_full
                            else: away_win += p_full
                            if (f_h + f_a) > 2.5: over25 += p_full
                            if f_h > 0 and f_a > 0: btts_yes += p_full

            st.divider()
            st.subheader(f"📊 Ergebnis-Wahrscheinlichkeiten ({aktuelle_liga})")
            c1, c2, c3 = st.columns(3)
            c1.metric("Sieg 1", f"{home_win*100:.1f}%")
            c2.metric("Remis X", f"{draw*100:.1f}%")
            c3.metric("Sieg 2", f"{away_win*100:.1f}%")
            
            c4, c5 = st.columns(2)
            c4.metric("Über 2.5 Tore", f"{over25*100:.1f}%")
            c5.metric("Beide treffen (BTTS)", f"{btts_yes*100:.1f}%")

# ==============================================================================
# SÄULE 2: WNBA BASKETBALL (EFFIZIENZ & GAUSS-MODELL)
# ==============================================================================
else:
    st.title("🏀 WNBA Buchmacher-Zerstörer")
    st.markdown("Nutzt Live-Effizienzdaten & Pace-Berechnungen (Normalverteilung).")

    @st.cache_data(ttl=3600) # Aktualisiert die API-Daten jede Stunde neu
    def lade_wnba_daten():
        try:
            from nba_api.stats.endpoints import leaguedashteamstats
            # Holt die echten WNBA Daten der aktuellen Saison ('10' steht für die WNBA)
            raw_stats = leaguedashteamstats.LeagueDashTeamStats(league_id='10', season='2026').get_data_frames()[0]
            
            df = pd.DataFrame()
            df['Team'] = raw_stats['TEAM_NAME']
            df['PTS'] = raw_stats['PTS'] / raw_stats['GP']       # Punkte pro Spiel
            df['OPP_PTS'] = raw_stats['OPP_PTS'] / raw_stats['GP'] # Kassierte Punkte pro Spiel
            df['PACE'] = raw_stats['PACE']                       # Angriffe pro Spiel
            return df
        except Exception as e:
            # Sicherheits-Fallback falls NBA.com den Server kurzzeitig blockiert
            st.warning("⚠️ Live-API temporär überlastet. Nutze historische Durchschnitts-Matrix.")
            teams = ['New York Liberty', 'Las Vegas Aces', 'Connecticut Sun', 'Minnesota Lynx', 
                     'Seattle Storm', 'Indiana Fever', 'Phoenix Mercury', 'Atlanta Dream', 
                     'Chicago Sky', 'Los Angeles Sparks', 'Dallas Wings', 'Washington Mystics']
            return pd.DataFrame({
                'Team': teams, 'PTS': [85.4, 88.2, 80.1, 82.3, 83.5, 81.2, 82.0, 79.5, 80.8, 78.9, 81.5, 76.4],
                'OPP_PTS': [79.2, 80.5, 74.8, 76.1, 78.9, 84.1, 83.2, 81.0, 82.1, 83.4, 84.9, 81.8],
                'PACE': [78.2, 80.1, 76.5, 77.9, 78.5, 81.0, 79.8, 78.1, 79.0, 78.6, 79.9, 77.2]
            })

    wnba_df = lade_wnba_daten()
    teams_list = sorted(wnba_df['Team'].tolist())

    col1, col2 = st.columns(2)
    with col1: wnba_home = st.selectbox("Heimteam (WNBA)", teams_list, index=0)
    with col2: wnba_away = st.selectbox("Auswärtsteam (WNBA)", teams_list, index=1)

    st.write("---")
    st.write("#### Deine Tipico Buchmacher-Lines eintragen:")
    cx, cy = st.columns(2)
    with cx: tipico_total = st.number_input("Tipico Over/Under Linie (z.B. 162.5)", value=161.5, step=0.5)
    with cy: tipico_hc = st.number_input("Handicap Linie fürs Heimteam (z.B. -4.5)", value=-3.5, step=0.5)

    if st.button("🏀 WNBA Value berechnen", use_container_width=True):
        # Liga-Schnitt
        avg_pts = wnba_df['PTS'].mean()
        avg_pace = wnba_df['PACE'].mean()
        
        # Teamwerte isolieren
        t_home = wnba_df[wnba_df['Team'] == wnba_home].iloc[0]
        t_away = wnba_df[wnba_df['Team'] == wnba_away].iloc[0]
        
        # Berechnung des erwarteten Speeds (Pace)
        exp_pace = (t_home['PACE'] * t_away['PACE']) / avg_pace
        
        # Offensiv- & Defensiv-Ratings (Punkte pro Ballbesitz)
        home_off = t_home['PTS'] / t_home['PACE']
        home_def = t_home['OPP_PTS'] / t_home['PACE']
        away_off = t_away['PTS'] / t_away['PACE']
        away_def = t_away['OPP_PTS'] / t_away['PACE']
        league_eff = avg_pts / avg_pace
        
        # Erwartete Punkte
        exp_pts_home = exp_pace * (home_off * away_def) / league_eff
        exp_pts_away = exp_pace * (away_off * home_def) / league_eff
        
        # Mathematische Projektionen
        total_exp = exp_pts_home + exp_pts_away
        diff_exp = exp_pts_home - exp_pts_away # Positiv = Heimsieg, Negativ = Auswärtssieg
        
        # WNBA Standardabweichungen (Standard in der Analytik: 10.5 für Spread, 14.0 für Totals)
        sigma_spread = 10.5
        sigma_total = 14.0
        
        # Wahrscheinlichkeiten berechnen über Gauß-Normalverteilung
        prob_home_win = norm.sf(0, loc=diff_exp, scale=sigma_spread)
        prob_over = norm.sf(tipico_total, loc=total_exp, scale=sigma_total)
        prob_hc_cover = norm.sf(-tipico_hc, loc=diff_exp, scale=sigma_spread)

        # --- CODE AUSGABE ---
        st.divider()
        st.subheader("🎯 Value-Prognose für deine Wetten")
        st.caption(f"Erwarteter Endstand: **{exp_pts_home:.1f} : {exp_pts_away:.1f}** (Gesamtpunkte: {total_exp:.1f})")
        
        c1, c2 = st.columns(2)
        c1.metric("Siegchance Heim (Moneyline)", f"{prob_home_win*100:.1f}%", f"Fair: {100/(prob_home_win*100+0.01):.2f}")
        c2.metric("Siegchance Auswärts (Moneyline)", f"{(1-prob_home_win)*100:.1f}%", f"Fair: {100/((1-prob_home_win)*100+0.01):.2f}")
        
        st.write("---")
        st.write("#### Abgleich mit deinen Tipico-Quoten:")
        
        # Over / Under Matcher
        if prob_over > 0.53:
            st.success(f"🔥 **Value auf ÜBER {tipico_total}!** Wahrscheinlichkeit: **{prob_over*100:.1f}%** (Faire Quote: {1/prob_over:.2f})")
        elif prob_over < 0.47:
            st.success(f"🔥 **Value auf UNTER {tipico_total}!** Wahrscheinlichkeit: **{(1-prob_over)*100:.1f}%** (Faire Quote: {1/(1-prob_over):.2f})")
        else:
            st.info(f"⚪ Linie {tipico_total} ist genau richtig quotiert ({prob_over*100:.1f}% Über). Kein Value.")
            
        # Handicap Matcher
        if prob_hc_cover > 0.53:
            st.success(f"🔥 **Value auf Handicap {wnba_home} ({tipico_hc})!** Chance: **{prob_hc_cover*100:.1f}%**")
        elif prob_hc_cover < 0.47:
            st.success(f"🔥 **Value auf Handicap {wnba_away} (+{-tipico_hc})!** Chance: **{(1-prob_hc_cover)*100:.1f}%**")
