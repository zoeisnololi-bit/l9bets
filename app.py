import streamlit as st
import pandas as pd
import os
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import warnings

warnings.filterwarnings("ignore")

# ---------------------------------------------------
# HILFSFUNKTIONEN
# ---------------------------------------------------

def hole_live_news(team1, team2=None):
    try:
        suchbegriff = f"{team1} {team2}" if team2 else team1

        url = (
            "https://news.google.com/rss/search?q="
            + urllib.parse.quote(f"{suchbegriff} WNBA")
            + "&hl=de&gl=DE&ceid=DE:de"
        )

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0"}
        )

        with urllib.request.urlopen(req, timeout=4) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)

        return [
            {
                "titel": item.find("title").text,
                "link": item.find("link").text
            }
            for item in root.findall(".//item")[:5]
        ]

    except:
        return []

# ---------------------------------------------------
# PAGE CONFIG
# ---------------------------------------------------

st.set_page_config(
    page_title="WNBA Power Analyst",
    page_icon="🏀",
    layout="centered"
)

st.title("🏀 WNBA Power Analyst")
st.caption("Spread-Modell + Siegwahrscheinlichkeit + Live News")

# ---------------------------------------------------
# DATEN LADEN
# ---------------------------------------------------

@st.cache_data
def lade_wnba_daten():

    if not os.path.exists("wnba_stats.csv"):
        return None, "Datei 'wnba_stats.csv' nicht gefunden."

    try:
        df = pd.read_csv(
            "wnba_stats.csv",
            sep=None,
            engine="python",
            encoding="utf-8"
        )
    except:
        df = pd.read_csv(
            "wnba_stats.csv",
            encoding="utf-8"
        )

    df.columns = [str(c).strip().upper() for c in df.columns]

    if "TEAM" not in df.columns:
        return None, "TEAM-Spalte fehlt."

    if "PTS" not in df.columns:
        return None, "PTS-Spalte fehlt."

    # W/L%
    if "W/L%" in df.columns:
        df["W/L%"] = pd.to_numeric(
            df["W/L%"],
            errors="coerce"
        )
    else:
        df["W/L%"] = 0.500

    # OPP_PTS erzeugen falls nicht vorhanden
    if "OPP_PTS" not in df.columns:
        df["OPP_PTS"] = df["PTS"].mean()

    return df, None


df, error = lade_wnba_daten()

if error:
    st.error(error)
    st.stop()

# ---------------------------------------------------
# UI
# ---------------------------------------------------

teams = sorted(df["TEAM"].unique().tolist())

c1, c2 = st.columns(2)

heimteam = c1.selectbox(
    "Heimteam",
    teams
)

auswaertsteam = c2.selectbox(
    "Auswärtsteam",
    teams
)

# ---------------------------------------------------
# FATIGUE SETTINGS
# ---------------------------------------------------

r1, r2 = st.columns(2)

rest_h = r1.slider(
    "Pause Heim (Tage)",
    0,
    5,
    2
)

rest_a = r2.slider(
    "Pause Auswärts (Tage)",
    0,
    5,
    2
)

buchmacher_spread = st.number_input(
    "Spread vom Buchmacher",
    value=-3.5
)

# ---------------------------------------------------
# ANALYSE
# ---------------------------------------------------

if st.button(
    "🚀 Analyse starten",
    use_container_width=True
):

    t_h = df[df["TEAM"] == heimteam].iloc[0]
    t_a = df[df["TEAM"] == auswaertsteam].iloc[0]

    # ====================================
    # 1. WIN-PROBABILITY MODELL
    # ====================================

    p_h = float(t_h["W/L%"])
    p_a = float(t_a["W/L%"])

    if p_h + p_a > 0:

        win_prob_h = p_h / (p_h + p_a)
        win_prob_a = p_a / (p_h + p_a)

    else:

        win_prob_h = 0.5
        win_prob_a = 0.5

    st.subheader("📊 Relative Teamstärken")

    x1, x2 = st.columns(2)

    x1.metric(
        heimteam,
        f"{p_h:.3f}"
    )

    x2.metric(
        auswaertsteam,
        f"{p_a:.3f}"
    )

    st.progress(win_prob_h)

    st.write(
        f"**{heimteam}: {win_prob_h*100:.1f}%**"
    )

    st.write(
        f"**{auswaertsteam}: {win_prob_a*100:.1f}%**"
    )

    if abs(win_prob_h - win_prob_a) > 0.15:
        st.success(
            "Klare Favoritenrolle erkannt."
        )
    else:
        st.warning(
            "Teams historisch sehr ausgeglichen."
        )

    st.divider()

    # ====================================
    # 2. SPREAD MODELL
    # ====================================

    fatigue_h = 2.5 if rest_h == 0 else 0
    fatigue_a = 2.5 if rest_a == 0 else 0

    exp_h = (
        t_h["PTS"]
        - t_h["OPP_PTS"]
        + fatigue_a
        - fatigue_h
    )

    exp_a = (
        t_a["PTS"]
        - t_a["OPP_PTS"]
        + fatigue_h
        - fatigue_a
    )

    model_spread = (
        exp_h + exp_a
    ) / 2

    st.subheader("🏀 Spread-Modell")

    s1, s2 = st.columns(2)

    s1.metric(
        "Modell-Spread",
        f"{model_spread:.1f}"
    )

    s2.metric(
        "Buchmacher",
        f"{buchmacher_spread:.1f}"
    )

    edge = model_spread - buchmacher_spread

    if abs(edge) > 1.5:
        st.success(
            f"🔥 VALUE FOUND! Edge: {abs(edge):.1f} Punkte"
        )
    else:
        st.warning(
            "Markt aktuell effizient."
        )

# ---------------------------------------------------
# NEWS
# ---------------------------------------------------

st.divider()

st.subheader("📰 Live News")

for news in hole_live_news(
    heimteam,
    auswaertsteam
):
    st.markdown(
        f"- [{news['titel']}]({news['link']})"
    )

# ---------------------------------------------------
# DEBUG
# ---------------------------------------------------

with st.expander("Datenquelle"):
    st.write(df.columns.tolist())
