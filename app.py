import streamlit as st
import requests

# ---------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------
# We use the UUID for the endpoint...
DATASET_ID = "c66d7f3a-d1a8-488f-af8b-302b0f2c3840"
# ...but we MUST use this specific Table Name for the SQL query to work
TABLE_NAME = "wat_050_aqueduct_baseline_water_stress"

# ---------------------------------------------------------
# 2. BACKEND FUNCTION
# ---------------------------------------------------------
def fetch_water_risk(lat, lon):
    """
    Queries the WRI API for water risk data at a specific lat/lon.
    """
    # FIX: We use the explicit table name here, not the ID
    sql_query = f"""
        SELECT bws_label, bws_score 
        FROM {TABLE_NAME} 
        WHERE ST_Intersects(the_geom, ST_SetSRID(ST_Point({lon}, {lat}), 4326))
    """
    
    # We still send the request to the Dataset ID endpoint
    url = f"https://api.resourcewatch.org/v1/query/{DATASET_ID}"
    params = {"sql": sql_query}

    try:
        response = requests.get(url, params=params)
        
        # If the query fails, return the raw error so we can see it
        if response.status_code != 200:
            return {"error": f"API Error {response.status_code}: {response.text}"}

        data = response.json().get('data', [])
        
        if data:
            return data[0]
        else:
            # If valid query but no intersection (e.g. ocean)
            return {"error": "No data at this location (Ocean or out of bounds)."}
            
    except Exception as e:
        return {"error": str(e)}

# ---------------------------------------------------------
# 3. FRONTEND UI
# ---------------------------------------------------------
st.title("💧 Water Risk Checker")
st.markdown("Enter coordinates to check **Baseline Water Stress**.")

# 1. Input Section
col1, col2 = st.columns(2)
with col1:
    lat_input = st.number_input("Latitude", value=33.4484, format="%.4f") # Default: Phoenix
with col2:
    lon_input = st.number_input("Longitude", value=-112.0740, format="%.4f")

# 2. Button Action
if st.button("Check Risk Level"):
    with st.spinner("Querying WRI Database..."):
        result = fetch_water_risk(lat_input, lon_input)
    
    # 3. Result Display
    if "error" in result:
        st.warning(result["error"])
    else:
        label = result.get('bws_label', 'Unknown')
        score = result.get('bws_score', 'N/A')
        
        # Dynamic color coding
        if score != 'N/A':
            score_val = float(score)
            if score_val >= 4:
                st.error(f"🔥 EXTREME RISK ({label})")
            elif score_val >= 3:
                st.warning(f"⚠️ HIGH RISK ({label})")
            else:
                st.success(f"✅ LOW/MEDIUM RISK ({label})")
        
        st.metric("Water Stress Score", f"{score} / 5")
