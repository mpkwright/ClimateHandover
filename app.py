import streamlit as st
import requests
import pandas as pd
import numpy as np
import time

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
        if response.status_code == 429: return generate_mock_climate_data()
        if response.status_code != 200: return None
        
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
        
        annual = pd.DataFrame()
        annual["Temp_Mean"] = df["Temp_Daily_Avg"].resample("Y").mean()
        annual["Precip_Mean"] = df["Precip_Daily_Avg"].resample("Y").sum()
        annual.attrs['is_mock'] = False 
        return annual
    except:
        return None

def generate_mock_climate_data():
    dates = pd.date_range(start="1950-01-01", end="2050-12-31", freq="Y")
    df = pd.DataFrame(index=dates)
    df["Temp_Mean"] = np.linspace(15, 18, len(dates))
    df["Precip_Mean"] = np.random.normal(200, 10, len(dates))
    df.attrs['is_mock'] = True
    return df

# ---------------------------------------------------------
# 4. HELPER: BATCH PROCESSOR
# ---------------------------------------------------------
def analyze_single_location(lat, lon):
    """Runs all fetchers for a single point and returns a flat dictionary row."""
    # 1. Hazards
    row = {
        "Latitude": lat, "Longitude": lon,
        "Drought Risk": fetch_wri_current(lat, lon, "Drought Risk"),
        "Riverine Flood": fetch_wri_current(lat, lon, "Riverine Flood"),
        "Coastal Flood": fetch_wri_current(lat, lon, "Coastal Flood"),
        "Baseline Water Stress": fetch_wri_current(lat, lon, "Baseline Water Stress")
    }
    
    # 2. Future Water
    fw = fetch_wri_future(lat, lon)
    row["WS_2030_Opt"] = fw.get("ws3024tl", "N/A")
    row["WS_2030_BAU"] = fw.get("ws3028tl", "N/A")
    row["WS_2040_Opt"] = fw.get("ws4024tl", "N/A")
    row["WS_2040_BAU"] = fw.get("ws4028tl", "N/A")

    # 3. Climate
    clim = fetch_climate_projections(lat, lon)
    if clim is not None:
        is_mock = clim.attrs.get('is_mock', False)
        suffix = " (SIM)" if is_mock else ""
        
        # Baseline
        base = clim.loc["1990":"2020"]
        row["Temp_Baseline"] = f"{base['Temp_Mean'].mean():.1f}C{suffix}"
        row["Precip_Baseline"] = f"{base['Precip_Mean'].mean():.0f}mm{suffix}"
        
        def get_c(y, col, is_s=False):
            try:
                s, e = str(y-2), str(y+2)
                v = clim.loc[s:e][col].mean()
                return f"{v:.0f}mm{suffix}" if is_s else f"{v:.1f}C{suffix}"
            except: return "N/A"

        # Projections
        for y in [2035, 2045, 2050]:
            row[f"Temp_{y}"] = get_c(y, "Temp_Mean")
            row[f"Precip_{y}"] = get_c(y, "Precip_Mean", True)
    else:
        # Fill N/As if climate failed
        cols = ["Temp_Baseline", "Precip_Baseline"] + [f"{m}_{y}" for y in [2035,2045,2050] for m in ["Temp", "Precip"]]
        for c in cols: row[c] = "N/A"
            
    return row

# ---------------------------------------------------------
# 5. FRONTEND UI
# ---------------------------------------------------------
st.set_page_config(page_title="Climate Risk Intelligence", page_icon="🌍", layout="wide")
st.title("🌍 Integrated Climate Risk Assessment")

tab1, tab2 = st.tabs(["📍 Single Location", "🚀 Batch Processing"])

# --- TAB 1: SINGLE LOCATION ---
with tab1:
    col_in1, col_in2 = st.columns(2)
    with col_in1:
        lat = st.number_input("Latitude", 33.4484, format="%.4f")
    with col_in2:
        lon = st.number_input("Longitude", -112.0740, format="%.4f")

    map_df = pd.DataFrame({'lat': [lat], 'lon': [lon]})
    st.map(map_df, zoom=8)

    if st.button("Generate Risk Report", key="btn_single"):
        # (Re-using the logic from previous steps, wrapped concisely)
        with st.spinner("Analyzing..."):
            data_row = analyze_single_location(lat, lon)
            
        # Display Hazards
        st.divider()
        st.subheader("⚠️ Current Hazard Profile")
        c1, c2, c3 = st.columns(3)
        c1.metric("Drought", data_row["Drought Risk"])
        c2.metric("Riverine Flood", data_row["Riverine Flood"])
        c3.metric("Coastal Flood", data_row["Coastal Flood"])
        
        # Display Table
        st.divider()
        st.subheader("🔮 Projected Trends")
        
        # Transform flat row back to table for display
        table_data = [
            {"Metric": "Temp", "Current": data_row.get("Temp_Baseline"), 
             "+10Y (2035)": data_row.get("Temp_2035"), "+20Y (2045)": data_row.get("Temp_2045"), "+30Y (2050)": data_row.get("Temp_2050")},
             
            {"Metric": "Precip", "Current": data_row.get("Precip_Baseline"), 
             "+10Y (2035)": data_row.get("Precip_2035"), "+20Y (2045)": data_row.get("Precip_2045"), "+30Y (2050)": data_row.get("Precip_2050")},
             
            {"Metric": "Water Stress (Opt)", "Current": data_row["Baseline Water Stress"],
             "+10Y (2035)": data_row["WS_2030_Opt"], "+20Y (2045)": data_row["WS_2040_Opt"], "+30Y (2050)": "N/A"},
             
            {"Metric": "Water Stress (BAU)", "Current": data_row["Baseline Water Stress"],
             "+10Y (2035)": data_row["WS_2030_BAU"], "+20Y (2045)": data_row["WS_2040_BAU"], "+30Y (2050)": "N/A"}
        ]
        st.dataframe(pd.DataFrame(table_data), use_container_width=True)

# --- TAB 2: BATCH PROCESSING ---
with tab2:
    st.markdown("### 📥 Bulk Analysis")
    st.info("Upload a CSV file with columns named `latitude` and `longitude`.")
    
    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])
    
    if uploaded_file:
        df_input = pd.read_csv(uploaded_file)
        
        # Validate columns
        required_cols = {'latitude', 'longitude'}
        if not required_cols.issubset(df_input.columns.str.lower()):
            st.error(f"CSV must contain 'latitude' and 'longitude' columns. Found: {list(df_input.columns)}")
        else:
            # Normalize column names
            df_input.columns = df_input.columns.str.lower()
            
            if st.button("Run Batch Analysis"):
                results = []
                progress_bar = st.progress(0)
                total_rows = len(df_input)
                
                status_text = st.empty()
                
                for index, row in df_input.iterrows():
                    # Update UI
                    status_text.text(f"Processing row {index + 1} of {total_rows}...")
                    progress_bar.progress((index + 1) / total_rows)
                    
                    # Analyze
                    r_lat, r_lon = row['latitude'], row['longitude']
                    analysis = analyze_single_location(r_lat, r_lon)
                    
                    # Add ID if exists, else Index
                    if 'id' in row: analysis['ID'] = row['id']
                    
                    results.append(analysis)
                    
                    # Rate Limit Pause (Politeness)
                    time.sleep(0.5)
                
                # Complete
                df_results = pd.DataFrame(results)
                st.success("Analysis Complete!")
                st.dataframe(df_results)
                
                # Download
                csv = df_results.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="💾 Download Results as CSV",
                    data=csv,
                    file_name="climate_risk_results.csv",
                    mime="text/csv",
                )
