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
