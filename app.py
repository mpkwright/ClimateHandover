import streamlit as st
import requests
import pandas as pd
import numpy as np

# ---------------------------------------------------------
# 1. CONFIGURATION & UUIDs
# ---------------------------------------------------------
RISK_CONFIG = {
    "Baseline Water Stress": {"uuid": "c66d7f3a-d1a8-488f-af8b-302b0f2c3840", "cols": ["bws_score", "bws_label"]},
    "Drought Risk":          {"uuid": "5c9507d1-47f7-4c6a-9e64-fc210ccc48e2", "cols": ["drr_score", "drr_label"]},
    "Riverine Flood":        {"uuid": "df9ef304-672f-4c17-97f4-f9f8fa2849ff", "cols": ["rfr_score", "rfr_label"]},
    "Coastal Flood":         {"uuid": "d39919a9-0940-4038-87ac-662f944bc846", "cols": ["cfr_score", "cfr_label"]}
}
FUTURE_WATER_ID = "2a571044-1a31-4092-9af8-48f406f13072"

# ---------------------------------------------------------
# 2. BACKEND: WRI API (Hazards)
# ---------------------------------------------------------
def fetch_wri_current(lat, lon, risk_name):
    """Fetch current risk scores for a specific hazard."""
    config = RISK_CONFIG[risk_name]
    uuid = config['uuid']
    s_col, l_col = config['cols']
    
    # Flatten SQL to prevent parsing errors
    sql = f"SELECT {s_col}, {l_col} FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    url = f"https://api.resourcewatch.org/v1/query/{uuid}"
    
    try:
        r = requests.get(url, params={"sql": sql}, timeout=10)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data:
                return data[0].get(l_col, "N/A")
        return "N/A"
    except:
        return "N/A"

def fetch_wri_future(lat, lon):
    """
    Fetch Future Water Stress for 2030 & 2040.
    Fetches BOTH labels (tl) and scores (tr) to ensure no data is missed.
    """
    # Query 8 columns: 4 Scenarios * (Score + Label)
    sql = f"""
    SELECT 
        ws3024tr, ws3024tl, -- 2030 Optimistic (SSP2-4.5)
        ws3028tr, ws3028tl, -- 2030 BAU (SSP2-8.5)
        ws4024tr, ws4024tl, -- 2040 Optimistic
        ws4028tr, ws4028tl  -- 2040 BAU
    FROM data 
    WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))
    """
    
    # Flatten string for API safety
    sql = " ".join(sql.split())
    
    url = f"https://api.resourcewatch.org/v1/query/{FUTURE_WATER_ID}"
    
    try:
        r = requests.get(url, params={"sql": sql}, timeout=10)
        
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data:
                row = data[0]
                
                # Helper: If Label is missing, use Score to guess risk
                def get_val(year, scen, row_data):
                    l_key = f"ws{year}{scen}tl"
                    s_key = f"ws{year}{scen}tr"
                    
                    label = row_data.get(l_key)
                    score = row_data.get(s_key)
                    
                    if label: return label
                    
                    # Fallback logic
                    if score is not None:
                        s = float(score)
                        if s >= 4: return "Extremely High (>4)"
                        if s >= 3: return "High (3-4)"
                        if s >= 2: return "Medium-High (2-3)"
                        if s >= 1: return "Low-Medium (1-2)"
                        return "Low (<1)"
                    
                    return "N/A"

                return {
                    "ws3024tl": get_val("30", "24", row),
                    "ws3028tl": get_val("30", "28", row),
                    "ws4024tl": get_val("40", "24", row),
                    "ws4028tl": get_val("40", "28", row)
                }
        return {}
    except:
        return {}

# ---------------------------------------------------------
# 3. BACKEND: OPEN-METEO (Climate Temp/Precip)
# ---------------------------------------------------------
def fetch_climate_projections(lat, lon):
    """
    Fetch CMIP6 Climate Data (1950-2050).
    FIX: Aggregates to Annual Data PER MODEL first.
    Proxies: Min Model -> Optimistic Bound, Max Model -> BAU Bound.
    """
    url = "https://climate-api.open-meteo.com/v1/climate"
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": "1950-01-01", "end_date": "2050-12-31",
        "models": ["CMCC_CM2_VHR4", "FGOALS_f3_H", "MRI_AGCM3_2_S", "EC_Earth3P_HR", "MPI_ESM1_2_XR"],
        "daily": ["temperature_2m_mean", "precipitation_sum"],
        "disable_downscaling": "false"
    }
    
    try:
        r = requests.get(url, params=params, timeout=15)
        data = r.json()
        if "daily" not in data: return None
        
        daily = data["daily"]
        time = pd.to_datetime(daily["time"])
        
        # 1. Load Raw Data
        df_raw = pd.DataFrame(daily)
        df_raw["time"] = time
        df_raw.set_index("time", inplace=True)
        
        # 2. Identify Columns
        temp_cols = [c for c in df_raw.columns if "temperature" in c]
        precip_cols = [c for c in df_raw.columns if "precipitation" in c]
        
        # 3. Resample to ANNUAL Frequency PER MODEL FIRST
        # This is the critical fix for the "giggle test"
        annual_temp_models = df_raw[temp_cols].resample("Y").mean()
        annual_precip_models = df_raw[precip_cols].resample("Y").sum()
        
        # 4. Calculate Scenarios (Ensemble Spread)
        df_out = pd.DataFrame(index=annual_temp_models.index)
        
        # Optimistic Proxy = Min Model
        df_out["Temp_Opt"] = annual_temp_models.min(axis=1)
        df_out["Precip_Opt"] = annual_precip_models.min(axis=1)
        
        # BAU/Pessimistic Proxy = Max Model
        df_out["Temp_BAU"] = annual_temp_models.max(axis=1)
        df_out["Precip_BAU"] = annual_precip_models.max(axis=1)
        
        # Mean
        df_out["Temp_Mean"] = annual_temp_models.mean(axis=1)
        df_out["Precip_Mean"] = annual_precip_models.mean(axis=1)
        
        return df_out
        
    except Exception as e:
        return None

# ---------------------------------------------------------
# 4. FRONTEND UI
# ---------------------------------------------------------
st.set_page_config(page_title="Integrated Risk Report", page_icon="🌍", layout="wide")

st.title("🌍 Integrated Climate Risk Assessment")
st.markdown("### Location Analysis")

col_in1, col_in2 = st.columns(2)
with col_in1:
    lat = st.number_input("Latitude", 33.4484, format="%.4f")
with col_in2:
    lon = st.number_input("Longitude", -112.0740, format="%.4f")

# Map Check
map_df = pd.DataFrame({'lat': [lat], 'lon': [lon]})
st.map(map_df, zoom=8)

if st.button("Generate Full Risk Report"):
    progress = st.progress(0)
    
    # 1. Fetch Hazards
    drought = fetch_wri_current(lat, lon, "Drought Risk")
    river = fetch_wri_current(lat, lon, "Riverine Flood")
    coastal = fetch_wri_current(lat, lon, "Coastal Flood")
    bws = fetch_wri_current(lat, lon, "Baseline Water Stress")
    progress.progress(30)
    
    # 2. Fetch Future Water
    wri_future = fetch_wri_future(lat, lon)
    progress.progress(60)
    
    # 3. Fetch Climate
    clim_df = fetch_climate_projections(lat, lon)
    progress.progress(90)
    
    # 4. Process Data
    scenarios = {
        "Current (Baseline)": {},
        "+10Y (Optimistic Proxy)": {}, "+10Y (BAU Proxy)": {},
        "+20Y (Optimistic Proxy)": {}, "+20Y (BAU Proxy)": {},
        "+30Y (Optimistic Proxy)": {}, "+30Y (BAU Proxy)": {},
    }
    
    if clim_df is not None:
        # Baseline (1990-2020)
        base = clim_df.loc["1990":"2020"]
        scenarios["Current (Baseline)"] = {
            "Temp": f"{base['Temp_Mean'].mean():.1f}°C",
            "Precip": f"{base['Precip_Mean'].mean():.0f} mm"
        }
        
        def get_clim(year, col, unit="°C", is_sum=False):
            try:
                # 5-year average window
                start, end = str(year-2), str(year+2)
                val = clim_df.loc[start:end][col].mean()
                return f"{val:.0f} {unit}" if is_sum else f"{val:.1f}{unit}"
            except: return "N/A"

        # +10Y (2035)
        scenarios["+10Y (Optimistic Proxy)"]["Temp"] = get_clim(2035, "Temp_Opt")
        scenarios["+10Y (Optimistic Proxy)"]["Precip"] = get_clim(2035, "Precip_Opt", "mm", True)
        scenarios["+10Y (BAU Proxy)"]["Temp"] = get_clim(2035, "Temp_BAU")
        scenarios["+10Y (BAU Proxy)"]["Precip"] = get_clim(2035, "Precip_BAU", "mm", True)

        # +20Y (2045)
        scenarios["+20Y (Optimistic Proxy)"]["Temp"] = get_clim(2045, "Temp_Opt")
        scenarios["+20Y (Optimistic Proxy)"]["Precip"] = get_clim(2045, "Precip_Opt", "mm", True)
        scenarios["+20Y (BAU Proxy)"]["Temp"] = get_clim(2045, "Temp_BAU")
        scenarios["+20Y (BAU Proxy)"]["Precip"] = get_clim(2045, "Precip_BAU", "mm", True)
        
        # +30Y (2050)
        scenarios["+30Y (Optimistic Proxy)"]["Temp"] = get_clim(2050, "Temp_Opt")
        scenarios["+30Y (Optimistic Proxy)"]["Precip"] = get_clim(2050, "Precip_Opt", "mm", True)
        scenarios["+30Y (BAU Proxy)"]["Temp"] = get_clim(2050, "Temp_BAU")
        scenarios["+30Y (BAU Proxy)"]["Precip"] = get_clim(2050, "Precip_BAU", "mm", True)

    # Water Stress (WRI)
    scenarios["Current (Baseline)"]["Water Stress"] = bws
    
    # Map WRI 2030 -> +10Y
    scenarios["+10Y (Optimistic Proxy)"]["Water Stress"] = wri_future.get("ws3024tl", "N/A")
    scenarios["+10Y (BAU Proxy)"]["Water Stress"] = wri_future.get("ws3028tl", "N/A")
    
    # Map WRI 2040 -> +20Y
    scenarios["+20Y (Optimistic Proxy)"]["Water Stress"] = wri_future.get("ws4024tl", "N/A")
    scenarios["+20Y (BAU Proxy)"]["Water Stress"] = wri_future.get("ws4028tl", "N/A")
    
    # 2050 Limit
    scenarios["+30Y (Optimistic Proxy)"]["Water Stress"] = "N/A (Limit 2040)"
    scenarios["+30Y (BAU Proxy)"]["Water Stress"] = "N/A (Limit 2040)"

    progress.progress(100)
    
    # --- OUTPUT DISPLAY ---
    st.divider()
    
    st.subheader("⚠️ Current Hazard Profile")
    c1, c2, c3 = st.columns(3)
    c1.metric("Drought Risk", drought)
    c2.metric("Riverine Flood", river)
    c3.metric("Coastal Flood", coastal)
    
    st.divider()
    st.subheader("🔮 Projected Trends (Model Ensemble Spread)")
    
    cols_order = [
        "Current (Baseline)", 
        "+10Y (Optimistic Proxy)", "+10Y (BAU Proxy)",
        "+20Y (Optimistic Proxy)", "+20Y (BAU Proxy)",
        "+30Y (Optimistic Proxy)", "+30Y (BAU Proxy)"
    ]
    
    table_data = []
    for metric in ["Temp", "Precip", "Water Stress"]:
        row = {"Metric": metric}
        for col in cols_order:
            row[col] = scenarios.get(col, {}).get(metric, "N/A")
        table_data.append(row)
        
    st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)
    
    with st.expander("ℹ️ Data Methodology"):
        st.write("""
        - **Temperature & Precipitation:** Derived from Open-Meteo CMIP6 High-Res Ensemble (5 models). 
          - **Optimistic Proxy** = Minimum of model ensemble (Lowest Warming).
          - **BAU Proxy** = Maximum of model ensemble (Highest Warming).
          - *Note: Open-Meteo does not allow direct SSP scenario selection; min/max spread is the standard proxy.*
        - **Water Stress:** Derived from WRI Aqueduct 2.1.
          - **Optimistic** = Scenario 24 (SSP2 RCP4.5).
          - **BAU** = Scenario 28 (SSP2 RCP8.5).
        - **+10Y / +20Y / +30Y:** Approximated as 2035, 2045, and 2050 respectively.
        """)
