import streamlit as st
import requests

# ---------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------
# Baseline (Current) ID
BASELINE_ID = "c66d7f3a-d1a8-488f-af8b-302b0f2c3840"

# Future Projections (Aqueduct 2.1) ID
FUTURE_ID = "2a571044-1a31-4092-9af8-48f406f13072"

# ---------------------------------------------------------
# 2. BACKEND LOGIC
# ---------------------------------------------------------
def fetch_baseline_risk(lat, lon):
    """
    Fetches current Baseline Water Stress (bws).
    """
    # Clean SQL on one line
    sql_query = f"SELECT bws_label, bws_score FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    
    url = f"https://api.resourcewatch.org/v1/query/{BASELINE_ID}"
    params = {"sql": sql_query}

    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json().get('data', [])
            return data[0] if data else {"error": "No baseline data found."}
        return {"error": f"API Error: {response.text}"}
    except Exception as e:
        return {"error": str(e)}

def fetch_future_risk(lat, lon):
    """
    Fetches Future Water Stress for 2030 (Business As Usual).
    
    Schema Decoding:
    - ws (Water Stress)
    - 30 (Year 2030)
    - 28 (Scenario 28: SSP2 RCP8.5 'Business As Usual')
    - t  (Type: Future Value)
    - r  (Suffix: Raw Score)
    """
    column_score = "ws3028tr"
    column_label = "ws3028tl"
    
    sql_query = f"""
        SELECT {column_score} as score, {column_label} as label 
        FROM data 
        WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))
    """
    
    url = f"https://api.resourcewatch.org/v1/query/{FUTURE_ID}"
    params = {"sql": sql_query}

    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json().get('data', [])
            return data[0] if data else {"error": "No future data found for this location."}
        return {"error": f"API Error: {response.text}"}
    except Exception as e:
        return {"error": str(e)}

# ---------------------------------------------------------
# 3. FRONTEND UI
# ---------------------------------------------------------
st.set_page_config(page_title="Water Risk App", page_icon="💧")
st.title("💧 Water Risk Intelligence")

# Input
col1, col2 = st.columns(2)
with col1:
    lat_input = st.number_input("Latitude", value=33.4484, format="%.4f")
with col2:
    lon_input = st.number_input("Longitude", value=-112.0740, format="%.4f")

# Baseline Section
st.subheader("1. Current Baseline")
if st.button("Check Current Risk"):
    with st.spinner("Analyzing..."):
        res = fetch_baseline_risk(lat_input, lon_input)
    if "error" in res:
        st.warning(res["error"])
    else:
        score = res.get('bws_score', 'N/A')
        label = res.get('bws_label', 'Unknown')
        st.metric("Current Score", f"{score} / 5")
        st.info(f"Category: {label}")

# Future Section
st.subheader("2. 2030 Projection (BAU)")
st.caption("Scenario: SSP2 RCP8.5 (Business as Usual)")

if st.button("Predict 2030 Risk"):
    with st.spinner("Projecting..."):
        res = fetch_future_risk(lat_input, lon_input)
    if "error" in res:
        st.warning(res["error"])
    else:
        # Note: Future scores are raw values (0-5)
        f_score = res.get('score', 'N/A')
        f_label = res.get('label', 'Unknown')
        
        st.metric("2030 Projected Score", f"{f_score}")
        st.info(f"Projected Category: {f_label}")
