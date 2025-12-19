import streamlit as st
import pandas as pd
import json
import reverse_geocoder as rg
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------
# 1. AUTHENTICATION & CONFIG
# ---------------------------------------------------------
def check_password():
    if st.session_state.get("password_correct", False): return True
    def password_entered():
        if st.session_state["password"] == st.secrets["app_password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
    st.title("🔒 Access Protected")
    st.text_input("Password", type="password", on_change=password_entered, key="password")
    return False

if not check_password(): st.stop()

# WRI Hazard API Mapping
RISK_CONFIG = {
    "Baseline Water Stress": {"uuid": "c66d7f3a-d1a8-488f-af8b-302b0f2c3840", "cols": ["bws_score", "bws_label"]},
    "Drought Risk":          {"uuid": "5c9507d1-47f7-4c6a-9e64-fc210ccc48e2", "cols": ["drr_score", "drr_label"]},
    "Riverine Flood":        {"uuid": "df9ef304-672f-4c17-97f4-f9f8fa2849ff", "cols": ["rfr_score", "rfr_label"]},
    "Coastal Flood":         {"uuid": "d39919a9-0940-4038-87ac-662f944bc846", "cols": ["cfr_score", "cfr_label"]}
}

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1)))

# ---------------------------------------------------------
# 2. DATA LOADERS
# ---------------------------------------------------------
@st.cache_data
def load_wb_json():
    """Reads your uploaded climate_WB_data.json."""
    with open("climate_WB_data.json", "r") as f:
        return json.load(f)

WB_DB = load_wb_json()

@st.cache_data(ttl=3600)
def fetch_wri_hazard(lat, lon, risk_name):
    """Fetches real-time hazard data from Resource Watch."""
    cfg = RISK_CONFIG[risk_name]
    sql = f"SELECT {cfg['cols'][1]} FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    try:
        r = session.get(f"https://api.resourcewatch.org/v1/query/{cfg['uuid']}", params={"sql": sql}, timeout=10)
        data = r.json().get('data', [])
        return data[0].get(cfg['cols'][1], "N/A") if data else "N/A"
    except: return "N/A"

# ---------------------------------------------------------
# 3. JSON LOOKUP LOGIC
# ---------------------------------------------------------
def get_wb_projection(loc_id, var, scenario, period):
    """
    Directly navigates your JSON: data -> var -> period -> scenario -> loc_id
    Uses month-key '2020-07' or '2040-07' found in your file.
    """
    try:
        month_key = '2020-07' if period == '2020-2039' else '2040-07'
        return WB_DATA['data'][var][period][scenario][loc_id][month_key]
    except: return None

def map_coords_to_id(lat, lon, manual_id=None):
    """Maps coordinates to a JSON ID."""
    if manual_id: return manual_id
    
    loc = rg.search((lat, lon))[0]
    # Mapping ISO2 to ISO3 for JSON keys (e.g., 'US' -> 'USA')
    iso_map = {"US": "USA", "AF": "AFG", "GB": "GBR", "DE": "DEU", "AZ": "AZE"}
    return iso_map.get(loc['cc'], "USA")

# ---------------------------------------------------------
# 4. ANALYSIS ENGINE
# ---------------------------------------------------------
def run_analysis(lat, lon, sub_id):
    target_id = map_coords_to_id(lat, lon, sub_id)
    loc_info = rg.search((lat, lon))[0]
    
    # Since JSON has no historical data, we use ssp126 (2020) as baseline
    results = {
        "Location": f"{loc_info['name']}, {loc_info['cc']}",
        "Data_ID": target_id,
        "Drought": fetch_wri_hazard(lat, lon, "Drought Risk"),
        "Flood": fetch_wri_hazard(lat, lon, "Riverine Flood"),
        "BWS": fetch_wri_hazard(lat, lon, "Baseline Water Stress"),
        
        # Pulling three scenarios (ssp126, ssp245, ssp370)
        "T_Base": get_wb_projection(target_id, 'tas', 'ssp126', '2020-2039'),
        "T35_245": get_wb_projection(target_id, 'tas', 'ssp245', '2020-2039'),
        "T35_370": get_wb_projection(target_id, 'tas', 'ssp370', '2020-2039'),
        "T50_245": get_wb_projection(target_id, 'tas', 'ssp245', '2040-2059'),
        "T50_370": get_wb_projection(target_id, 'tas', 'ssp370', '2040-2059'),
        
        "P_Base": get_wb_projection(target_id, 'pr', 'ssp126', '2020-2039'),
        "P35_245": get_wb_projection(target_id, 'pr', 'ssp245', '2020-2039'),
        "P35_370": get_wb_projection(target_id, 'pr', 'ssp370', '2020-2039'),
        "P50_245": get_wb_projection(target_id, 'pr', 'ssp245', '2040-2059'),
        "P50_370": get_wb_projection(target_id, 'pr', 'ssp370', '2040-2059'),
    }
    return results

# ---------------------------------------------------------
# 5. STREAMLIT UI
# ---------------------------------------------------------
st.set_page_config(page_title="Integrated Risk Report", layout="wide")
st.title("🌍 Integrated Climate & Hazard Assessment")

with st.sidebar:
    st.header("📍 Parameters")
    lat_in = st.number_input("Latitude", value=33.4484, format="%.4f")
    lon_in = st.number_input("Longitude", value=-112.0740, format="%.4f")
    sub_id = st.text_input("Manual Sub-region ID", help="Optional GADM ID (e.g., USA.5)")
    if st.button("Generate Report"):
        st.session_state.report = run_analysis(lat_in, lon_in, sub_id)

if 'report' in st.session_state:
    res = st.session_state.report
    
    # 1. MAP
    st.map(pd.DataFrame({'lat': [lat_in], 'lon': [lon_in]}), zoom=7)
    
    st.subheader(f"📍 Results for {res['Location']} (ID: {res['Data_ID']})")
    
    # 2. WRI HAZARDS
    c1, c2, c3 = st.columns(3)
    c1.metric("Drought Risk", res["Drought"])
    c2.metric("Flood Risk", res["Flood"])
    c3.metric("Water Stress", res["BWS"])
    
    st.divider()
    
    # 3. CLIMATE TABLE (SSP245 vs SSP370)
    st.subheader("🔮 Sub-National Projections (from Local JSON)")
    def fmt(v, u): return f"{v:.2f}{u}" if v else "N/A"
    
    matrix = [
        {"Metric": "Temp (Mod - SSP245)", "Current (2020)": fmt(res["T_Base"],"C"), "+10Y": fmt(res["T35_245"],"C"), "+25Y": fmt(res["T50_245"],"C")},
        {"Metric": "Temp (High - SSP370)", "Current (2020)": fmt(res["T_Base"],"C"), "+10Y": fmt(res["T35_370"],"C"), "+25Y": fmt(res["T50_370"],"C")},
        {"Metric": "Prec (Mod - SSP245)", "Current (2020)": fmt(res["P_Base"],"mm"), "+10Y": fmt(res["P35_245"],"mm"), "+25Y": fmt(res["P50_245"],"mm")},
        {"Metric": "Prec (High - SSP370)", "Current (2020)": fmt(res["P_Base"],"mm"), "+10Y": fmt(res["P35_370"],"mm"), "+25Y": fmt(res["P50_370"],"mm")}
    ]
    st.table(pd.DataFrame(matrix))
    
    # 4. TREND CHARTS
    st.subheader("📈 Scenario Trends")
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        st.write("**Temp (SSP3-7.0)**")
        st.line_chart(pd.Series([res["T_Base"], res["T35_370"], res["T50_370"]], index=[2020, 2035, 2050]))
    with chart_col2:
        st.write("**Precip (SSP3-7.0)**")
        st.line_chart(pd.Series([res["P_Base"], res["P35_370"], res["P50_370"]], index=[2020, 2035, 2050]))
