import streamlit as st
import pandas as pd
import os
import math

st.set_page_config(page_title="WNBA Value Analyst", page_icon="🏀", layout="centered")

st.title("🏀 WNBA Value Analyst Pro")
st.caption("Mit dynamischer Wahrscheinlichkeitsberechnung für Handicap & Over/Under")

# --- 1. DATEN LADEN (Der "kugelsichere" Loader) ---
@st.cache_data
def lade_wnba_daten():
    if not os.path.exists('wnba_stats.csv'): return "FEHLT", None
    try:
        df = pd.read_csv('wnba_stats.csv', encoding='utf-8')
        
        # Verrutschte Header erkennen und reparieren
        if 'Team' not in df.columns and 'TEAM' not in [str(c).upper() for c in df.columns]:
            for i in range(5):
                row_vals = [str(x).strip().upper() for x in df.iloc[i].values]
                if 'TEAM' in row_vals and 'PTS' in row_vals:
                    df.columns = df.iloc[i] 
                    df = df[i+1:].reset_index(drop=True)
                    break
                    
        df.columns = [str(c).strip().upper() for c in df.columns]
            
        team_col = next((c for c in df.columns if c in ['TEAM', 'TEAM_NAME', 'NAME', 'MANNSCHAFT']), None)
        pts_col = next((c for c in df.columns if c in ['PTS', 'POINTS', 'PUNKTE']), None)
        opp_col = next((c for c in df.columns if c in ['OPP_PTS', 'OPP_POINTS', 'OPPTS']), None)
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
    except Exception as e: 
        return "ERROR", None

status, wnba_df = lade_wnba_daten()

if wnba_df is None: 
    st.error("Daten-Ladefehler. Bitte lade eine gültige wnba_stats.csv mit 'Team' und 'PTS' hoch.")
    st.stop()

# --- 2. USER INTERFACE ---
teams_list = sorted(wnba_df['Team'].tolist())
c1, c2 = st.columns(2)
wnba_home = c1.selectbox("Heimteam", teams_list, index=0)
wnba_away = c2.selectbox("Auswärtsteam", teams_list, index=1 if len(teams_list)>1 else 0)

st.write("#### ✈️ Schedule & Fatigue")
col_a, col_b = st.columns(2)
rest_home = col_a.slider("Pause Heimteam (Tage)", 0, 5, 2)
rest_away = col_b.slider("Pause Auswärtsteam (Tage)", 0, 5, 2)

st.write("#### 💰 Buchmacher-Linien")
q_col1, q_col2 = st.columns(2)
b_spread = q_col1.number_input("Handicap Heimteam (z.B. -3.5)", value=-3.5, step=0.5)
b_total = q_col2.number_input("Over/Under Linie", value=165.5, step=0.5)

# --- 3. BERECHNUNG & AUSGABE ---
if st.button("🚀 Wahrscheinlichkeiten berechnen", use_container_width=True):
    t_home = wnba_df[wnba_df['Team'] == wnba_home].iloc[0]
    t_away = wnba_df[wnba_df['Team'] == wnba_away].iloc[0]
        
    # Fatigue Adjustments (Müdigkeit kostet Punkte)
    fatigue_home = 2.0 if rest_home == 0 else (1.0 if rest_home == 1 else 0)
    fatigue_away = 2.0 if rest_away == 0 else (1.0 if rest_away == 1 else 0)
        
    # Erwartete Punkte berechnen (Offensive des einen vs. Defensive des anderen)
    exp_pts_home = (t_home['PTS'] + t_away['OPP_PTS']) / 2 - fatigue_home
    exp_pts_away = (t_away['PTS'] + t_home['OPP_PTS']) / 2 - fatigue_away
    
    # Modelle für Spread und Total
    model_margin = exp_pts_home - exp_pts_away
    model_total = exp_pts_home + exp_pts_away
    
    # --- PROBABILITIES (Wahrscheinlichkeiten) ---
    # In der WNBA entspricht 1 Punkt Differenz ca. 3.5% Wahrscheinlichkeit beim Handicap
    # und ca. 2.5% Wahrscheinlichkeit beim Total.
    
    # 1. Handicap Wahrscheinlichkeit
    bookie_margin = -b_spread # z.B. -3.5 bedeutet, Buchmacher erwartet +3.5 Vorsprung fürs Heimteam
    edge_spread = model_margin - bookie_margin
    prob_home_cover = 50.0 + (edge_spread * 3.5)
    prob_home_cover = max(5.0, min(95.0, prob_home_cover)) # Cappen zwischen 5% und 95%
    
    # 2. Total Wahrscheinlichkeit
    edge_total = model_total - b_total
    prob_over = 50.0 + (edge_total * 2.5)
    prob_over = max(5.0, min(95.0, prob_over))
    
    # --- VISUELLE AUSGABE ---
    st.divider()
    st.subheader(f"🎯 Spiel-Prognose: {exp_pts_home:.1f} - {exp_pts_away:.1f}")
    
    # HANDICAP AUSGABE
    st.write("### ⚖️ Handicap (Spread)")
    h_col1, h_col2 = st.columns(2)
    h_col1.metric("Dein Model-Spread", f"{model_margin*-1:.1f}")
    h_col2.metric("Buchmacher Handicap", f"{b_spread}")
    
    if prob_home_cover > 55.0:
        st.success(f"🔥 **Value auf {wnba_home} ({b_spread})** mit **{prob_home_cover:.1f}%** Wahrscheinlichkeit!")
    elif prob_home_cover < 45.0:
        st.success(f"🔥 **Value auf {wnba_away} ({(b_spread*-1):+})** mit **{100-prob_home_cover:.1f}%** Wahrscheinlichkeit!")
    else:
        st.warning(f"Kein klarer Value beim Handicap (Markt ist effizient).")

    st.write("---")
    
    # OVER/UNDER AUSGABE
    st.write("### 📈 Over / Under")
    o_col1, o_col2 = st.columns(2)
    o_col1.metric("Dein Model-Total", f"{model_total:.1f}")
    o_col2.metric("Buchmacher Linie", f"{b_total}")
    
    if prob_over > 55.0:
        st.success(f"🔥 **Value im OVER** mit **{prob_over:.1f}%** Wahrscheinlichkeit!")
    elif prob_over < 45.0:
        st.success(f"🔥 **Value im UNDER** mit **{100-prob_over:.1f}%** Wahrscheinlichkeit!")
    else:
        st.warning(f"Kein klarer Value beim Total (Markt ist effizient).")
