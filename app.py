import streamlit as st
import pandas as pd
import json
import reverse_geocoder as rg
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 1. DATABASE LOADER
@st.cache_data
def load_wb_db():
    with open("climate_WB_data.json", "r") as f:
        return json.load(f)

WB_DB = load_wb_db()

# 2. HAZARD CONFIG
RISK_CONFIG = {
    "Baseline Water Stress": {"uuid": "c66d7f3a-d1a8-488f-af8b-302b0f2c3840", "cols": ["bws_score", "bws_label"]},
    "Drought Risk":          {"uuid": "5c9507d1-47f7-4c6a-9e64-fc210ccc48e2", "cols": ["drr_score", "drr_label"]},
    "Riverine Flood":        {"uuid": "df9ef304-672f-4c17-97f4-f9f8fa2849ff", "cols": ["rfr_score", "rfr_label"]},
    "Coastal Flood":         {"uuid": "d39919a9-0940-4038-87ac-662f944bc846", "cols": ["cfr_score", "cfr_label"]}
}
session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=3)))

# 3. CUSTOM STYLING
st.markdown("""
    <style>
    [data-testid="stMetricValue"] { font-size: 1.6rem !important; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-size: 1.0rem !important; }
    </style>
    """, unsafe_allow_html=True)

# 4. DATA ENGINE
def get_wb_val(loc_id, var, scenario, period):
    try:
        m_key = '2020-07' if period == '2020-2039' else '2040-07'
        return WB_DB['data'][var][period][scenario][loc_id][m_key]
    except: return None

def analyze(lat, lon, sub_id):
    loc_info = rg.search((lat, lon))[0]
    # Country ISO3 Mapper
    iso3_map = {"US": "USA", "AF": "AFG", "GB": "GBR", "DE": "DEU", "AZ": "AZE", "IN": "IND", "BR": "BRA", "FR": "FRA"}
    target_id = sub_id if sub_id else iso3_map.get(loc_info['cc'], "USA")
    
    res = {"Location": f"{loc_info['name']}, {loc_info['cc']}", "ID": target_id}
    
    # Hazard Data
    for name, cfg in RISK_CONFIG.items():
        sql = f"SELECT {cfg['cols'][1]} FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
        try:
            r = session.get(f"https://api.resourcewatch.org/v1/query/{cfg['uuid']}", params={"sql": sql}, timeout=5)
            res[name] = r.json()['data'][0][cfg['cols'][1]]
        except: res[name] = "N/A"

    # Climate Data
    for var in ['tas', 'pr']:
        for sc in ['ssp126', 'ssp245', 'ssp370']:
            for prd in ['2020-2039', '2040-2059']:
                res[f"{var}_{sc}_{prd}"] = get_wb_val(target_id, var, sc, prd)
    return res

# 5. FRONTEND UI
st.title("🌍 Climate Risk & Hazard Intelligence")

with st.sidebar:
    st.header("📍 Location Parameters")
    lat_v = st.number_input("Latitude", value=33.4484, format="%.4f")
    lon_v = st.number_input("Longitude", value=-112.0740, format="%.4f")
    sid = st.text_input("GADM Sub-region ID (Optional)", placeholder="e.g. USA.5")
    if st.button("Generate Report"):
        st.session_state.rpt = analyze(lat_v, lon_v, sid)

if 'rpt' in st.session_state:
    r = st.session_state.rpt
    st.map(pd.DataFrame({'lat': [lat_v], 'lon': [lon_v]}), zoom=7)
    
    st.subheader(f"📍 {r['Location']} (Reference ID: {r['ID']})")
    
    # HAZARDS SPLIT OVER TWO ROWS FOR VISIBILITY
    h_row1_col1, h_row1_col2 = st.columns(2)
    h_row2_col1, h_row2_col2 = st.columns(2)
    
    h_row1_col1.metric("🌊 Water Stress", r["Baseline Water Stress"])
    h_row1_col2.metric("🏜️ Drought Risk", r["Drought Risk"])
    h_row2_col1.metric("🏠 Riverine Flood", r["Riverine Flood"])
    h_row2_col2.metric("🏖️ Coastal Flood", r["Coastal Flood"])

    st.divider()
    st.subheader("🔮 Projection Matrix (All Scenarios)")
    
    def fm(v, u): return f"{v:.2f}{u}" if v is not None else "N/A"
    
    res_data = [
        {"Scenario": "Optimistic (SSP1-2.6)", "Temp +10Y": fm(r['tas_ssp126_2020-2039'], "C"), "Temp +25Y": fm(r['tas_ssp126_2040-2059'], "C"), "Prec +10Y": fm(r['pr_ssp126_2020-2039'], "mm"), "Prec +25Y": fm(r['pr_ssp126_2040-2059'], "mm")},
        {"Scenario": "Moderate (SSP2-4.5)", "Temp +10Y": fm(r['tas_ssp245_2020-2039'], "C"), "Temp +25Y": fm(r['tas_ssp245_2040-2059'], "C"), "Prec +10Y": fm(r['pr_ssp245_2020-2039'], "mm"), "Prec +25Y": fm(r['pr_ssp245_2040-2059'], "mm")},
        {"Scenario": "High Risk (SSP3-7.0)", "Temp +10Y": fm(r['tas_ssp370_2020-2039'], "C"), "Temp +25Y": fm(r['tas_ssp370_2040-2059'], "C"), "Prec +10Y": fm(r['pr_ssp370_2020-2039'], "mm"), "Prec +25Y": fm(r['pr_ssp370_2040-2059'], "mm")}
    ]
    st.table(pd.DataFrame(res_data))

    # DUAL PATHWAY CHARTS (ALL 3 SCENARIOS)
    
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Temperature Pathways (C)**")
        t_df = pd.DataFrame({
            "SSP1-2.6": [r['tas_ssp126_2020-2039'], r['tas_ssp126_2040-2059']],
            "SSP2-4.5": [r['tas_ssp245_2020-2039'], r['tas_ssp245_2040-2059']],
            "SSP3-7.0": [r['tas_ssp370_2020-2039'], r['tas_ssp370_2040-2059']]
        }, index=[2030, 2050])
        st.line_chart(t_df)
    
    with c2:
        st.write("**Precipitation Pathways (mm)**")
        p_df = pd.DataFrame({
            "SSP1-2.6": [r['pr_ssp126_2020-2039'], r['pr_ssp126_2040-2059']],
            "SSP2-4.5": [r['pr_ssp245_2020-2039'], r['pr_ssp245_2040-2059']],
            "SSP3-7.0": [r['pr_ssp370_2020-2039'], r['pr_ssp370_2040-2059']]
        }, index=[2030, 2050])
        st.line_chart(p_df)
