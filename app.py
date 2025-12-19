import streamlit as st
import requests
import pandas as pd
import numpy as np
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

    if st.session_state.get("password_correct", False):
        return True

    st.title("🔒 Access Protected")
    st.text_input("Please enter the access password", type="password", on_change=password_entered, key="password")
    
    if "password_correct" in st.session_state and not st.session_state["password_correct"]:
        st.error("😕 Password incorrect")
    return False

if not check_password():
    st.stop()

# ---------------------------------------------------------
# 1. ROBUST CONNECTION CONFIGURATION
# ---------------------------------------------------------
def get_robust_session():
    """Creates a session that identifies as a browser and retries on blips."""
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    # Browsers are less likely to be throttled than "python-requests"
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
# 3. BACKEND API FETCHERS
# ---------------------------------------------------------
@st.cache_data(ttl=3600)
def fetch_wri_current(lat, lon, risk_name):
    config = RISK_CONFIG[risk_name]
    uuid, (s_col, l_col) = config['uuid'], config['cols']
    sql = f"SELECT {s_col}, {l_col} FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    try:
        r = http.get(f"https://api.resourcewatch.org/v1/query/{uuid}", params={"sql": sql}, timeout=15)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data: return data[0].get(l_col, "N/A")
        return "N/A"
    except: return "N/A"

@st.cache_data(ttl=3600)
def fetch_wri_future(lat, lon):
    sql = f"SELECT ws3024tr, ws3024tl, ws3028tr, ws3028tl, ws4024tr, ws4024tl, ws4028tr, ws4028tl FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    try:
        r = http.get(f"https://api.resourcewatch.org/v1/query/{FUTURE_WATER_ID}", params={"sql": sql}, timeout=15)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data:
                row = data[0]
                def get_val(y, s, d):
                    l, sc = d.get(f"ws{y}{s}tl"), d.get(f"ws{y}{s}tr")
                    if l: return l
                    if sc is not None:
                        val = float(sc)
                        if val >= 4: return "Extremely High (>4)"
                        if val >= 3: return "High (3-4)"
                        if val >= 2: return "Medium-High (2-3)"
                        if val >= 1: return "Low-Medium (1-2)"
                        return "Low (<1)"
                    return "N/A"
                return {"ws3024tl": get_val("30","24",row), "ws3028tl": get_val("30","28",row),
                        "ws4024tl": get_val("40","24",row), "ws4028tl": get_val("40","28",row)}
        return {}
    except: return {}

@st.cache_data(ttl=86400)
def fetch_climate_projections(lat, lon):
    url = "https://climate-api.open-meteo.com/v1/climate"
    models = ["ec_earth3_cc", "gfdl_esm4", "ips_cm6a_lr", "mpi_esm1_2_hr", "mri_esm2_0"]
    params = {"latitude": lat, "longitude": lon, "start_date": "1950-01-01", "end_date": "2050-12-31", "models": models, "daily": ["temperature_2m_mean", "precipitation_sum"], "disable_downscaling": "false"}
    try:
        r = http.get(url, params=params, timeout=30)
        if r.status_code == 429: return generate_mock_climate_data()
        if r.status_code != 200: return None
        data = r.json()
        daily = data["daily"]
        df = pd.DataFrame(daily)
        df["time"] = pd.to_datetime(daily["time"])
        df.set_index("time", inplace=True)
        df["Temp_Mean"] = df[[c for c in df.columns if "temperature" in c]].mean(axis=1)
        df["Precip_Mean"] = df[[c for c in df.columns if "precipitation" in c]].mean(axis=1)
        annual = pd.DataFrame()
        annual["Temp_Mean"] = df["Temp_Mean"].resample("Y").mean()
        annual["Precip_Mean"] = df["Precip_Mean"].resample("Y").sum()
        annual.attrs['is_mock'] = False 
        return annual
    except: return None

def generate_mock_climate_data():
    dates = pd.date_range(start="1950-01-01", end="2050-12-31", freq="Y")
    df = pd.DataFrame({"Temp_Mean": np.linspace(15, 18, len(dates)), "Precip_Mean": np.random.normal(200, 10, len(dates))}, index=dates)
    df.attrs['is_mock'] = True
    return df

# ---------------------------------------------------------
# 4. ANALYSIS ENGINE (STABILITY & INITIALIZATION)
# ---------------------------------------------------------
def analyze_location(lat, lon):
    # Initialize dictionary to prevent KeyError if an API fails
    row = {
        "Latitude": lat, "Longitude": lon, 
        "Drought": "N/A", "Riverine": "N/A", "Coastal": "N/A", "BWS": "N/A",
        "WS30_Opt": "N/A", "WS30_BAU": "N/A", "WS40_Opt": "N/A", "WS40_BAU": "N/A",
        "Temp_Base": "N/A", "Prec_Base": "N/A",
        "Temp_2035": "N/A", "Prec_2035": "N/A",
        "Temp_2045": "N/A", "Prec_2045": "N/A",
        "Temp_2050": "N/A", "Prec_2050": "N/A"
    }
    
    row["Drought"] = fetch_wri_current(lat, lon, "Drought Risk")
    row["Riverine"] = fetch_wri_current(lat, lon, "Riverine Flood")
    row["Coastal"] = fetch_wri_current(lat, lon, "Coastal Flood")
    row["BWS"] = fetch_wri_current(lat, lon, "Baseline Water Stress")
    
    fw = fetch_wri_future(lat, lon)
    row.update({"WS30_Opt": fw.get("ws3024tl","N/A"), "WS30_BAU": fw.get("ws3028tl","N/A"), "WS40_Opt": fw.get("ws4024tl","N/A"), "WS40_BAU": fw.get("ws4028tl","N/A")})
    
    clim = fetch_climate_projections(lat, lon)
    if clim is not None:
        suff = " (SIM)" if clim.attrs.get('is_mock', False) else ""
        base = clim.loc["1990":"2020"]
        if not base.empty:
            row["Temp_Base"] = f"{base['Temp_Mean'].mean():.1f}C{suff}"
            row["Prec_Base"] = f"{base['Precip_Mean'].mean():.0f}mm{suff}"
        
        def get_c(y, col, is_s=False):
            try:
                v = clim.loc[str(y-2):str(y+2)][col].mean()
                return f"{v:.0f}mm{suff}" if is_s else f"{v:.1f}C{suff}"
            except: return "N/A"
        for y in [2035, 2045, 2050]:
            row[f"Temp_{y}"] = get_c(y, "Temp_Mean")
            row[f"Prec_{y}"] = get_c(y, "Precip_Mean", True)
    return row

# ---------------------------------------------------------
# 5. FRONTEND UI
# ---------------------------------------------------------
st.set_page_config(page_title="Climate Risk Intelligence", page_icon="🌍", layout="wide")
st.title("🌍 Integrated Climate Risk Assessment")

t1, t2 = st.tabs(["📍 Single Location", "🚀 Batch Processing"])

with t1:
    ci1, ci2 = st.columns(2)
    lat_in = ci1.number_input("Latitude", 33.4484, format="%.4f")
    lon_in = ci2.number_input("Longitude", -112.0740, format="%.4f")
    st.map(pd.DataFrame({'lat': [lat_in], 'lon': [lon_in]}), zoom=8)

    if st.button("Generate Risk Report"):
        with st.spinner("Analyzing..."):
            res = analyze_location(lat_in, lon_in)
        st.divider()
        st.subheader("⚠️ Current Hazard Profile")
        c1, c2, c3 = st.columns(3)
        c1.metric("Drought", res["Drought"])
        c2.metric("Riverine", res["Riverine"])
        c3.metric("Coastal", res["Coastal"])
        
        st.divider()
        st.subheader("🔮 Projected Trends")
        table = [
            {"Metric": "Temp", "Current": res.get("Temp_Base", "N/A"), "+10Y (2035)": res.get("Temp_2035", "N/A"), "+20Y (2045)": res.get("Temp_2045", "N/A"), "+30Y (2050)": res.get("Temp_2050", "N/A")},
            {"Metric": "Precip", "Current": res.get("Prec_Base", "N/A"), "+10Y (2035)": res.get("Prec_2035", "N/A"), "+20Y (2045)": res.get("Prec_2045", "N/A"), "+30Y (2050)": res.get("Prec_2050", "N/A")},
            {"Metric": "WS (Opt)", "Current": res.get("BWS", "N/A"), "+10Y (2035)": res.get("WS30_Opt", "N/A"), "+20Y (2045)": res.get("WS40_Opt", "N/A"), "+30Y (2050)": "N/A"},
            {"Metric": "WS (BAU)", "Current": res.get("BWS", "N/A"), "+10Y (2035)": res.get("WS30_BAU", "N/A"), "+20Y (2045)": res.get("WS40_BAU", "N/A"), "+30Y (2050)": "N/A"}
        ]
        st.dataframe(pd.DataFrame(table), use_container_width=True, hide_index=True)

with t2:
    st.markdown("### 📥 Bulk Analysis")
    up = st.file_uploader("Upload CSV (must have 'latitude' and 'longitude')", type=["csv"])
    if up:
        df_in = pd.read_csv(up)
        df_in.columns = df_in.columns.str.lower()
        if st.button("Run Batch Analysis"):
            results, prog = [], st.progress(0)
            status = st.empty()
            for i, r in df_in.iterrows():
                status.text(f"Processing {i+1}/{len(df_in)}...")
                res = analyze_location(r['latitude'], r['longitude'])
                if 'id' in r: res['ID'] = r['id']
                results.append(res)
                prog.progress((i+1)/len(df_in))
                time.sleep(0.5)
            df_res = pd.DataFrame(results)
            st.success("Batch Complete!")
            st.dataframe(df_res)
            st.download_button("💾 Download Results", df_res.to_csv(index=False).encode('utf-8'), "risk_results.csv", "text/csv")
