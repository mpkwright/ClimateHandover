import streamlit as st
import requests

# ---------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------
# Baseline Water Stress (Current)
BASELINE_ID = "c66d7f3a-d1a8-488f-af8b-302b0f2c3840"

# Projected Water Stress (Future) - The UUID you found!
FUTURE_ID = "2a571044-1a31-4092-9af8-48f406f13072"

# ---------------------------------------------------------
# 2. BACKEND FUNCTIONS
# ---------------------------------------------------------
def fetch_baseline_risk(lat, lon):
    """
    Fetches current Baseline Water Stress.
    """
    # Clean SQL on one line
    sql_query = f"SELECT bws_label, bws_score FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    
    url = f"https://api.resourcewatch.org/v1/query/{BASELINE_ID}"
    params = {"sql": sql_query}

    try:
        response = requests.get(url, params=params)
        if response.status_code != 200:
            return {"error": f"API Error {response.status_code}: {response.text}"}

        data = response.json().get('data', [])
        return data[0] if data else {"error": "No baseline data at this location."}
            
    except Exception as e:
        return {"error": str(e)}

def fetch_future_risk(lat, lon):
    """
    Fetches Future Water Stress (2030 Business As Usual).
    Columns: bau30_ws_x_r (Raw Score), bau30_ws_x_l (Label)
    """
    sql_query = f"SELECT bau30_ws_x_r as score, bau30_ws_x_l as label FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    
    url = f"https://api.resourcewatch.org/v1/query/{FUTURE_ID}"
    params = {"sql": sql_query}

    try:
        response = requests.get(url, params=params)
        if response.status_code != 200:
            return {"error": f"API Error {response.status_code}: {response.text}"}

        data = response.json().get('data', [])
        return data[0] if data else {"error": "No future data found for this location."}
            
    except Exception as e:
        return {"error": str(e)}

def search_datasets(term):
    """
    Helper to search for other datasets in the sidebar.
    """
    url = "https://api.resourcewatch.org/v1/dataset"
    params = {"name": term, "published": "true", "limit": 20, "includes": "metadata"}
    try:
        return requests.get(url, params=params).json().get('data', [])
    except:
        return []

# ---------------------------------------------------------
# 3. FRONTEND UI
# ---------------------------------------------------------
st.set_page_config(page_title="Water Risk App", page_icon="💧", layout="wide")

st.title("💧 Water Risk Intelligence")
st.markdown("Analyze current and future water stress for any location on Earth.")

# Input Section
with st.container():
    col1, col2 = st.columns(2)
    with col1:
        lat_input = st.number_input("Latitude", value=33.4484, format="%.4f")
    with col2:
        lon_input = st.number_input("Longitude", value=-112.0740, format="%.4f")

# ---------------------------------------------------------
# SECTION A: BASELINE RISK
# ---------------------------------------------------------
st.divider()
st.subheader("1. Current Baseline Risk")

if st.button("Check Current Risk"):
    with st.spinner("Querying Baseline Database..."):
        result = fetch_baseline_risk(lat_input, lon_input)
    
    if "error" in result:
        st.warning(result["error"])
    else:
        label = result.get('bws_label', 'Unknown')
        score = result.get('bws_score', 'N/A')
        
        # Color Logic
        if score != 'N/A':
            score_val = float(score)
            if score_val >= 4:
                st.error(f"🔥 EXTREME RISK ({label})")
            elif score_val >= 3:
                st.warning(f"⚠️ HIGH RISK ({label})")
            else:
                st.success(f"✅ LOW/MEDIUM RISK ({label})")
        
        st.metric("Current Water Stress Score", f"{score} / 5")

# ---------------------------------------------------------
# SECTION B: FUTURE RISK (2030)
# ---------------------------------------------------------
st.divider()
st.subheader("2. Future Projections (2030)")
st.info("Scenario: Business As Usual (BAU)")

if st.button("🔮 Predict 2030 Risk"):
    with st.spinner("Projecting 2030 Risk..."):
        future_result = fetch_future_risk(lat_input, lon_input)
        
    if "error" in future_result:
        st.warning(future_result["error"])
    else:
        f_score = future_result.get('score', 'N/A')
        f_label = future_result.get('label', 'Unknown')
        
        # Display nicely
        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("2030 Projected Score", f"{f_score} / 5")
        with col_b:
            st.write(f"**Projected Category:**")
            st.info(f_label)

# ---------------------------------------------------------
# SIDEBAR TOOLS
# ---------------------------------------------------------
st.sidebar.header("🔧 Developer Tools")
search_query = st.sidebar.text_input("Search Dataset Name", "wat.006")
if st.sidebar.button("Search"):
    results = search_datasets(search_query)
    for ds in results:
        with st.sidebar.expander(ds['attributes']['name']):
            st.code(ds['id'])
            st.json(ds)

# ---------------------------------------------------------
# PASTE THIS INTO YOUR SIDEBAR SECTION IN app.py
# ---------------------------------------------------------
st.sidebar.divider()
st.sidebar.subheader("🕵️ Column Inspector")

# Paste your Future UUID here to check it
inspect_id = st.sidebar.text_input("Dataset UUID to Inspect", value="2a571044-1a31-4092-9af8-48f406f13072")

if st.sidebar.button("Show Columns"):
    # Query just 1 row to see the table structure
    inspect_url = f"https://api.resourcewatch.org/v1/query/{inspect_id}?sql=SELECT * FROM data LIMIT 1"
    
    try:
        r = requests.get(inspect_url)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data:
                # Get the first row keys (column names)
                columns = list(data[0].keys())
                st.sidebar.success(f"Found {len(columns)} columns!")
                st.sidebar.write(columns) # Prints list of all column names
                
                # Check for common Future keywords
                future_cols = [c for c in columns if "30" in c or "40" in c or "20" in c]
                if future_cols:
                    st.sidebar.info("Possible Future Columns:")
                    st.sidebar.json(future_cols)
            else:
                st.sidebar.warning("Dataset is empty or permissions block access.")
        else:
            st.sidebar.error(f"Error {r.status_code}: {r.text}")
    except Exception as e:
        st.sidebar.error(f"Failed: {e}")
