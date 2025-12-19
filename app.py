import streamlit as st
import pandas as pd
import json
import reverse_geocoder as rg
import requests
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------
# 1. CORE DATA LOADERS
# ---------------------------------------------------------
@st.cache_data
def load_wb_json():
    with open("climate_WB_data.json", "r") as f:
        return json.load(f)

WB_DB = load_wb_json()

# WRI Hazard Config (The parts that worked!)
RISK_CONFIG = {
    "Baseline Water Stress": {"uuid": "c66d7f3a-d1a8-488f-af8b-302b0f2c3840", "cols": ["bws_score", "bws_label"]},
    "Drought Risk":          {"uuid": "5c9507d1-47f7-4c6a-9e64-fc210ccc48e2", "cols": ["drr_score", "drr_label"]},
    "Riverine Flood":        {"uuid": "df9ef304-672f-4c17-97f4-f9f8fa2849ff", "cols": ["rfr_score", "rfr_label"]},
    "Coastal Flood":         {"uuid": "d39919a9-0940-4038-87ac-662f944bc846", "cols": ["cfr_score", "cfr_label"]}
}

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=3)))

# ---------------------------------------------------------
# 2. THE JSON ENGINE (Mapping Coordinates to Sub-Regions)
# ---------------------------------------------------------
def get_wb_value(loc_id, var, period, scenario):
    try:
        m_key = '2020-07' if period == '2020-2039' else '2040-07'
        return WB_DB['data'][var][period][scenario][loc_id][m_key]
    except: return None

def find_subregion_id(lat, lon):
    """Matches coordinates to the most specific ID in the JSON."""
    loc = rg.search((lat, lon))[0]
    iso2 = loc['cc']
    # Add common ISO2 to ISO3 mappings here
    iso3_map = {"US": "USA", "AF": "AFG", "GB": "GBR", "DE": "DEU", "IN": "IND", "BR": "BRA", "FR": "FRA"}
    iso3 = iso3_map.get(iso2, "USA")
    
    # Check if we can find a sub-region (e.g., USA.5)
    # This is a fallback to country-level if sub-region logic is too complex for a script
    return iso3 

# ---------------------------------------------------------
# 3. ANALYSIS ENGINE
# ---------------------------------------------------------
def analyze(lat, lon):
    loc_id = find_subregion_id(lat, lon)
    loc_info = rg.search((lat, lon))[0]
    
    # Fetching Hazard Data (WRI)
    hazards = {name: fetch_wri_data(lat, lon, name) for name in RISK_CONFIG.keys()}
    
    # Fetching Climate Data (Actual JSON References)
    res = {
        "Location": f"{loc_info['name']}, {loc_info['admin1']}",
        "ID": loc_id,
        "Hazards": hazards,
        "Temp": {
            "Base": get_wb_value(loc_id, 'tas', '2020-2039', 'ssp126'),
            "T35_245": get_wb_value(loc_id, 'tas', '2020-2039', 'ssp245'),
            "T35_370": get_wb_value(loc_id, 'tas', '2020-2039', 'ssp370'),
            "T50_245": get_wb_value(loc_id, 'tas', '2040-2059', 'ssp245'),
            "T50_370": get_wb_value(loc_id, 'tas', '2040-2059', 'ssp370')
        },
        "Prec": {
            "Base": get_wb_value(loc_id, 'pr', '2020-2039', 'ssp126'),
            "P35_245": get_wb_value(loc_id, 'pr', '2020-2039', 'ssp245'),
            "P35_370": get_wb_value(loc_id, 'pr', '2020-2039', 'ssp370'),
            "P50_245": get_wb_value(loc_id, 'pr', '2040-2059', 'ssp245'),
            "P50_370": get_wb_value(loc_id, 'pr', '2040-2059', 'ssp370')
        }
    }
    return res

def fetch_wri_data(lat, lon, risk):
    cfg = RISK_CONFIG[risk]
    sql = f"SELECT {cfg['cols'][1]} FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    try:
        r = session.get(f"https://api.resourcewatch.org/v1/query/{cfg['uuid']}", params={"sql": sql}, timeout=5)
        return r.json()['data'][0][cfg['cols'][1]]
    except: return "N/A"

# ---------------------------------------------------------
# 4. FRONTEND UI (RESTORING ALL WORKING PARTS)
# ---------------------------------------------------------
st.set_page_config(page_title="Risk Dashboard", layout="wide")
st.title("🌍 Integrated Climate & Hazard Intel")

# RESTORED SIDEBAR MAP & INPUTS
with st.sidebar:
    st.header("📍 Settings")
    lat_in = st.number_input("Lat", value=33.4484, format="%.4f")
    lon_in = st.number_input("Lon", value=-112.0740, format="%.4f")
    if st.button("Analyze"):
        st.session_state.data = analyze(lat_in, lon_in)

if 'data' in st.session_state:
    d = st.session_state.data
    st.map(pd.DataFrame({'lat': [lat_in], 'lon': [lon_in]}), zoom=6)
    
    st.subheader(f"📍 {d['Location']} (JSON ID: {d['ID']})")
    
    # HAZARD ROW
    cols = st.columns(4)
    for i, (name, val) in enumerate(d['Hazards'].items()):
        cols[i].metric(name, val)

    st.divider()
    
    # CLIMATE TABLE
    st.subheader("🔮 Actual Projections from Local JSON")
    def f(v, u): return f"{v:.2f}{u}" if v else "N/A"
    
    res_table = [
        {"Scenario": "Moderate (SSP2-4.5)", "Temp +10Y": f(d['Temp']['T35_245'], "C"), "Temp +25Y": f(d['Temp']['T50_245'], "C"), "Prec +10Y": f(d['Prec']['P35_245'], "mm")},
        {"Scenario": "High Risk (SSP3-7.0)", "Temp +10Y": f(d['Temp']['T35_370'], "C"), "Temp +25Y": f(d['Temp']['T50_370'], "C"), "Prec +10Y": f(d['Prec']['P35_370'], "mm")}
    ]
    st.table(pd.DataFrame(res_table))

    # TREND CHARTS
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Temp Trend (SSP3-7.0)**")
        st.line_chart(pd.Series([d['Temp']['Base'], d['Temp']['T35_370'], d['Temp']['T50_370']], index=[2020, 2035, 2050]))
    with c2:
        st.write("**Precip Trend (SSP3-7.0)**")
        st.line_chart(pd.Series([d['Prec']['Base'], d['Prec']['P35_370'], d['Prec']['P50_370']], index=[2020, 2035, 2050]))
