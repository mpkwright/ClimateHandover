import streamlit as st
import requests
import pandas as pd
import numpy as np
import time
import reverse_geocoder as rg
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
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("😕 Password incorrect")
    return False

if not check_password(): st.stop()

# ---------------------------------------------------------
# 1. ROBUST CONNECTION CONFIGURATION
# ---------------------------------------------------------
def get_robust_session():
    session = requests.Session()
    retry = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
    return session

http = get_robust_session()

# ---------------------------------------------------------
# 2. CONFIGURATION & UUIDs
# ---------------------------------------------------------
RISK_CONFIG = {
    "Baseline Water Stress": {"uuid": "c66d7f3a-d1a8-488f-af8b-302b0f2c3840", "cols": ["bws_score", "bws_label"]},
    "Drought Risk":          {"uuid": "5c9507d1-47f7-4c6a-9e64-fc210ccc48e2", "cols": ["drr_score", "drr_label"]},
    "Riverine Flood":        {"uuid": "df9ef304-672f-4c17-97f4-f9f8fa2849ff", "cols": ["rfr_score", "rfr_label"]},
    "Coastal Flood":         {"uuid": "d39919a9-0940-4038-87ac-662f944bc846", "cols": ["cfr_score", "cfr_label"]}
}
FUTURE_WATER_ID = "2a571044-1a31-4092-9af8-48f406f13072"

# ---------------------------------------------------------
# 3. BACKEND API FETCHERS (World Bank CCKP)
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_wri_current(lat, lon, risk_name):
    config = RISK_CONFIG[risk_name]
    sql = f"SELECT {config['cols'][1]} FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    try:
        r = http.get(f"https://api.resourcewatch.org/v1/query/{config['uuid']}", params={"sql": sql}, timeout=15)
        if r.status_code == 200:
            data = r.json().get('data', [])
            return data[0].get(config['cols'][1], "N/A") if data else "N/A"
        return "N/A"
    except: return "N/A"

@st.cache_data(ttl=3600)
def fetch_wri_future(lat, lon):
    sql = f"SELECT ws3024tl, ws3028tl, ws4024tl, ws4028tl FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    try:
        r = http.get(f"https://api.resourcewatch.org/v1/query/{FUTURE_WATER_ID}", params={"sql": sql}, timeout=15)
        if r.status_code == 200:
            data = r.json().get('data', [])
            return data[0] if data else {}
        return {}
    except: return {}

@st.cache_data(ttl=86400)
def fetch_wb_climate(iso_code, variable, period, scenario):
    """World Bank API using ISO code directly."""
    try:
        url = f"https://cckpapi.worldbank.org/cckp/v1/cmip6-x0.25_climatology_{variable}_annual_{period}_median_{scenario}_ensemble_all_mean/{iso_code}"
        r = http.get(url, params={"_format": "json"}, timeout=15)
        if r.status_code == 200:
            val = r.json().get('data', {}).get(iso_code, {}).get('value')
            return val
        return None
    except: return None

# ---------------------------------------------------------
# 4. ANALYSIS ENGINE
# ---------------------------------------------------------
def analyze_location(lat, lon):
    # Get ISO Country Code for sense-check
    cc_res = rg.search((lat, lon))[0]
    iso_code = cc_res['cc']
    location_name = f"{cc_res['name']}, {iso_code}"

    row = {
        "Latitude": lat, "Longitude": lon, "Country_Code": iso_code, "Location": location_name,
        "Drought": "N/A", "Riverine": "N/A", "Coastal": "N/A", "BWS": "N/A",
        "WS30_Opt": "N/A", "WS30_BAU": "N/A", "WS40_Opt": "N/A", "WS40_BAU": "N/A",
        "T_Base": 15.0, "P_Base": 200.0,
        "T35_Opt": None, "T35_BAU": None, "T50_Opt": None, "T50_BAU": None,
        "P35_Opt": None, "P35_BAU": None, "P50_Opt": None, "P50_BAU": None
    }
    
    row["Drought"] = fetch_wri_current(lat, lon, "Drought Risk")
    row["Riverine"] = fetch_wri_current(lat, lon, "Riverine Flood")
    row["Coastal"] = fetch_wri_current(lat, lon, "Coastal Flood")
    row["BWS"] = fetch_wri_current(lat, lon, "Baseline Water Stress")
    
    fw = fetch_wri_future(lat, lon)
    row.update({"WS30_Opt": fw.get("ws3024tl","N/A"), "WS30_BAU": fw.get("ws3028tl","N/A"), "WS40_Opt": fw.get("ws4024tl","N/A"), "WS40_BAU": fw.get("ws4028tl","N/A")})
    
    # Climate Fetching using ISO code
    row["T35_Opt"] = fetch_wb_climate(iso_code, 'tas', '2020-2039', 'ssp245')
    row["T35_BAU"] = fetch_wb_climate(iso_code, 'tas', '2020-2039', 'ssp585')
    row["T50_Opt"] = fetch_wb_climate(iso_code, 'tas', '2040-2059', 'ssp245')
    row["T50_BAU"] = fetch_wb_climate(iso_code, 'tas', '2040-2059', 'ssp585')
    row["P35_Opt"] = fetch_wb_climate(iso_code, 'pr', '2020-2039', 'ssp245')
    row["P35_BAU"] = fetch_wb_climate(iso_code, 'pr', '2020-2039', 'ssp585')
    row["P50_Opt"] = fetch_wb_climate(iso_code, 'pr', '2040-2059', 'ssp245')
    row["P50_BAU"] = fetch_wb_climate(iso_code, 'pr', '2040-2059', 'ssp585')
    
    return row

# ---------------------------------------------------------
# 5. FRONTEND UI
# ---------------------------------------------------------
st.set_page_config(page_title="Climate Risk Intel", page_icon="🌍", layout="wide")
st.title("🌍 Integrated Climate Risk Assessment")

t1, t2 = st.tabs(["📍 Single Location", "🚀 Batch Processing"])

with t1:
    ci1, ci2 = st.columns(2)
    lat_in = ci1.number_input("Latitude", 33.4484, format="%.4f")
    lon_in = ci2.number_input("Longitude", -112.0740, format="%.4f")
    st.map(pd.DataFrame({'lat': [lat_in], 'lon': [lon_in]}), zoom=8)

    if st.button("Generate Risk Report"):
        with st.spinner("Fetching Data..."):
            res = analyze_location(lat_in, lon_in)
        
        st.divider()
        # SENSE CHECK: Display identified location
        st.subheader(f"📍 Analysis for: {res['Location']}")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Drought", res["Drought"])
        c2.metric("Riverine", res["Riverine"])
        c3.metric("Coastal", res["Coastal"])
        
        st.divider()
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            st.subheader("📈 Temperature Pathway")
            t_chart = pd.DataFrame({
                "Year": [2010, 2035, 2050],
                "Optimistic (SSP2-4.5)": [res["T_Base"], res["T35_Opt"], res["T50_Opt"]],
                "BAU (SSP5-8.5)": [res["T_Base"], res["T35_BAU"], res["T50_BAU"]]
            }).set_index("Year")
            st.line_chart(t_chart)

        
        with chart_col2:
            st.subheader("🌧️ Precipitation Pathway")
            p_chart = pd.DataFrame({
                "Year": [2010, 2035, 2050],
                "Optimistic (SSP2-4.5)": [res["P_Base"], res["P35_Opt"], res["P50_Opt"]],
                "BAU (SSP5-8.5)": [res["P_Base"], res["P35_BAU"], res["P50_BAU"]]
            }).set_index("Year")
            st.line_chart(p_chart)

        st.divider()
        st.subheader("🔮 Detailed Projections")
        def fmt(val, unit): return f"{val:.1f}{unit}" if val else "N/A"
        
        table = [
            {"Metric": "Temp (Optimistic)", "Current": "15.0C", "+10Y (2035)": fmt(res["T35_Opt"], "C"), "+25Y (2050)": fmt(res["T50_Opt"], "C")},
            {"Metric": "Temp (BAU)", "Current": "15.0C", "+10Y (2035)": fmt(res["T35_BAU"], "C"), "+25Y (2050)": fmt(res["T50_BAU"], "C")},
            {"Metric": "Precip (Optimistic)", "Current": "200mm", "+10Y (2035)": fmt(res["P35_Opt"], "mm"), "+25Y (2050)": fmt(res["P50_Opt"], "mm")},
            {"Metric": "Precip (BAU)", "Current": "200mm", "+10Y (2035)": fmt(res["P35_BAU"], "mm"), "+25Y (2050)": fmt(res["P50_BAU"], "mm")},
            {"Metric": "WS (Optimistic)", "Current": res["BWS"], "+10Y (2035)": res["WS30_Opt"], "+25Y (2050)": res["WS40_Opt"]},
            {"Metric": "WS (BAU)", "Current": res["BWS"], "+10Y (2035)": res["WS30_BAU"], "+25Y (2050)": res["WS40_BAU"]}
        ]
        st.dataframe(pd.DataFrame(table), width='stretch', hide_index=True)

with t2:
    st.markdown("### 📥 Bulk Analysis")
    up = st.file_uploader("Upload CSV", type=["csv"])
    if up:
        df_in = pd.read_csv(up)
        df_in.columns = df_in.columns.str.lower()
        if st.button("Run Batch Analysis"):
            results, prog = [], st.progress(0)
            status = st.empty()
            for i, r in df_in.iterrows():
                status.text(f"Processing Row {i+1}/{len(df_in)}...")
                res = analyze_location(r['latitude'], r['longitude'])
                if 'id' in r: res['ID'] = r['id']
                results.append(res)
                prog.progress((i+1)/len(df_in))
                time.sleep(0.5)
            df_res = pd.DataFrame(results)
            st.success("Batch Complete!")
            st.dataframe(df_res, width='stretch')
            st.download_button("💾 Download CSV", df_res.to_csv(index=False).encode('utf-8'), "risk_results.csv", "text/csv")
