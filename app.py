import streamlit as st
import pandas as pd
import os
import math

st.set_page_config(page_title="WNBA Analytics", page_icon="🏀", layout="centered")

st.title("🏀 WNBA Strategy Pro")

@st.cache_data
def lade_daten():
    if not os.path.exists('wnba_stats.csv'): return None, "Datei fehlt."
    df = pd.read_csv('wnba_stats.csv', encoding='utf-8')
    df.columns = [str(c).strip().upper() for c in df.columns]
    return df, None

df, err = lade_daten()
if err: st.error(err); st.stop()

# UI
c1, c2 = st.columns(2)
teams = sorted(df['TEAM'].unique().tolist())
h_team = c1.selectbox("Heimteam", teams)
a_team = c2.selectbox("Auswärtsteam", teams)

st.write("---")
# Buchmacher Eingaben
st.subheader("📉 Buchmacher-Werte")
b_spread = st.number_input("Spread (Buchmacher)", value=-3.5)
b_total = st.number_input("Total (Buchmacher O/U)", value=165.5)

if st.button("🚀 Analyse ausführen", use_container_width=True):
    t_h = df[df['TEAM'] == h_team].iloc[0]
    t_a = df[df['TEAM'] == a_team].iloc[0]
    
    # --- BERECHNUNGEN ---
    # Win Prob: Logistische Regression basierend auf Punktedifferenz
    # Faktor 0.1 skaliert die Differenz auf Wahrscheinlichkeit
    diff = t_h['PTS'] - t_a['PTS']
    win_prob_h = 1 / (1 + math.exp(-0.1 * diff)) * 100
    
    # Model Total: Durchschnitt der Teams
    model_total = (t_h['PTS'] + t_a['PTS'])
    
    # Ausgaben
    st.divider()
    
    # Sieg-Sektion
    st.subheader("📊 Sieg-Prognose")
    st.metric("Sieg-Wahrscheinlichkeit (Heim)", f"{win_prob_h:.1f}%")
    
    # Over/Under Sektion
    st.subheader("📈 Over / Under")
    st.write(f"Model-Erwartung: **{model_total:.1f} Punkte**")
    st.write(f"Buchmacher-Linie: {b_total:.1f} Punkte")
    
    diff_total = model_total - b_total
    if diff_total > 2.0:
        st.success(f"🔥 OVER! Das Modell erwartet {abs(diff_total):.1f} Punkte mehr als der Buchmacher.")
    elif diff_total < -2.0:
        st.success(f"🔥 UNDER! Das Modell erwartet {abs(diff_total):.1f} Punkte weniger als der Buchmacher.")
    else:
        st.warning("Kein Value (Markt effizient).")

    # Spread Sektion
    st.subheader("⚖️ Spread-Check")
    model_spread = t_h['PTS'] - t_a['PTS']
    st.write(f"Model-Spread: **{model_spread:.1f} Pkt** vs Buchmacher: {b_spread:.1f}")
    if abs(model_spread - b_spread) > 1.5:
        st.info("Spread-Diskrepanz erkannt!")
