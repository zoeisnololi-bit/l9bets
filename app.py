import streamlit as st
import pandas as pd
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="WNBA Edge Pro", page_icon="🏀", layout="centered")

st.title("🏀 WNBA Betting Edge Pro")
st.caption("Fokus: Spread & Over/Under Analyse")

# --- DATEN-LOADER ---
@st.cache_data
def lade_wnba_daten():
    if not os.path.exists('wnba_stats.csv'):
        return None, "Datei 'wnba_stats.csv' nicht gefunden."
    
    df = pd.read_csv('wnba_stats.csv', sep=None, engine='python', encoding='utf-8')
    df.columns = [str(c).strip().upper() for c in df.columns]
    
    # Mapping für unterschiedliche Spalten-Benennungen
    mapping = {
        'TEAM': ['TEAM', 'TEAM_NAME', 'NAME', 'MANNSCHAFT'],
        'PTS': ['PTS', 'POINTS', 'PUNKTE', 'SCORE'],
        'OPP_PTS': ['OPP_PTS', 'OPP_POINTS', 'OPP_SCORE', 'ALLOWED'],
        'PACE': ['PACE', 'SPEED', 'POSSESSIONS']
    }
    
    # Spalten umbenennen, falls möglich
    new_cols = {}
    for standard, variations in mapping.items():
        for col in df.columns:
            if col in variations:
                new_cols[col] = standard
    
    df = df.rename(columns=new_cols)
    
    # Check ob die wichtigen Spalten existieren
    missing = [c for c in ['TEAM', 'PTS', 'OPP_PTS'] if c not in df.columns]
    if missing:
        return None, f"Fehlende Spalten in CSV: {missing}. Gefundene Spalten: {list(df.columns)}"
    
    return df, None

# Daten laden
df, error = lade_wnba_daten()
if error:
    st.error(error)
    st.stop()

# --- UI ---
col1, col2 = st.columns(2)
teams = sorted(df['TEAM'].unique().tolist())
wnba_home = col1.selectbox("Heimteam", teams)
wnba_away = col2.selectbox("Auswärtsteam", teams)

st.write("---")
st.subheader("⚙️ Spiel-Faktoren")
r1, r2 = st.columns(2)
rest_h = r1.slider("Pause Heim (Tage)", 0, 5, 2)
rest_a = r2.slider("Pause Auswärts (Tage)", 0, 5, 2)

st.subheader("📉 Buchmacher-Werte")
b1, b2 = st.columns(2)
b_spread = b1.number_input("Spread (z.B. -3.5)", value=-3.5)
b_total = b2.number_input("Total (O/U Linie)", value=165.5)

if st.button("🚀 Edge berechnen", use_container_width=True):
    t_h = df[df['TEAM'] == wnba_home].iloc[0]
    t_a = df[df['TEAM'] == wnba_away].iloc[0]
    
    # Fatigue-Berechnung
    f_h = 2.5 if rest_h == 0 else 0
    f_a = 2.5 if rest_a == 0 else 0
    
    # Punkte-Berechnung
    # Formel: (Team-Schnitt + Opp-Schnitt) / 2
    avg_pts_h = (t_h['PTS'] + t_a['OPP_PTS']) / 2 - f_h
    avg_pts_a = (t_a['PTS'] + t_h['OPP_PTS']) / 2 - f_a
    
    model_spread = avg_pts_h - avg_pts_a
    model_total = avg_pts_h + avg_pts_a
    
    # Output
    st.divider()
    c_spread, c_total = st.columns(2)
    
    c_spread.metric("Model Spread", f"{model_spread:.1f} Pkt")
    c_spread.write(f"Buchmacher: {b_spread:.1f}")
    if abs(model_spread - b_spread) > 1.5:
        c_spread.success("Value im Spread!")
        
    c_total.metric("Model Total", f"{model_total:.1f} Pkt")
    c_total.write(f"Buchmacher: {b_total:.1f}")
    if abs(model_total - b_total) > 3.0:
        c_total.success("Value im Over/Under!")

# Debug: Spalten anzeigen (hilfreich falls nochmal Fehler kommen)
with st.expander("Daten-Check (Spaltennamen)"):
    st.write(df.columns.tolist())
