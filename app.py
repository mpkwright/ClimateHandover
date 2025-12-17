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
    lat = st.number_input("Latitude", value=51.5074, format="%.4f")
    lon = st.number_input("Longitude", value=-0.1278, format="%.4f")
    run_btn = st.button("Generate Analysis", type="primary")

# --- 3. RAW API FUNCTIONS ---

def get_climate_data_raw(lat, lon):
    debug_logs = []
    
    # 1. BASELINE (Historical)
    url_hist = "https://archive-api.open-meteo.com/v1/archive"
    params_hist = {
        "latitude": lat, "longitude": lon,
        "start_date": "1991-01-01", "end_date": "2020-12-31",
        "daily": ["temperature_2m_mean", "precipitation_sum"],
        "timezone": "auto"
    }
    
    data_hist = None
    try:
        r_hist = requests.get(url_hist, params=params_hist)
        if r_hist.status_code == 200:
            data_hist = r_hist.json()
            debug_logs.append(f"✅ Baseline Status: 200 OK")
        else:
            debug_logs.append(f"❌ Baseline Failed: {r_hist.status_code}")
    except Exception as e:
        debug_logs.append(f"❌ Baseline Error: {e}")

    # 2. FUTURE (Projections)
    url_pro = "https://climate-api.open-meteo.com/v1/climate"
    future_results = {}
    scenarios = ["ssp1_2_6", "ssp2_4_5", "ssp3_7_0"]
    
    for sc in scenarios:
        # random cache_buster to prevent identical results
        params_pro = {
            "latitude": lat, "longitude": lon,
            "start_date": "2021-01-01", "end_date": "2050-12-31",
            "models": "EC_Earth3P_HR",
            "scenarios": sc, 
            "daily": ["temperature_2m_mean", "precipitation_sum"],
            "disable_bias_correction": "true",
            "cache_buster": int(time.time() * 1000) 
        }
        
        try:
            r_pro = requests.get(url_pro, params=params_pro)
            debug_logs.append(f"👉 Scenario {sc} URL: {r_pro.url}") 
            
            if r_pro.status_code == 200:
                future_results[sc] = r_pro.json()
                # Log first valid temp to prove data distinction
                if 'daily' in future_results[sc]:
                    vals = future_results[sc]['daily']['temperature_2m_mean']
                    first_val = next((x for x in vals if x is not None), "All None")
                    debug_logs.append(f"   ✅ First Valid Temp: {first_val}")
            else:
                debug_logs.append(f"   ❌ Failed: {r_pro.text}")
        except Exception as e:
            debug_logs.append(f"   ❌ Exception: {e}")

    return {"hist": data_hist, "future": future_results}, debug_logs

def get_water_stress_raw(lat, lon):
    debug_logs = []
    
    # 1. Get Metadata (Table Name)
    meta_url = "https://api.resourcewatch.org/v1/dataset/c66d7f3a-d1a8-488f-af8b-302b0f2c3840"
    
    try:
        r_meta = requests.get(meta_url).json()
        table_name = r_meta['data']['attributes']['tableName']
        debug_logs.append(f"✅ Found Table Name: {table_name}")
    except:
        return {"bws_label": "Meta Error"}, ["❌ Could not fetch metadata"]

    # 2. SQL Query (ST_DWithin 0.1 deg ~ 11km)
    sql = f"SELECT bws_label, bws_score FROM {table_name} WHERE ST_DWithin(the_geom, ST_SetSRID(ST_Point({lon}, {lat}), 4326), 0.1) LIMIT 1"
    query_url = f"https://api.resourcewatch.org/v1/query?sql={sql}"
    
    debug_logs.append(f"👉 SQL URL: {query_url}")
    
    try:
        r_query = requests.get(query_url).json()
        if 'data' in r_query and len(r_query['data']) > 0:
            return r_query['data'][0], debug_logs
        else:
            return {"bws_label": "No Data (Ocean/Remote)"}, debug_logs
    except Exception as e:
        return {"bws_label": "SQL Error"}, [f"❌ SQL Query Failed: {e}"]

# --- 4. PROCESSING (FIXED) ---

def process_data(climate_raw, water_raw):
    rows = []
    
    # --- Helper to clean None values ---
    def safe_mean(data_list):
        # Filter out None values
        valid = [x for x in data_list if x is not None]
        if not valid: return 0.0
        return sum(valid) / len(valid)

    def safe_sum(data_list):
        valid = [x for x in data_list if x is not None]
        return sum(valid)

    # 1. Baseline Processing
    hist_data = climate_raw.get('hist', {})
    if hist_data and 'daily' in hist_data:
        h_temps = hist_data['daily'].get('temperature_2m_mean', [])
        h_precips = hist_data['daily'].get('precipitation_sum', [])
        
        hist_temp = safe_mean(h_temps)
        hist_precip = safe_sum(h_precips) / 30.0 # Annual Avg
    else:
        hist_temp = 0.0
        hist_precip = 0.0

    ws_label = water_raw.get('bws_label', 'Unknown') if water_raw else "Unknown"
    
    rows.append({
        "Scenario": "Baseline (1991-2020)",
        "Temp (Avg)": f"{hist_temp:.2f} °C",
        "Precip (Annual)": f"{hist_precip:.0f} mm",
        "Water Stress": ws_label
    })
    
    # 2. Future Processing
    for sc, data in climate_raw['future'].items():
        if not data or 'daily' not in data: continue
        
        temps = data['daily'].get('temperature_2m_mean', [])
        precips = data['daily'].get('precipitation_sum', [])
        
        f_temp = safe_mean(temps)
        f_precip = safe_sum(precips) / 30.0
        
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
        with st.spinner("Diagnosing..."):
            climate_raw, c_logs = get_climate_data_raw(lat, lon)
            water_raw, w_logs = get_water_stress_raw(lat, lon)
            
            # Now safe to call
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
