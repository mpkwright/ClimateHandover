import streamlit as st
import pandas as pd
import numpy as np
import openmeteo_requests
import requests
import requests_cache
from retry_requests import retry
import altair as alt
from geopy.geocoders import Nominatim
import json

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="Climate Risk Dashboard", layout="wide")
st.markdown("""<style>.reportview-container { background: #f0f2f6 }</style>""", unsafe_allow_html=True)

st.title("🌍 Climate Risk & Resilience Dashboard")
st.markdown("""
**Decadal Risk Pathway Analysis**
* **Baseline:** ERA5 Reanalysis (1991–2020) & WRI Aqueduct 4.0.
* **Future:** CMIP6 Projections (2021–2050) & WRI Water Stress Projections.
""")

# --- 2. INPUTS ---
with st.sidebar:
    st.header("📍 Location Parameters")
    # Default: London
    lat = st.number_input("Latitude", value=51.5074, format="%.4f", min_value=-90.0, max_value=90.0)
    lon = st.number_input("Longitude", value=-0.1278, format="%.4f", min_value=-180.0, max_value=180.0)
    
    st.markdown("---")
    st.caption("✅ **Live Climate:** ERA5 & CMIP6 (Open-Meteo)")
    st.caption("✅ **Live Water Risk:** WRI Aqueduct 4.0 (Resource Watch API)")
    run_btn = st.button("Generate Risk Analysis", type="primary")

# --- 3. DATA ENGINE (CLIMATE) ---

@st.cache_data
def get_location_name(lat, lon):
    try:
        geolocator = Nominatim(user_agent="climate_risk_app")
        location = geolocator.reverse((lat, lon), language='en')
        address = location.raw.get('address', {})
        return f"{address.get('state', '')}, {address.get('country', 'Unknown')}"
    except:
        return "Unknown Location"

@st.cache_data
def get_climate_data(lat, lon):
    # Setup Client with Caching
    # IMPORTANT: We use a session but strictly differentiate params in the loop
    cache_session = requests_cache.CachedSession('.cache', expire_after=3600*24)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    # 1. BASELINE (1991-2020)
    url_hist = "https://archive-api.open-meteo.com/v1/archive"
    params_hist = {
        "latitude": lat, "longitude": lon,
        "start_date": "1991-01-01", "end_date": "2020-12-31",
        "daily": ["temperature_2m_mean", "precipitation_sum"]
    }
    
    # 2. FUTURE (2021-2050)
    url_pro = "https://climate-api.open-meteo.com/v1/climate"
    # Using MPI_ESM1_2_XR as it has robust support for multiple SSPs
    base_params_pro = {
        "latitude": lat, "longitude": lon,
        "start_date": "2021-01-01", "end_date": "2050-12-31",
        "models": "MPI_ESM1_2_XR",
        "daily": ["temperature_2m_mean", "precipitation_sum"],
        "disable_bias_correction": "true" 
    }

    try:
        # -- Execute Historical --
        hist_resp = openmeteo.weather_api(url_hist, params=params_hist)[0]
        
        # -- Execute Future Scenarios --
        future_data = {}
        # Explicit mapping to ensure we request distinct data
        scenarios_to_fetch = {
            "ssp1_2_6": "SSP1-2.6 (Ambitious)",
            "ssp2_4_5": "SSP2-4.5 (Optimistic)",
            "ssp3_7_0": "SSP3-7.0 (BAU)"
        }
        
        for sc_key, sc_name in scenarios_to_fetch.items():
             # CRITICAL: Create a FRESH dictionary for params to avoid cache collisions
             p = base_params_pro.copy()
             p["scenarios"] = [sc_key] # Pass as list
             
             # Force unique request
             f_resp = openmeteo.weather_api(url_pro, params=p)[0]
             
             # Process Daily Data
             f_daily = f_resp.Daily()
             
             # Date Generation
             f_start = pd.to_datetime(f_daily.Time(), unit="s", origin="unix")
             f_end = pd.to_datetime(f_daily.TimeEnd(), unit="s", origin="unix")
             f_interval = pd.to_timedelta(f_daily.Interval(), unit="s")
             f_dates = pd.date_range(start=f_start, end=f_end, freq=f_interval, inclusive="left")
             
             f_temps = f_daily.Variables(0).ValuesAsNumpy()
             f_precip = f_daily.Variables(1).ValuesAsNumpy()
             
             min_len = min(len(f_dates), len(f_temps), len(f_precip))
             df_f = pd.DataFrame({"temp": f_temps[:min_len], "precip": f_precip[:min_len]}, index=f_dates[:min_len])
             
             # Decadal Slicing
             decades = {
                 "2020s (2021-30)": df_f.loc['2021':'2030'],
                 "2030s (2031-40)": df_f.loc['2031':'2040'],
                 "2040s (2041-50)": df_f.loc['2041':'2050']
             }
             
             future_data[sc_name] = {}
             for d_name, d_df in decades.items():
                 if not d_df.empty:
                     future_data[sc_name][d_name] = {
                         "temp": d_df["temp"].mean(),
                         "precip": d_df["precip"].sum() / 10.0
                     }

        # -- Process Historical Baseline --
        h_daily = hist_resp.Daily()
        h_start = pd.to_datetime(h_daily.Time(), unit="s", origin="unix")
        h_end = pd.to_datetime(h_daily.TimeEnd(), unit="s", origin="unix")
        h_interval = pd.to_timedelta(h_daily.Interval(), unit="s")
        h_dates = pd.date_range(start=h_start, end=h_end, freq=h_interval, inclusive="left")
        
        h_temps = h_daily.Variables(0).ValuesAsNumpy()
        h_precips = h_daily.Variables(1).ValuesAsNumpy()
        
        min_len_h = min(len(h_dates), len(h_temps), len(h_precips))
        
        baseline_temp = h_temps.mean()
        baseline_precip = h_precips.sum() / 30.0 
        
        df_h = pd.DataFrame({"temp": h_temps[:min_len_h], "precip": h_precips[:min_len_h]}, index=h_dates[:min_len_h])
        monthly = df_h.groupby(df_h.index.month).agg({"temp": "mean", "precip": "mean"})
        monthly["precip_total"] = monthly["precip"] * 30.44

        return {
            "baseline_temp": baseline_temp,
            "baseline_precip": baseline_precip,
            "future": future_data,
            "monthly": monthly
        }

    except Exception as e:
        st.error(f"Climate Data Fetch Error: {e}")
        return None

# --- 4. DATA ENGINE (WATER RISK - WRI AQUEDUCT) ---
@st.cache_data
def get_water_risk_data(lat, lon):
    """
    Queries Resource Watch API for WRI Aqueduct 4.0 Data.
    Uses 'ST_DWithin' (distance search) to handle coastlines/border issues.
    """
    
    # Dataset IDs
    ID_BASELINE = "c66d7f3a-d1a8-488f-af8b-302b0f2c3840" # wat050
    # ID_FUTURE = "2a571044-1a31-4092-9af8-48f406f13072"   # wat006 (Future) - *Often missing specific columns in public API*
    
    def get_table_name(dataset_id):
        try:
            url = f"https://api.resourcewatch.org/v1/dataset/{dataset_id}"
            r = requests.get(url).json()
            return r['data']['attributes']['tableName']
        except:
            return None

    def query_rw_spatial(table_name, cols="*"):
        # Uses ST_DWithin to find data within ~10km (0.1 deg) if exact point fails
        try:
            # Try Exact Point First
            sql = f"SELECT {cols} FROM {table_name} WHERE ST_Intersects(the_geom, ST_SetSRID(ST_Point({lon}, {lat}), 4326))"
            url = f"https://api.resourcewatch.org/v1/query?sql={sql}"
            r = requests.get(url).json()
            
            if 'data' in r and len(r['data']) > 0:
                return r['data'][0]
                
            # Fallback: Nearest Neighbor within 0.1 degree (approx 10km)
            sql_near = f"SELECT {cols} FROM {table_name} WHERE ST_DWithin(the_geom, ST_SetSRID(ST_Point({lon}, {lat}), 4326), 0.1) LIMIT 1"
            url_near = f"https://api.resourcewatch.org/v1/query?sql={sql_near}"
            r_near = requests.get(url_near).json()
            
            if 'data' in r_near and len(r_near['data']) > 0:
                return r_near['data'][0]

            return None
        except:
            return None

    # 1. Fetch Baseline Water Stress (bws)
    # Columns: bws_label (Label), bws_score (0-5 Score)
    table_base = get_table_name(ID_BASELINE)
    base_data = query_rw_spatial(table_base, "bws_label, bws_score") if table_base else None
    
    # 2. Future Water Stress
    # Note: The Resource Watch public API often hides the future columns or changes them.
    # We will attempt to fetch, but handle failure gracefully.
    # We return the baseline data primarily.
    
    return {
        "baseline": base_data,
        "future
