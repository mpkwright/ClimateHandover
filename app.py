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
@st.cache_data(ttl=3600)
def fetch_wri_current(lat, lon, risk_name):
    config = RISK_CONFIG[risk_name]
    uuid = config['uuid']
    s_col, l_col = config['cols']
    sql = f"SELECT {s_col}, {l_col} FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    url = f"https://api.resourcewatch.org/v1/query/{uuid}"
    try:
        r = requests.get(url, params={"sql": sql}, timeout=5)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data: return data[0].get(l_col, "N/A")
        return "N/A"
    except:
        return "N/A"

@st.cache_data(ttl=3600)
def fetch_wri_future(lat, lon):
    sql = f"SELECT ws3024tr, ws3024tl, ws3028tr, ws3028tl, ws4024tr, ws4024tl, ws4028tr, ws4028tl FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    url = f"https://api.resourcewatch.org/v1/query/{FUTURE_WATER_ID}"
    try:
        r = requests.get(url, params={"sql": sql}, timeout=5)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data:
                row = data[0]
                def get_val(year, scen, row_data):
                    l_key, s_key = f"ws{year}{scen}tl", f"ws{year}{scen}tr"
                    label, score = row_data.get(l_key), row_data.get(s_key)
                    if label: return label
                    if score is not None:
                        s = float(score)
                        if s >= 4: return "Extremely High (>4)"
                        if s >= 3: return "High (3-4)"
                        if s >= 2: return "Medium-High (2-3)"
                        if s >= 1: return "Low-Medium (1-2)"
                        return "Low (<1)"
                    return "N/A"
                return {
                    "ws3024tl": get_val("30", "24", row), "ws3028tl": get_val("30", "28", row),
                    "ws4024tl": get_val("40", "24", row), "ws4028tl": get_val("40", "28", row)
                }
        return {}
    except:
        return {}

# ---------------------------------------------------------
# 3. BACKEND: OPEN-METEO (Climate)
# ---------------------------------------------------------
@st.cache_data(ttl=86400)
def fetch_climate_projections(lat, lon):
    url = "https://climate-api.open-meteo.com/v1/climate"
    models = ["ec_earth3_cc", "gfdl_esm4", "ips_cm6a_lr", "mpi_esm1_2_hr", "mri_esm2_0"]
    
    params = {
        "latitude": lat, "longitude": lon,
        "start_date": "1950-01-01", "end_date": "2050-12-31",
        "models": models,
        "daily": ["temperature_2m_mean", "precipitation_sum"],
        "disable_downscaling": "false"
    }
    
    try:
        response = requests.get(url, params=params, timeout=25)
        
        # --- SAFETY: IF 429 LIMIT HIT, RETURN MOCK DATA ---
        if response.status_code == 429:
            return generate_mock_climate_data()
            
        if response.status_code != 200:
            st.error(f"Open-Meteo Error {response.status_code}")
            return None
        
        data = response.json()
        if "daily" not in data: return None
        
        daily = data["daily"]
        time = pd.to_datetime(daily["time"])
        df = pd.DataFrame(daily)
        df["time"] = time
        df.set_index("time", inplace=True)
        
        temp_cols = [c for c in df.columns if "temperature" in c]
        precip_cols = [c for c in df.columns if "precipitation" in c]
        
        # Ensemble Mean
        df["Temp_Daily_Avg"] = df[temp_cols].mean(axis=1)
        df["Precip_Daily_Avg"] = df[precip_cols].mean(axis=1)
        
        # Resample to Annual
        annual = pd.DataFrame()
        annual["Temp_Mean"] = df["Temp_Daily_Avg"].resample("Y").mean()
        annual["Precip_Mean"] = df["Precip_Daily_Avg"].resample("Y").sum()
        
        # Mark as REAL data
        annual.attrs['is_mock'] = False 
        
        return annual
        
    except Exception as e:
        st.error(f"API Failed: {e}")
        return None

def generate_mock_climate_data():
    """Generates fake data but FLAGS it so the UI knows."""
    dates = pd.date_range(start="1950-01-01", end="2050-12-31", freq="Y")
    df = pd.DataFrame(index=dates)
    
    # Random placeholder numbers
    df["Temp_Mean"] = np.linspace(15, 18, len(dates))
    df["Precip_Mean"] = np.random.normal(200, 10, len(dates))
    
    # CRITICAL: Mark this dataframe as fake using Pandas attributes
    df.attrs['is_mock'] = True
    
    return df

# ---------------------------------------------------------
# 4. FRONTEND UI
# ---------------------------------------------------------
st.set_page_config(page_title="Integrated Risk Report", page_icon="🌍", layout="wide")

st.title("🌍 Integrated Climate Risk Assessment")

col_in1, col_in2 = st.columns(2)
with col_in1:
    lat = st.number_input("Latitude", 33.4484, format="%.4f")
with col_in2:
    lon = st.number_input("Longitude", -112.0740, format="%.4f")

map_df = pd.DataFrame({'lat': [lat], 'lon': [lon]})
st.map(map_df, zoom=8)

if st.button("Generate Full Risk Report"):
    progress = st.progress(0)
    
    # 1. Hazards
    drought = fetch_wri_current(lat, lon, "Drought Risk")
    river = fetch_wri_current(lat, lon, "Riverine Flood")
    coastal = fetch_wri_current(lat, lon, "Coastal Flood")
    bws = fetch_wri_current(lat, lon, "Baseline Water Stress")
    progress.progress(30)
    
    # 2. Future Water
    wri_future = fetch_wri_future(lat, lon)
    progress.progress(60)
    
    # 3. Climate
    clim_df = fetch_climate_projections(lat, lon)
    progress.progress(90)
    
    # 4. Process Data
    scenarios = {
        "Current (Baseline)": {},
        "+10Y (Optimistic)": {}, "+10Y (BAU)": {},
        "+20Y (Optimistic)": {}, "+20Y (BAU)": {},
        "+30Y (Optimistic)": {}, "+30Y (BAU)": {},
    }
    
    if clim_df is not None:
        # CHECK: Is this data fake?
        is_mock = clim_df.attrs.get('is_mock', False)
        
        # If fake, show a giant error banner
        if is_mock:
            st.error("🚨 API LIMIT REACHED: The Climate Data below is SIMULATED/FAKE. Do not use for analysis.")
            suffix = " (SIMULATED)"
        else:
            suffix = ""

        base = clim_df.loc["1990":"2020"]
        scenarios["Current (Baseline)"] = {
            "Temp": f"{base['Temp_Mean'].mean():.1f}°C{suffix}",
            "Precip": f"{base['Precip_Mean'].mean():.0f} mm{suffix}"
        }
        
        def get_clim(year, col, unit="°C", is_sum=False):
            try:
                start, end = str(year-2), str(year+2)
                val = clim_df.loc[start:end][col].mean()
                # Append the suffix (SIMULATED) to every single value
                return f"{val:.0f} {unit}{suffix}" if is_sum else f"{val:.1f}{unit}{suffix}"
            except: return "N/A"

        for year, label in [(2035, "+10Y"), (2045, "+20Y"), (2050, "+30Y")]:
            t_val = get_clim(year, "Temp_Mean")
            p_val = get_clim(year, "Precip_Mean", "mm", True)
            
            scenarios[f"{label} (Optimistic)"]["Temp"] = t_val
            scenarios[f"{label} (Optimistic)"]["Precip"] = p_val
            scenarios[f"{label} (BAU)"]["Temp"] = t_val
            scenarios[f"{label} (BAU)"]["Precip"] = p_val

    # Water Stress
    scenarios["Current (Baseline)"]["Water Stress"] = bws
    scenarios["+10Y (Optimistic)"]["Water Stress"] = wri_future.get("ws3024tl", "N/A")
    scenarios["+10Y (BAU)"]["Water Stress"] = wri_future.get("ws3028tl", "N/A")
    scenarios["+20Y (Optimistic)"]["Water Stress"] = wri_future.get("ws4024tl", "N/A")
    scenarios["+20Y (BAU)"]["Water Stress"] = wri_future.get("ws4028tl", "N/A")
    scenarios["+30Y (Optimistic)"]["Water Stress"] = "N/A (Limit 2040)"
    scenarios["+30Y (BAU)"]["Water Stress"] = "N/A (Limit 2040)"

    progress.progress(100)
    
    st.divider()
    st.subheader("⚠️ Current Hazard Profile")
    c1, c2, c3 = st.columns(3)
    c1.metric("Drought Risk", drought)
    c2.metric("Riverine Flood", river)
    c3.metric("Coastal Flood", coastal)
    
    st.divider()
    st.subheader("🔮 Projected Trends (Ensemble Mean)")
    
    cols_order = [
        "Current (Baseline)", 
        "+10Y (Optimistic)", "+10Y (BAU)",
        "+20Y (Optimistic)", "+20Y (BAU)",
        "+30Y (Optimistic)", "+30Y (BAU)"
    ]
    
    table_data = []
    for metric in ["Temp", "Precip", "Water Stress"]:
        row = {"Metric": metric}
        for col in cols_order:
            row[col] = scenarios.get(col, {}).get(metric, "N/A")
        table_data.append(row)
        
    st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)
