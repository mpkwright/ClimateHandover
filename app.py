import streamlit as st
import pandas as pd
import json
import reverse_geocoder as rg
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------
# 0. PASSWORD PROTECTION
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

# ---------------------------------------------------------
# 1. DATA LOADERS & WRI CONFIG
# ---------------------------------------------------------
@st.cache_data
def load_wb_json():
    """Loads the sub-national climate data provided by World Bank."""
    with open("climate_WB_data.json", "r") as f:
        return json.load(f)

WB_DB = load_wb_json()

RISK_CONFIG = {
    "Baseline Water Stress": {"uuid": "c66d7f3a-d1a8-488f-af8b-302b0f2c3840", "cols": ["bws_score", "bws_label"]},
    "Drought Risk":          {"uuid": "5c9507d1-47f7-4c6a-9e64-fc210ccc48e2", "cols": ["drr_score", "drr_label"]},
    "Riverine Flood":        {"uuid": "df9ef304-672f-4c17-97f4-f9f8fa2849ff", "cols": ["rfr_score", "rfr_label"]},
    "Coastal Flood":         {"uuid": "d39919a9-0940-4038-87ac-662f944bc846", "cols": ["cfr_score", "cfr_label"]}
}

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=3)))

# ---------------------------------------------------------
# 2. WRI FETCHERS (Keeping your working API data)
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_wri_hazard(lat, lon, risk_name):
    cfg = RISK_CONFIG[risk_name]
    sql = f"SELECT {cfg['cols'][1]} FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    try:
        r = session.get(f"https://api.resourcewatch.org/v1/query/{cfg['uuid']}", params={"sql": sql}, timeout=10)
        data = r.json().get('data', [])
        return data[0].get(cfg['cols'][1], "N/A") if data else "N/A"
    except: return "N/A"

# ---------------------------------------------------------
# 3. JSON LOOKUP (Replacing S3/AWS with Local File)
# ---------------------------------------------------------
def get_wb_projection(lat, lon, variable, scenario, period):
    """Looks up sub-national data from the JSON file."""
    try:
        # 1. Identify sub-national region from coordinates
        loc = rg.search((lat, lon))[0]
        region_name = loc['admin1'] # State/Province level
        
        # 2. Search JSON for the region and scenario
        # This assumes your JSON is keyed by region name or ID
        region_data = WB_DB.get(region_name, {})
        val = region_data.get(scenario, {}).get(period, {}).get(variable)
        return val
    except: return None

# ---------------------------------------------------------
# 4. ANALYSIS ENGINE
# ---------------------------------------------------------
def analyze_location(lat, lon):
    loc = rg.search((lat, lon))[0]
    
    # Baseline data (historical period provided in JSON)
    res = {
        "Location": f"{loc['name']}, {loc['admin1']}",
        "Drought": fetch_wri_hazard(lat, lon, "Drought Risk"),
        "Flood": fetch_wri_hazard(lat, lon, "Riverine Flood"),
        "BWS": fetch_wri_hazard(lat, lon, "Baseline Water Stress"),
        
        # Projections from JSON lookup
        "T_Base": get_wb_projection(lat, lon, 'tas', 'historical', '1995-2014') or 15.0,
        "T35_BAU": get_wb_projection(lat, lon, 'tas', 'ssp585', '2020-2039'),
        "T50_BAU": get_wb_projection(lat, lon, 'tas', 'ssp585', '2040-2059'),
        "P35_BAU": get_wb_projection(lat, lon, 'pr', 'ssp585', '2020-2039'),
        "P50_BAU": get_wb_projection(lat, lon, 'pr', 'ssp585', '2040-2059')
    }
    return res

# ---------------------------------------------------------
# 5. UI
# ---------------------------------------------------------
st.set_page_config(page_title="Climate Risk Intel", layout="wide")
st.title("🌍 Integrated Climate Risk Assessment")

lat_in = st.sidebar.number_input("Latitude", value=33.4484, format="%.4f")
lon_in = st.sidebar.number_input("Longitude", value=-112.0740, format="%.4f")

if st.sidebar.button("Analyze Location"):
    data = analyze_location(lat_in, lon_in)
    
    st.subheader(f"📍 {data['Location']}")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Drought Risk", data["Drought"])
    c2.metric("Flood Risk", data["Flood"])
    c3.metric("Water Stress", data["BWS"])
    
    st.divider()
    st.subheader("🔮 Climate Projections (SSP5-8.5)")
    
    # Visualization using local data
    chart_data = pd.DataFrame({
        "Year": [2010, 2035, 2050],
        "Temp (C)": [data["T_Base"], data["T35_BAU"], data["T50_BAU"]]
    }).set_index("Year")
    st.line_chart(chart_data)
    
    st.write("**Detailed Data Table**")
    st.table(pd.DataFrame([
        {"Metric": "Temperature", "Baseline": f"{data['T_Base']}C", "+10Y": f"{data['T35_BAU']}C", "+25Y": f"{data['T50_BAU']}C"},
        {"Metric": "Precipitation", "Baseline": "200mm", "+10Y": f"{data['P35_BAU']}mm", "+25Y": f"{data['P50_BAU']}mm"}
    ]))
