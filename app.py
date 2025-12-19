import streamlit as st
import pandas as pd
import numpy as np
import xarray as xr
import s3fs
import requests
import reverse_geocoder as rg
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
# 1. WRI API CONFIGURATION (Hazard Logic)
# ---------------------------------------------------------
RISK_CONFIG = {
    "Baseline Water Stress": {"uuid": "c66d7f3a-d1a8-488f-af8b-302b0f2c3840", "cols": ["bws_score", "bws_label"]},
    "Drought Risk":          {"uuid": "5c9507d1-47f7-4c6a-9e64-fc210ccc48e2", "cols": ["drr_score", "drr_label"]},
    "Riverine Flood":        {"uuid": "df9ef304-672f-4c17-97f4-f9f8fa2849ff", "cols": ["rfr_score", "rfr_label"]},
    "Coastal Flood":         {"uuid": "d39919a9-0940-4038-87ac-662f944bc846", "cols": ["cfr_score", "cfr_label"]}
}
FUTURE_WATER_ID = "2a571044-1a31-4092-9af8-48f406f13072"

def get_robust_session():
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update({"User-Agent": "Mozilla/5.0"})
    return session

http = get_robust_session()

# ---------------------------------------------------------
# 2. WRI FETCHERS (Hazard Data)
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_wri_current(lat, lon, risk_name):
    config = RISK_CONFIG[risk_name]
    sql = f"SELECT {config['cols'][1]} FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    try:
        r = http.get(f"https://api.resourcewatch.org/v1/query/{config['uuid']}", params={"sql": sql}, timeout=10)
        if r.status_code == 200:
            data = r.json().get('data', [])
            return data[0].get(config['cols'][1], "N/A") if data else "N/A"
        return "N/A"
    except: return "N/A"

@st.cache_data(ttl=3600)
def fetch_wri_future(lat, lon):
    sql = f"SELECT ws3024tl, ws3028tl, ws4024tl, ws4028tl FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    try:
        r = http.get(f"https://api.resourcewatch.org/v1/query/{FUTURE_WATER_ID}", params={"sql": sql}, timeout=10)
        if r.status_code == 200:
            data = r.json().get('data', [])
            return data[0] if data else {}
        return {}
    except: return {}

# ---------------------------------------------------------
# 3. AWS S3 CLIMATE FETCHERS (Temp/Precip Data)
# ---------------------------------------------------------
@st.cache_data(ttl=86400)
def fetch_s3_climate(lat, lon, variable, scenario, period_range):
    fs = s3fs.S3FileSystem(anon=True)
    file_path = f"wbg-cckp/cmip6-x0.25/climatology/{variable}_annual_{period_range}_median_{scenario}_ensemble_all_mean.nc"
    try:
        with fs.open(file_path) as f:
            ds = xr.open_dataset(f, engine="h5netcdf")
            # S3 data uses 0-360 lon; convert if necessary
            target_lon = lon if lon >= 0 else 360 + lon 
            data_point = ds.sel(lat=lat, lon=target_lon, method="nearest")
            return float(data_point[variable].values)
    except: return None

# ---------------------------------------------------------
# 4. INTEGRATED ANALYSIS ENGINE
# ---------------------------------------------------------
def analyze_location(lat, lon):
    cc_res = rg.search((lat, lon))[0]
    
    row = {
        "Latitude": lat, "Longitude": lon, "Location": f"{cc_res['name']}, {cc_res['cc']}",
        "Drought": fetch_wri_current(lat, lon, "Drought Risk"),
        "Riverine": fetch_wri_current(lat, lon, "Riverine Flood"),
        "Coastal": fetch_wri_current(lat, lon, "Coastal Flood"),
        "BWS": fetch_wri_current(lat, lon, "Baseline Water Stress"),
        "T_Base": fetch_s3_climate(lat, lon, 'tas', 'historical', '1995-2014') or 15.0,
        "P_Base": fetch_s3_climate(lat, lon, 'pr', 'historical', '1995-2014') or 200.0
    }

    # Fetch Future Water (WRI)
    fw = fetch_wri_future(lat, lon)
    row.update({"WS30_Opt": fw.get("ws3024tl","N/A"), "WS30_BAU": fw.get("ws3028tl","N/A"), 
                "WS40_Opt": fw.get("ws4024tl","N/A"), "WS40_BAU": fw.get("ws4028tl","N/A")})

    # Fetch Climate Trends (AWS S3)
    row["T35_Opt"] = fetch_s3_climate(lat, lon, 'tas', 'ssp245', '2020-2039')
    row["T35_BAU"] = fetch_s3_climate(lat, lon, 'tas', 'ssp585', '2020-2039')
    row["T50_Opt"] = fetch_s3_climate(lat, lon, 'tas', 'ssp245', '2040-2059')
    row["T50_BAU"] = fetch_s3_climate(lat, lon, 'tas', 'ssp585', '2040-2059')
    row["P35_Opt"] = fetch_s3_climate(lat, lon, 'pr', 'ssp245', '2020-2039')
    row["P35_BAU"] = fetch_s3_climate(lat, lon, 'pr', 'ssp585', '2020-2039')
    row["P50_Opt"] = fetch_s3_climate(lat, lon, 'pr', 'ssp245', '2040-2059')
    row["P50_BAU"] = fetch_s3_climate(lat, lon, 'pr', 'ssp585', '2040-2059')
    
    return row

# ---------------------------------------------------------
# 5. FRONTEND UI
# ---------------------------------------------------------
st.set_page_config(page_title="Global Risk Intel", layout="wide")
st.title("🌍 Integrated Climate Risk Assessment")

t1, t2 = st.tabs(["📍 Single Location", "🚀 Batch Processing"])

with t1:
    ci1, ci2 = st.columns(2)
    lat_in = ci1.number_input("Latitude", 33.4484, format="%.4f")
    lon_in = ci2.number_input("Longitude", -112.0740, format="%.4f")
    st.map(pd.DataFrame({'lat': [lat_in], 'lon': [lon_in]}), zoom=6)

    if st.button("Generate Integrated Report"):
        with st.spinner("Accessing WRI APIs & AWS S3 Rasters..."):
            res = analyze_location(lat_in, lon_in)
        
        st.divider()
        st.subheader("⚠️ Current Hazard Profile (WRI)")
        c1, c2, c3 = st.columns(3)
        c1.metric("Drought Risk", res["Drought"])
        c2.metric("Riverine Flood", res["Riverine"])
        c3.metric("Coastal Flood", res["Coastal"])
        
        st.divider()
        st.subheader("📈 AWS Climate Pathways")
        
        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            st.write("**Temperature Profile**")
            t_chart = pd.DataFrame({
                "Year": [2010, 2035, 2050],
                "Optimistic": [res["T_Base"], res["T35_Opt"], res["T50_Opt"]],
                "BAU": [res["T_Base"], res["T35_BAU"], res["T50_BAU"]]
            }).set_index("Year")
            st.line_chart(t_chart)

        
        with chart_col2:
            st.write("**Precipitation Profile**")
            p_chart = pd.DataFrame({
                "Year": [2010, 2035, 2050],
                "Optimistic": [res["P_Base"], res["P35_Opt"], res["P50_Opt"]],
                "BAU": [res["P_Base"], res["P35_BAU"], res["P50_BAU"]]
            }).set_index("Year")
            st.line_chart(p_chart)

        st.divider()
        st.subheader("🔮 Full Risk Matrix")
        def f(v, u): return f"{v:.1f}{u}" if v is not None and not isinstance(v, str) else "N/A"
        
        table = [
            {"Metric": "Temp (Opt)", "Baseline": f(res["T_Base"],"C"), "+10Y": f(res["T35_Opt"],"C"), "+25Y": f(res["T50_Opt"],"C")},
            {"Metric": "Temp (BAU)", "Baseline": f(res["T_Base"],"C"), "+10Y": f(res["T35_BAU"],"C"), "+25Y": f(res["T50_BAU"],"C")},
            {"Metric": "Prec (Opt)", "Baseline": f(res["P_Base"],"mm"), "+10Y": f(res["P35_Opt"],"mm"), "+25Y": f(res["P50_Opt"],"mm")},
            {"Metric": "Prec (BAU)", "Baseline": f(res["P_Base"],"mm"), "+10Y": f(res["P35_BAU"],"mm"), "+25Y": f(res["P50_BAU"],"mm")},
            {"Metric": "WS (Opt)", "Baseline": res["BWS"], "+10Y": res["WS30_Opt"], "+25Y": res["WS40_Opt"]},
            {"Metric": "WS (BAU)", "Baseline": res["BWS"], "+10Y": res["WS30_BAU"], "+25Y": res["WS40_BAU"]}
        ]
        st.dataframe(pd.DataFrame(table), width='stretch', hide_index=True)

with t2:
    st.markdown("### 📥 Bulk Integrated Analysis")
    up = st.file_uploader("Upload CSV", type=["csv"])
    if up:
        df_in = pd.read_csv(up)
        if st.button("Run Batch"):
            results = []
            for i, r in df_in.iterrows():
                results.append(analyze_location(r['latitude'], r['longitude']))
                time.sleep(0.2) # Small polite delay for WRI API
            st.dataframe(pd.DataFrame(results))
