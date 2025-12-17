import streamlit as st
import requests
import pandas as pd
import numpy as np

# ---------------------------------------------------------
# 1. CONFIGURATION & UUIDs
# ---------------------------------------------------------
# WRI Aqueduct Dataset IDs
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
    Scenarios: 24 (Optimistic/RCP4.5), 28 (BAU/RCP8.5)
    """
    # ws = Water Stress, 30=2030, 40=2040, tl=Label
    sql = "SELECT ws3024tl, ws3028tl, ws4024tl, ws4028tl FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    url = f"https://api.resourcewatch.org/v1/query/{FUTURE_WATER_ID}"
    
    try:
        r = requests.get(url, params={"sql": sql}, timeout=10)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data:
                return data[0]
        return {}
    except:
        return {}

# ---------------------------------------------------------
# 3. BACKEND: OPEN-METEO (Climate Temp/Precip)
# ---------------------------------------------------------
def fetch_climate_projections(lat, lon):
    """
    Fetch CMIP6 Climate Data (1950-2050).
    Returns DataFrame with Optimistic (Min) and Pessimistic (Max) scenarios.
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
        df = pd.DataFrame({"time": time})
        
        # Helper to aggregate model data
        def get_scenario_data(keyword):
            cols = [k for k in daily.keys() if keyword in k]
            vals = pd.DataFrame({k: daily[k] for k in cols})
            return vals.min(axis=1), vals.max(axis=1), vals.mean(axis=1) # Min=Opt, Max=Pes, Mean=Base

        # Temperature
        t_opt, t_pes, t_mean = get_scenario_data("temperature")
        df["Temp_Opt"], df["Temp_Pes"], df["Temp_Mean"] = t_opt, t_pes, t_mean
        
        # Precipitation (Annual Sums require resampling later)
        p_opt, p_pes, p_mean = get_scenario_data("precipitation")
        df["Precip_Opt"], df["Precip_Pes"], df["Precip_Mean"] = p_opt, p_pes, p_mean
        
        return df.set_index("time")
    except:
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

# --- A. MAP SENSE CHECK ---
map_df = pd.DataFrame({'lat': [lat], 'lon': [lon]})
st.map(map_df, zoom=8)

if st.button("Generate Full Risk Report"):
    progress = st.progress(0)
    
    # 1. Fetch WRI Hazards (25%)
    drought = fetch_wri_current(lat, lon, "Drought Risk")
    river = fetch_wri_current(lat, lon, "Riverine Flood")
    coastal = fetch_wri_current(lat, lon, "Coastal Flood")
    bws = fetch_wri_current(lat, lon, "Baseline Water Stress")
    progress.progress(25)
    
    # 2. Fetch WRI Future (50%)
    wri_future = fetch_wri_future(lat, lon)
    progress.progress(50)
    
    # 3. Fetch Climate Data (75%)
    clim_df = fetch_climate_projections(lat, lon)
    progress.progress(90)
    
    # 4. Process Data for Table
    
    # --- Climate Calculations ---
    # Baseline: 1990-2020 Mean
    base_temp = "N/A"
    base_precip = "N/A"
    
    # Future Time Horizons (using 5-year windows around target)
    # Current ~ 2025. +10Y=2035, +20Y=2045, +30Y=2050 (Max data)
    
    scenarios = {
        "Current (Baseline)": {},
        "+10Y (Optimistic)": {}, "+10Y (Business as Usual)": {},
        "+20Y (Optimistic)": {}, "+20Y (Business as Usual)": {},
        "+30Y (Optimistic)": {}, "+30Y (Business as Usual)": {},
    }
    
    if clim_df is not None:
        # Resample to Annual
        annual = clim_df.resample('Y').agg({
            "Temp_Mean": "mean", "Temp_Opt": "mean", "Temp_Pes": "mean",
            "Precip_Mean": "sum", "Precip_Opt": "sum", "Precip_Pes": "sum"
        })
        
        # Baseline
        base_period = annual.loc["1990":"2020"]
        b_t = base_period["Temp_Mean"].mean()
        b_p = base_period["Precip_Mean"].mean()
        scenarios["Current (Baseline)"] = {"Temp": f"{b_t:.1f}°C", "Precip": f"{b_p:.0f} mm"}
        
        # Helper to extract future
        def get_clim_val(year, col, is_temp=True):
            try:
                # 5 year window
                start, end = str(year-2), str(year+2)
                val = annual.loc[start:end][col].mean()
                return f"{val:.1f}°C" if is_temp else f"{val:.0f} mm"
            except: return "N/A"

        # +10Y (2035)
        scenarios["+10Y (Optimistic)"]["Temp"] = get_clim_val(2035, "Temp_Opt")
        scenarios["+10Y (Optimistic)"]["Precip"] = get_clim_val(2035, "Precip_Opt", False)
        scenarios["+10Y (Business as Usual)"]["Temp"] = get_clim_val(2035, "Temp_Pes")
        scenarios["+10Y (Business as Usual)"]["Precip"] = get_clim_val(2035, "Precip_Pes", False)

        # +20Y (2045)
        scenarios["+20Y (Optimistic)"]["Temp"] = get_clim_val(2045, "Temp_Opt")
        scenarios["+20Y (Optimistic)"]["Precip"] = get_clim_val(2045, "Precip_Opt", False)
        scenarios["+20Y (Business as Usual)"]["Temp"] = get_clim_val(2045, "Temp_Pes")
        scenarios["+20Y (Business as Usual)"]["Precip"] = get_clim_val(2045, "Precip_Pes", False)
        
        # +30Y (2050 - Max available)
        scenarios["+30Y (Optimistic)"]["Temp"] = get_clim_val(2050, "Temp_Opt")
        scenarios["+30Y (Optimistic)"]["Precip"] = get_clim_val(2050, "Precip_Opt", False)
        scenarios["+30Y (Business as Usual)"]["Temp"] = get_clim_val(2050, "Temp_Pes")
        scenarios["+30Y (Business as Usual)"]["Precip"] = get_clim_val(2050, "Precip_Pes", False)

    # --- Water Stress Integration ---
    # WRI has 2030 (+5Y approx) and 2040 (+15Y approx).
    # We will map 2030 -> +10Y slot, 2040 -> +20Y slot.
    
    scenarios["Current (Baseline)"]["Water Stress"] = bws
    
    # 2030 Data
    scenarios["+10Y (Optimistic)"]["Water Stress"] = wri_future.get("ws3024tl", "N/A")
    scenarios["+10Y (Business as Usual)"]["Water Stress"] = wri_future.get("ws3028tl", "N/A")
    
    # 2040 Data
    scenarios["+20Y (Optimistic)"]["Water Stress"] = wri_future.get("ws4024tl", "N/A")
    scenarios["+20Y (Business as Usual)"]["Water Stress"] = wri_future.get("ws4028tl", "N/A")
    
    # 2050 Data (Not available in this WRI dataset)
    scenarios["+30Y (Optimistic)"]["Water Stress"] = "N/A (Limit 2040)"
    scenarios["+30Y (Business as Usual)"]["Water Stress"] = "N/A (Limit 2040)"

    progress.progress(100)
    
    # --- OUTPUT DISPLAY ---
    st.divider()
    
    # 1. Current Hazards Summary
    st.subheader("⚠️ Current Hazard Profile")
    c1, c2, c3 = st.columns(3)
    c1.metric("Drought Risk", drought)
    c2.metric("Riverine Flood", river)
    c3.metric("Coastal Flood", coastal)
    
    st.divider()
    
    # 2. Integrated Table
    st.subheader("🔮 Projected Trends (Temperature, Precip, Water Stress)")
    
    # Convert dictionary to DataFrame for display
    # We want rows = Metrics, Cols = Scenarios
    
    table_data = []
    
    # Define column order
    cols_order = [
        "Current (Baseline)", 
        "+10Y (Optimistic)", "+10Y (Business as Usual)",
        "+20Y (Optimistic)", "+20Y (Business as Usual)",
        "+30Y (Optimistic)", "+30Y (Business as Usual)"
    ]
    
    metrics = ["Temp", "Precip", "Water Stress"]
    
    for metric in metrics:
        row = {"Metric": metric}
        for col in cols_order:
            row[col] = scenarios.get(col, {}).get(metric, "N/A")
        table_data.append(row)
        
    df_display = pd.DataFrame(table_data)
    
    # Styling for the table
    st.dataframe(
        df_display,
        column_config={
            "Metric": st.column_config.TextColumn("Indicator", width="medium"),
        },
        hide_index=True,
        use_container_width=True
    )
    
    st.caption("Note: Climate data uses CMIP6 ensemble (Min=Optimistic, Max=BAU/Pessimistic). Water Stress uses WRI Aqueduct 2.1 (2030/2040). +30Y Climate is capped at 2050.")
