import streamlit as st
import pandas as pd
import json
import reverse_geocoder as rg
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------
# 0. PASSWORD PROTECTION
# ---------------------------------------------------------
def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False
    if st.session_state.get("password_correct", False): return True
    st.title("🔒 Access Protected")
    st.text_input("Please enter the access password", type="password", on_change=password_entered, key="password")
    return False

if not check_password(): st.stop()

# ---------------------------------------------------------
# 1. DATA LOADERS & WRI CONFIG
# ---------------------------------------------------------
@st.cache_data
def load_wb_db():
    with open("climate_WB_data.json", "r") as f:
        return json.load(f)

WB_DATA = load_wb_db()

RISK_CONFIG = {
    "Baseline Water Stress": {"uuid": "c66d7f3a-d1a8-488f-af8b-302b0f2c3840", "cols": ["bws_score", "bws_label"]},
    "Drought Risk":          {"uuid": "5c9507d1-47f7-4c6a-9e64-fc210ccc48e2", "cols": ["drr_score", "drr_label"]},
    "Riverine Flood":        {"uuid": "df9ef304-672f-4c17-97f4-f9f8fa2849ff", "cols": ["rfr_score", "rfr_label"]},
    "Coastal Flood":         {"uuid": "d39919a9-0940-4038-87ac-662f944bc846", "cols": ["cfr_score", "cfr_label"]}
}

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=3)))

# ---------------------------------------------------------
# 2. DATA FETCHERS
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_hazard(lat, lon, risk_name):
    cfg = RISK_CONFIG[risk_name]
    sql = f"SELECT {cfg['cols'][1]} FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    try:
        r = session.get(f"https://api.resourcewatch.org/v1/query/{cfg['uuid']}", params={"sql": sql}, timeout=10)
        data = r.json().get('data', [])
        return data[0].get(cfg['cols'][1], "N/A") if data else "N/A"
    except: return "N/A"

def get_wb_value(loc_id, var, period, scenario):
    """Accurately fetches values from your JSON structure."""
    try:
        # Month-key is 2020-07 for first period, 2040-07 for second
        m_key = '2020-07' if period == '2020-2039' else '2040-07'
        return WB_DATA['data'][var][period][scenario][loc_id][m_key]
    except: return None

def analyze_location(lat, lon, manual_id=None):
    # Geocoding for ID mapping
    loc_info = rg.search((lat, lon))[0]
    # Simple ISO2 to ISO3 mapping for your JSON keys
    iso3_map = {"US": "USA", "AZ": "AZE", "GB": "GBR", "DE": "DEU", "AF": "AFG"}
    loc_id = manual_id if manual_id else iso3_map.get(loc_info['cc'], "USA")

    res = {
        "Location": f"{loc_info['name']}, {loc_info['cc']}",
        "ID_Used": loc_id,
        "Drought": fetch_hazard(lat, lon, "Drought Risk"),
        "Flood": fetch_hazard(lat, lon, "Riverine Flood"),
        "BWS": fetch_hazard(lat, lon, "Baseline Water Stress"),
        
        # Pulling EXACT values from JSON
        "T_Base": get_wb_value(loc_id, 'tas', '2020-2039', 'ssp126'),
        "T35_BAU": get_wb_value(loc_id, 'tas', '2020-2039', 'ssp370'),
        "T50_BAU": get_wb_value(loc_id, 'tas', '2040-2059', 'ssp370'),
        "P_Base": get_wb_value(loc_id, 'pr', '2020-2039', 'ssp126'),
        "P35_BAU": get_wb_value(loc_id, 'pr', '2020-2039', 'ssp370'),
        "P50_BAU": get_wb_value(loc_id, 'pr', '2040-2059', 'ssp370')
    }
    return res

# ---------------------------------------------------------
# 3. UI DISPLAY
# ---------------------------------------------------------
st.set_page_config(page_title="Global Risk Intelligence", layout="wide")
st.title("🌍 Integrated Climate Risk Assessment")

with st.sidebar:
    st.header("📍 Location Inputs")
    lat_in = st.number_input("Latitude", value=33.4484, format="%.4f")
    lon_in = st.number_input("Longitude", value=-112.0740, format="%.4f")
    manual_id = st.text_input("Sub-region ID (e.g., USA.5)", help="Leave blank for country-level")
    run_btn = st.button("Generate Report")

t1, t2 = st.tabs(["📊 Analysis", "🚀 Batch"])

with t1:
    if run_btn:
        with st.spinner("Accessing JSON & WRI APIs..."):
            data = analyze_location(lat_in, lon_in, manual_id)
        
        # RESTORED MAP
        st.map(pd.DataFrame({'lat': [lat_in], 'lon': [lon_in]}), zoom=7)
        
        st.subheader(f"📍 Region: {data['Location']} (Data ID: {data['ID_Used']})")
        
        # WRI METRICS
        c1, c2, c3 = st.columns(3)
        c1.metric("Drought Risk", data["Drought"])
        c2.metric("Flood Risk", data["Flood"])
        c3.metric("Water Stress", data["BWS"])
        
        st.divider()
        st.subheader("🔮 Projections from WB JSON (SSP3-7.0 BAU)")
        
        # ACCURATE TABLE
        def fmt(v, u): return f"{v:.2f}{u}" if v is not None else "N/A"
        
        table = [
            {"Metric": "Temperature", "Baseline (2020)": fmt(data["T_Base"],"C"), "+10Y (2035)": fmt(data["T35_BAU"],"C"), "+25Y (2050)": fmt(data["T50_BAU"],"C")},
            {"Metric": "Precipitation", "Baseline (2020)": fmt(data["P_Base"],"mm"), "+10Y (2035)": fmt(data["P35_BAU"],"mm"), "+25Y (2050)": fmt(data["P50_BAU"],"mm")}
        ]
        st.table(pd.DataFrame(table))
        
        # DUAL CHARTS
        cc1, cc2 = st.columns(2)
        with cc1:
            st.write("**Temp Trend (C)**")
            st.line_chart(pd.DataFrame({"Temp": [data["T_Base"], data["T35_BAU"], data["T50_BAU"]]}, index=[2020, 2035, 2050]))
        with cc2:
            st.write("**Precip Trend (mm)**")
            st.line_chart(pd.DataFrame({"Precip": [data["P_Base"], data["P35_BAU"], data["P50_BAU"]]}, index=[2020, 2035, 2050]))

with t2:
    st.markdown("### 📥 Bulk Analysis")
    up = st.file_uploader("Upload CSV (must have 'latitude' and 'longitude')", type=["csv"])
    if up:
        df_in = pd.read_csv(up)
        if st.button("Run Batch Processing"):
            results = []
            prog = st.progress(0)
            for i, r in df_in.iterrows():
                results.append(analyze_location(r['latitude'], r['longitude']))
                prog.progress((i+1)/len(df_in))
            st.dataframe(pd.DataFrame(results))
