import streamlit as st
import requests

# ---------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------
# The UUID for the "Aqueduct Baseline Water Stress" dataset
DATASET_ID = "c66d7f3a-d1a8-488f-af8b-302b0f2c3840"

# ---------------------------------------------------------
# 2. BACKEND FUNCTION (Logic only, no display)
# ---------------------------------------------------------
def fetch_water_risk(lat, lon):
    """
    Queries the WRI API for water risk data at a specific lat/lon.
    Returns a dictionary with data or None if failed.
    """
    # SQL query to find the polygon containing the point
    sql_query = f"""
        SELECT bws_label, bws_score 
        FROM {DATASET_ID} 
        WHERE ST_Intersects(the_geom, ST_SetSRID(ST_Point({lon}, {lat}), 4326))
    """
    
    url = f"https://api.resourcewatch.org/v1/query/{DATASET_ID}"
    params = {"sql": sql_query}

    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json().get('data', [])
            if data:
                return data[0]  # Return the first match
            else:
                return {"error": "No data found for this location."}
        else:
            return {"error": f"API Error: {response.status_code}"}
    except Exception as e:
        return {"error": str(e)}

# ---------------------------------------------------------
# 3. FRONTEND (The Streamlit UI)
# ---------------------------------------------------------
st.title("💧 Water Risk Checker")
st.markdown("Enter coordinates to check the **Baseline Water Stress** from the WRI Aqueduct dataset.")

# Input columns
col1, col2 = st.columns(2)
with col1:
    lat_input = st.number_input("Latitude", value=51.5074, format="%.4f")
with col2:
    lon_input = st.number_input("Longitude", value=-0.1278, format="%.4f")

if st.button("Check Risk Level"):
    with st.spinner("Querying WRI Database..."):
        result = fetch_water_risk(lat_input, lon_input)
    
    # Check if we got a valid result or an error
    if "error" in result:
        st.warning(result["error"])
    else:
        # Success! Display Metrics
        label = result.get('bws_label', 'Unknown')
        score = result.get('bws_score', 'N/A')
        
        # Color code the result
        if score != 'N/A' and float(score) >= 4:
            st.error(f"Risk Level: {label}")
        elif score != 'N/A' and float(score) >= 2:
            st.warning(f"Risk Level: {label}")
        else:
            st.success(f"Risk Level: {label}")
            
        st.metric(label="Water Stress Score (0-5)", value=f"{score} / 5")
