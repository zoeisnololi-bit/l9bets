import streamlit as st
import pandas as pd
import glob
import math
import warnings
import os
warnings.filterwarnings('ignore')

# --- EIGENE MATHEMATISCHE FUNKTIONEN (ERSETZT SCIPY KOMPLETT) ---
def poisson_pmf(k, lamb):
    """Berechnet die Poisson-Wahrscheinlichkeit ohne scipy."""
    if lamb <= 0: return 0
    try:
        return (lamb**k * math.exp(-lamb)) / math.factorial(k)
    except:
        return 0

def norm_sf(x, mu, sigma):
    """Berechnet die Normalverteilung (Survival Function / Über-Wahrscheinlichkeit) ohne scipy."""
    if sigma <= 0: sigma = 0.01
    z = (x - mu) / sigma
    try:
        # Nutzen der eingebauten math.erfc Funktion für präzise Wahrscheinlichkeiten
        return 0.5 * math.erfc(z / math.sqrt(2))
    except:
        return 0.5

# --- STREAMLIT CONFIG ---
st.set_page_config(page_title="L9 Bets", page_icon="📈", layout="centered")

# --- SPORTARTAUSWAHL ---
sportart = st.sidebar.radio("Sportart wählen", ["⚽ Fußball (Minor Leagues)", "🏀 WNBA Basketball (CSV)"])

# ==============================================================================
# SÄULE 1: FUSSBALL (POISSON-MODELL)
# ==============================================================================
if sportart == "⚽ Fußball (Minor Leagues)":
    st.title("⚽ Tipico Fußball-Analyst (Minor Leagues)")
    st.markdown("Fokus: Griechenland, Dänemark, Irland, Mexiko, Schweden, Norwegen")

    @st.cache_data
    def lade_fussball_daten():
        csv_dateien = [f for f in glob.glob('*.csv') if f != 'wnba_stats.csv']
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
                    'HT_AD': (away['HTHG'].mean() / avg_htag) if avg_htag > 0 else 1,
                }
            liga_daten[liga] = {'avg_fthg': avg_fthg, 'avg_ftag': avg_ftag, 'avg_hthg': avg_hthg, 'avg_htag': avg_htag, 'team_stats': team_stats}
        return df_gesamt, liga_daten, alle_teams

    df_gesamt, liga_daten, alle_teams = lade_fussball_daten()
    if df_gesamt is None:
        st.error("❌ Keine Fußball-CSV-Dateien im Ordner gefunden!")
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
                p_ht_h = poisson_pmf(i, ht_home_xg)
                for j in range(6):
                    p_ht = p_ht_h * poisson_pmf(j, ht_away_xg)
                    for k in range(6):
                        p_sh_h = poisson_pmf(k, sh_home_xg)
                        for l in range(6):
                            p_full = p_ht * p_sh_h * poisson_pmf(l, sh_away_xg)
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
# SÄULE 2: WNBA BASKETBALL (INTELLIGENTES HYBRID-MODELL FÜR JEDE CSV)
# ==============================================================================
else:
    st.title("🏀 WNBA Buchmacher-Analyst (Hybrid-Version)")

    @st.cache_data
    def lade_wnba_daten():
        if not os.path.exists('wnba_stats.csv'):
            return "FEHLT", None
        try:
            df = pd.read_csv('wnba_stats.csv', sep=None, engine='python', encoding='utf-8')
            df.columns = [str(c).strip().upper() for c in df.columns]
            
            team_col = next((c for c in df.columns if c in ['TEAM', 'TEAM_NAME', 'NAME', 'MANNSCHAFT']), None)
            if not team_col:
                return "SPALTEN_FEHLER", None
                
            clean_df = pd.DataFrame()
            clean_df['Team'] = df[team_col].astype(str).str.strip()
            
            # Prüfen, ob detaillierte Punkte-Statistiken vorliegen
            pts_col = next((c for c in df.columns if c in ['PTS', 'POINTS', 'PUNKTE']), None)
            opp_col = next((c for c in df.columns if c in ['OPP_PTS', 'OPP_POINTS', 'OPPTS']), None)
            pace_col = next((c for c in df.columns if c in ['PACE', 'SPEED']), None)
            
            if pts_col and opp_col and pace_col:
                clean_df['PTS'] = pd.to_numeric(df[pts_col], errors='coerce')
                clean_df['OPP_PTS'] = pd.to_numeric(df[opp_col], errors='coerce')
                clean_df['PACE'] = pd.to_numeric(df[pace_col], errors='coerce')
                return "EFFIZIENZ_MODELL", clean_df.dropna()
                
            # Fallback für historische Tabellen (wie aus Screenshot 5.PNG: W, L, W/L%)
            wl_col = next((c for c in df.columns if c in ['W/L%', 'WIN%', 'PCT', 'WL%']), None)
            w_col = next((c for c in df.columns if c in ['W', 'WINS', 'SIEGE']), None)
            g_col = next((c for c in df.columns if c in ['G', 'GAMES', 'SPIELE']), None)
            
            if wl_col:
                clean_df['WIN_PCT'] = pd.to_numeric(df[wl_col], errors='coerce')
                # Falls Prozentwerte als 46.1 statt 0.461 gespeichert sind
                if clean_df['WIN_PCT'].max() > 1.0: clean_df['WIN_PCT'] /= 100.0
                return "BILANZ_MODELL", clean_df.dropna()
            elif w_col and g_col:
                w = pd.to_numeric(df[w_col], errors='coerce').fillna(0)
                g = pd.to_numeric(df[g_col], errors='coerce').fillna(1)
                clean_df['WIN_PCT'] = w / g.replace(0, 1)
                return "BILANZ_MODELL", clean_df.dropna()
                
            return "SPALTEN_FEHLER", None
        except Exception as e:
            return f"ERROR: {str(e)}", None

    modell_typ, wnba_df = lade_wnba_daten()

    if "ERROR" in str(modell_typ):
        st.error(f"❌ Fehler beim Laden: {modell_typ}")
        st.stop()
    elif modell_typ == "FEHLT":
        st.error("❌ `wnba_stats.csv` wurde nicht im Hauptordner gefunden.")
        st.stop()
    elif modell_typ == "SPALTEN_FEHLER":
        st.error("❌ Spalten-Konflikt! Die App konnte weder Punkte- noch Sieg-Statistiken zuordnen.")
        st.info("Bitte benenne die Teamspalte in deiner CSV zu 'Team' um und stelle sicher, dass 'W' und 'G' oder 'W/L%' existieren.")
        st.stop()

    # Visueller Hinweis für den Nutzer, welcher Modus läuft
    if modell_typ == "BILANZ_MODELL":
        st.info("ℹ️ Historischer Bilanz-Modus aktiv (Berechnung basiert auf Win-Loss-Daten deiner Tabelle).")
    else:
        st.success("🎯 Erweitertes Effizienz-Modell aktiv (Punkte- & Pace-Statistiken erkannt).")

    teams_list = sorted(wnba_df['Team'].tolist())
    col1, col2 = st.columns(2)
    with col1: wnba_home = st.selectbox("Heimteam (WNBA)", teams_list, index=0)
    with col2: wnba_away = st.selectbox("Auswärtsteam (WNBA)", teams_list, index=1 if len(teams_list) > 1 else 0)

    st.write("---")
    st.write("#### Deine Tipico Buchmacher-Lines eintragen:")
    cx, cy = st.columns(2)
    with cx: tipico_total = st.number_input("Tipico Over/Under Linie (z.B. 162.5)", value=161.5, step=0.5)
    with cy: tipico_hc = st.number_input("Handicap Linie fürs Heimteam (z.B. -3.5)", value=-3.5, step=0.5)

    if st.button("🏀 WNBA Value berechnen", use_container_width=True):
        if modell_typ == "EFFIZIENZ_MODELL":
            avg_pts = wnba_df['PTS'].mean()
            avg_pace = wnba_df['PACE'].mean()
            t_home = wnba_df[wnba_df['Team'] == wnba_home].iloc[0]
            t_away = wnba_df[wnba_df['Team'] == wnba_away].iloc[0]
            
            exp_pace = (t_home['PACE'] * t_away['PACE']) / avg_pace
            home_off, home_def = t_home['PTS'] / t_home['PACE'], t_home['OPP_PTS'] / t_home['PACE']
            away_off, away_def = t_away['PTS'] / t_away['PACE'], t_away['OPP_PTS'] / t_away['PACE']
            league_eff = avg_pts / avg_pace
            
            exp_pts_home = exp_pace * (home_off * away_def) / league_eff
            exp_pts_away = exp_pace * (away_off * home_def) / league_eff
        else:
            # BILANZ-MODELL (Maßgeschneidert für Screenshot 5.PNG)
            t_home = wnba_df[wnba_df['Team'] == wnba_home].iloc[0]
            t_away = wnba_df[wnba_df['Team'] == wnba_away].iloc[0]
            
            home_pct = t_home['WIN_PCT']
            away_pct = t_away['WIN_PCT']
            
            # WNBA-Durchschnittswerte als stabiler mathematischer Anker
            total_exp = 161.8 
            # Errechnet den erwarteten Punkte-Abstand anhand der Win-Verhältnisse + Heimvorteil (+2.5 Punkte)
            diff_exp = 13.5 * (home_pct - away_pct) + 2.5
            
            exp_pts_home = (total_exp / 2) + (diff_exp / 2)
            exp_pts_away = (total_exp / 2) - (diff_exp / 2)

        total_exp = exp_pts_home + exp_pts_away
        diff_exp = exp_pts_home - exp_pts_away
        
        sigma_spread, sigma_total = 10.5, 14.0
        
        prob_home_win = norm_sf(0, diff_exp, sigma_spread)
        prob_over = norm_sf(tipico_total, total_exp, sigma_total)
        prob_hc_cover = norm_sf(-tipico_hc, diff_exp, sigma_spread)

        st.divider()
        st.subheader("🎯 Value-Prognose für deine Wetten")
        st.caption(f"Erwarteter Endstand: **{exp_pts_home:.1f} : {exp_pts_away:.1f}** (Gesamtpunkte: {total_exp:.1f})")
        
        c1, c2 = st.columns(2)
        c1.metric("Siegchance Heim (Moneyline)", f"{prob_home_win*100:.1f}%", f"Fair: {100/(prob_home_win*100+0.01):.2f}")
        c2.metric("Siegchance Auswärts (Moneyline)", f"{(1-prob_home_win)*100:.1f}%", f"Fair: {100/((1-prob_home_win)*100+0.01):.2f}")
        
        st.write("---")
        st.write("#### Abgleich mit deinen Tipico-Quoten:")
        
        if prob_over > 0.53:
            st.success(f"🔥 **Value auf ÜBER {tipico_total}!** Wahrscheinlichkeit: **{prob_over*100:.1f}%** (Faire Quote: {1/prob_over:.2f})")
        elif prob_over < 0.47:
            st.success(f"🔥 **Value auf UNTER {tipico_total}!** Wahrscheinlichkeit: **{(1-prob_over)*100:.1f}%** (Faire Quote: {1/(1-prob_over):.2f})")
        else:
            st.info(f"⚪ Linie {tipico_total} ist stabil quotiert ({prob_over*100:.1f}% Über). Kein Value.")
            
        if prob_hc_cover > 0.53:
            st.success(f"🔥 **Value auf Handicap {wnba_home} ({tipico_hc})!** Chance: **{prob_hc_cover*100:.1f}%**")
        elif prob_hc_cover < 0.47:
            st.success(f"🔥 **Value auf Handicap {wnba_away} (+{-tipico_hc})!** Chance: **{(1-prob_hc_cover)*100:.1f}%**")
