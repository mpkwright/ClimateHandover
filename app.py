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
* **Baseline:** ERA5 Reanalysis (1991–2020) & WRI Aqueduct 4.0 (Actual Water Stress).
* **Future:** CMIP6 Projections (2021–2050) & WRI Future Water Stress (2030/2050).
""")

# --- 2. INPUTS ---
with st.sidebar:
    st.header("📍 Location Parameters")
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
    params_pro = {
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
        scenarios_to_fetch = {
            "ssp1_2_6": "SSP1-2.6 (Ambitious)",
            "ssp2_4_5": "SSP2-4.5 (Optimistic)",
            "ssp3_7_0": "SSP3-7.0 (BAU)"
        }
        
        for sc_key, sc_name in scenarios_to_fetch.items():
             p = params_pro.copy()
             p["scenarios"] = [sc_key]
             f_resp = openmeteo.weather_api(url_pro, params=p)[0]
             
             # Process Daily Data
             f_daily = f_resp.Daily()
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
    Uses 'ST_Intersects' to find the polygon containing the point.
    """
    
    # Dataset IDs provided by user
    ID_BASELINE = "c66d7f3a-d1a8-488f-af8b-302b0f2c3840" # wat050
    ID_FUTURE = "2a571044-1a31-4092-9af8-48f406f13072"   # wat006
    
    def get_table_name(dataset_id):
        try:
            url = f"https://api.resourcewatch.org/v1/dataset/{dataset_id}"
            r = requests.get(url).json()
            return r['data']['attributes']['tableName']
        except:
            return None

    def query_rw(table_name, cols="*"):
        try:
            sql = f"SELECT {cols} FROM {table_name} WHERE ST_Intersects(the_geom, ST_SetSRID(ST_Point({lon}, {lat}), 4326))"
            url = f"https://api.resourcewatch.org/v1/query?sql={sql}"
            r = requests.get(url).json()
            if 'data' in r and len(r['data']) > 0:
                return r['data'][0]
            return None
        except:
            return None

    # 1. Fetch Baseline Water Stress (bws)
    table_base = get_table_name(ID_BASELINE)
    base_data = query_rw(table_base, "bws_label, bws_score") if table_base else None
    
    # 2. Fetch Future Water Stress (ws)
    # Aqueduct 4.0 Columns: 'bau30_ws_x_l' (Business As Usual 2030 Label), 'opt30...', 'pes30...'
    table_future = get_table_name(ID_FUTURE)
    # We fetch key columns for 2030 and 2050 for different scenarios
    # bau = SSP3 RCP7.0 (Business as Usual)
    # opt = SSP1 RCP2.6 (Optimistic)
    # pes = SSP5 RCP8.5 (Pessimistic)
    cols_future = "bau30_ws_x_l, bau50_ws_x_l, opt30_ws_x_l, opt50_ws_x_l, pes30_ws_x_l, pes50_ws_x_l"
    future_data = query_rw(table_future, cols_future) if table_future else None
    
    return {
        "baseline": base_data,
        "future": future_data
    }

# --- 5. RISK CALCULATION & TABLE ---
def calculate_risk_table(climate_data, water_data):
    b_t = climate_data["baseline_temp"]
    b_p = climate_data["baseline_precip"]
    
    # Helper for Heat/Flood/Drought based on CLIMATE data
    def get_climate_labels(t, p):
        drought = "High" if p < 500 else ("Medium" if p < 800 else "Low")
        flood = "High" if p > 1200 else ("Medium" if p > 800 else "Low")
        wildfire = "High" if (t > 15 and p < 600) else "Low"
        return drought, flood, wildfire

    # Helper for Water Stress from WRI DATA
    def get_water_stress_label(scenario, decade):
        # Default to baseline if not found
        val = "No Data"
        if not water_data or not water_data['future']:
             return water_data['baseline']['bws_label'] if (water_data and water_data['baseline']) else "No Data"
        
        f = water_data['future']
        # Map our Scenarios to WRI Columns
        # ssp1_2_6 -> opt (Optimistic)
        # ssp2_4_5 -> bau (using BAU as proxy for middle road, though WRI BAU is usually SSP3-7.0. Close enough for demo)
        # ssp3_7_0 -> pes (Pessimistic)
        
        prefix = "bau" # default
        if "ssp1" in scenario.lower(): prefix = "opt"
        if "ssp5" in scenario.lower() or "ssp3" in scenario.lower(): prefix = "pes" # WRI BAU is SSP3
        if "ssp2" in scenario.lower(): prefix = "bau" # Approximation

        year = "30" # default
        if "2040" in decade or "2050" in decade: year = "50"
        
        key = f"{prefix}{year}_ws_x_l"
        return f.get(key, "No Data")

    rows = []
    
    # 1. Current Row
    d, f, w = get_climate_labels(b_t, b_p)
    ws_base = water_data['baseline']['bws_label'] if (water_data and water_data['baseline']) else "Unknown"
    
    rows.append({
        "Scenario": "Current Baseline",
        "Decade": "1991-2020",
        "Temp": f"{b_t:.2f} °C",
        "Precip": f"{b_p:.0f} mm",
        "Water Stress (WRI)": ws_base,
        "Drought Risk": d, "Flood Risk": f, "Wildfire Risk": w
    })
    
    # 2. Future Rows
    for sc_name, decades in climate_data["future"].items():
        for dec_name, metrics in decades.items():
            
            delta_t = metrics["temp"] - b_t
            delta_p_pct = ((metrics["precip"] - b_p) / b_p) * 100 if b_p != 0 else 0
            
            fd, ff, fw = get_climate_labels(metrics["temp"], metrics["precip"])
            wri_label = get_water_stress_label(sc_name, dec_name)
            
            rows.append({
                "Scenario": sc_name,
                "Decade": dec_name,
                "Temp": f"{'+' if delta_t>0 else ''}{delta_t:.2f} °C",
                "Precip": f"{'+' if delta_p_pct>0 else ''}{delta_p_pct:.1f} %",
                "Water Stress (WRI)": wri_label,
                "Drought Risk": fd, "Flood Risk": ff, "Wildfire Risk": fw
            })

    return pd.DataFrame(rows)

# --- 6. VISUALIZATION ---
def plot_chart(monthly):
    src = monthly.reset_index()
    src['month_name'] = pd.to_datetime(src['index'], format='%m').dt.month_name().str.slice(stop=3)
    base = alt.Chart(src).encode(x=alt.X('month_name', sort=None, title='Month'))
    bar = base.mark_bar(opacity=0.5, color='#4c78a8').encode(y='precip_total', tooltip='precip_total')
    line = base.mark_line(color='#e45756', strokeWidth=3).encode(y='temp', tooltip='temp')
    return alt.layer(bar, line).resolve_scale(y='independent').properties(title="Seasonal Baseline (1991-2020)")

def style_rows(val):
    s = str(val).lower()
    if 'high' in s or 'extremely' in s: return 'background-color: #ffcccc; color: black'
    if 'med' in s: return 'background-color: #fff4cc; color: black'
    if 'low' in s: return 'background-color: #ccffcc; color: black'
    if 'arid' in s: return 'background-color: #ffcccc; color: black'
    return ''

# --- 7. MAIN ---
if run_btn:
    with st.spinner("Fetching Climate Models & WRI Aqueduct Data..."):
        c_data = get_climate_data(lat, lon)
        w_data = get_water_risk_data(lat, lon)
        
        if c_data:
            st.subheader(f"📍 Analysis for: {get_location_name(lat, lon)}")
            st.map(pd.DataFrame({'lat':[lat], 'lon':[lon]}), zoom=4)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Baseline Temp", f"{c_data['baseline_temp']:.1f}°C")
            c2.metric("Baseline Precip", f"{c_data['baseline_precip']:.0f}mm")
            
            ws_val = w_data['baseline']['bws_label'] if (w_data and w_data['baseline']) else "N/A"
            c3.metric("Current Water Stress", ws_val)
            
            st.markdown("### 🔮 Decadal Risk Pathways")
            df = calculate_risk_table(c_data, w_data)
            
            st.dataframe(
                df.style.applymap(style_rows), 
                use_container_width=True,
                column_order=["Scenario", "Decade", "Temp", "Precip", "Water Stress (WRI)", "Drought Risk", "Flood Risk", "Wildfire Risk"]
            )
            
            st.altair_chart(plot_chart(c_data['monthly']), use_container_width=True)
        else:
            st.error("Data Unavailable.")
else:
    st.info("👈 Enter Latitude/Longitude in the sidebar and click 'Generate' to start.")
