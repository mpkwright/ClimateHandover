import streamlit as st
import pandas as pd
import requests
import altair as alt
from geopy.geocoders import Nominatim
import time

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Climate Risk Debugger", layout="wide")
st.title("🌍 Climate Risk Dashboard (Diagnostic Mode)")

# --- 2. INPUTS ---
with st.sidebar:
    st.header("📍 Location")
    # Defaulting to a coordinate we KNOW works for testing (Central London)
    lat = st.number_input("Latitude", value=51.5074, format="%.4f")
    lon = st.number_input("Longitude", value=-0.1278, format="%.4f")
    run_btn = st.button("Generate Analysis", type="primary")

# --- 3. RAW API FUNCTIONS (No Wrappers) ---

def get_climate_data_raw(lat, lon):
    """
    Fetches data using raw requests to ensure no hidden caching occurs.
    """
    debug_logs = []
    
    # 1. BASELINE (Historical)
    url_hist = "https://archive-api.open-meteo.com/v1/archive"
    params_hist = {
        "latitude": lat, "longitude": lon,
        "start_date": "1991-01-01", "end_date": "2020-12-31",
        "daily": ["temperature_2m_mean", "precipitation_sum"],
        "timezone": "auto"
    }
    
    try:
        r_hist = requests.get(url_hist, params=params_hist)
        data_hist = r_hist.json()
        debug_logs.append(f"✅ Baseline Status: {r_hist.status_code}")
    except Exception as e:
        return None, [f"❌ Baseline Failed: {e}"]

    # 2. FUTURE (Projections)
    # We purposefully do NOT loop yet, to test one specific call first
    url_pro = "https://climate-api.open-meteo.com/v1/climate"
    
    future_results = {}
    scenarios = ["ssp1_2_6", "ssp2_4_5", "ssp3_7_0"]
    
    for sc in scenarios:
        # We add a random 'cache_buster' param to force a new request
        params_pro = {
            "latitude": lat, "longitude": lon,
            "start_date": "2021-01-01", "end_date": "2050-12-31",
            "models": "EC_Earth3P_HR",
            "scenarios": sc, 
            "daily": ["temperature_2m_mean", "precipitation_sum"],
            "disable_bias_correction": "true",
            "cache_buster": time.time() 
        }
        
        try:
            r_pro = requests.get(url_pro, params=params_pro)
            debug_logs.append(f"👉 Scenario {sc} URL: {r_pro.url}") # SHOW THE URL
            
            if r_pro.status_code == 200:
                future_results[sc] = r_pro.json()
                # LOG FIRST VALUE to prove they are different
                first_temp = future_results[sc]['daily']['temperature_2m_mean'][0]
                debug_logs.append(f"   ✅ Data Rx. First Temp: {first_temp}")
            else:
                debug_logs.append(f"   ❌ Failed: {r_pro.text}")
        except Exception as e:
            debug_logs.append(f"   ❌ Exception: {e}")

    return {"hist": data_hist, "future": future_results}, debug_logs

def get_water_stress_raw(lat, lon):
    debug_logs = []
    
    # 1. Get Table Name for 'Water Stress Baseline' (Dataset ID: c66d7f3a-d1a8-488f-af8b-302b0f2c3840)
    meta_url = "https://api.resourcewatch.org/v1/dataset/c66d7f3a-d1a8-488f-af8b-302b0f2c3840"
    
    try:
        r_meta = requests.get(meta_url).json()
        table_name = r_meta['data']['attributes']['tableName']
        debug_logs.append(f"✅ Found Table Name: {table_name}")
    except:
        return None, ["❌ Could not fetch metadata/table name"]

    # 2. Construct SQL Query (Using ST_DWithin for 'Near' search)
    # We search within 0.1 degrees (~11km) to catch nearby basins
    sql = f"SELECT bws_label, bws_score FROM {table_name} WHERE ST_DWithin(the_geom, ST_SetSRID(ST_Point({lon}, {lat}), 4326), 0.1) LIMIT 1"
    
    query_url = f"https://api.resourcewatch.org/v1/query?sql={sql}"
    debug_logs.append(f"👉 SQL URL: {query_url}")
    
    try:
        r_query = requests.get(query_url).json()
        debug_logs.append(f"📄 Raw Response: {r_query}")
        
        if 'data' in r_query and len(r_query['data']) > 0:
            return r_query['data'][0], debug_logs
        else:
            return {"bws_label": "No Data (Ocean/Remote)"}, debug_logs
            
    except Exception as e:
        return None, [f"❌ SQL Query Failed: {e}"]

# --- 4. PROCESSING ---

def process_data(climate_raw, water_raw):
    # Quick helpers
    if not climate_raw: return pd.DataFrame()
    
    hist_temp = sum(climate_raw['hist']['daily']['temperature_2m_mean']) / len(climate_raw['hist']['daily']['temperature_2m_mean'])
    hist_precip = sum(climate_raw['hist']['daily']['precipitation_sum']) / 30.0 # approx annual
    
    rows = []
    
    # Baseline Row
    ws_label = water_raw.get('bws_label', 'Unknown') if water_raw else "Unknown"
    rows.append({
        "Scenario": "Baseline (1991-2020)",
        "Temp (Avg)": f"{hist_temp:.2f} °C",
        "Precip (Annual)": f"{hist_precip:.0f} mm",
        "Water Stress": ws_label
    })
    
    # Future Rows
    for sc, data in climate_raw['future'].items():
        if 'daily' not in data: continue
        
        temps = data['daily']['temperature_2m_mean']
        precips = data['daily']['precipitation_sum']
        
        # Simple mean of the whole 2021-2050 block for the demo
        f_temp = sum(temps) / len(temps)
        f_precip = sum(precips) / 30.0
        
        rows.append({
            "Scenario": sc,
            "Temp (Avg)": f"{f_temp:.2f} °C",
            "Precip (Annual)": f"{f_precip:.0f} mm",
            "Water Stress": "See Baseline"
        })
        
    return pd.DataFrame(rows)

# --- 5. MAIN APP ---

if run_btn:
    c1, c2 = st.columns([2, 1])
    
    with c1:
        st.subheader("📊 Analysis Results")
        with st.spinner("Pinging satellites..."):
            climate_raw, c_logs = get_climate_data_raw(lat, lon)
            water_raw, w_logs = get_water_stress_raw(lat, lon)
            
            df = process_data(climate_raw, water_raw)
            st.table(df)

    with c2:
        st.subheader("🛠️ API Debugger")
        
        with st.expander("💧 Water Stress Logs", expanded=True):
            for log in w_logs:
                st.code(log, language="text")
                
        with st.expander("☁️ Climate Data Logs", expanded=True):
            for log in c_logs:
                if "URL" in log:
                    st.markdown(f"**Request:** `{log}`")
                else:
                    st.text(log)
