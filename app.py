import streamlit as st
import requests

# ---------------------------------------------------------
# 1. CONFIGURATION
# ---------------------------------------------------------
BASELINE_ID = "c66d7f3a-d1a8-488f-af8b-302b0f2c3840"
FUTURE_ID = "2a571044-1a31-4092-9af8-48f406f13072"

# ---------------------------------------------------------
# 2. BACKEND LOGIC
# ---------------------------------------------------------
def fetch_baseline_risk(lat, lon):
    """
    Fetches current Baseline Water Stress.
    """
    sql_query = f"SELECT bws_label, bws_score FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    url = f"https://api.resourcewatch.org/v1/query/{BASELINE_ID}"
    
    try:
        response = requests.get(url, params={"sql": sql_query})
        if response.status_code == 200:
            data = response.json().get('data', [])
            return data[0] if data else {"error": "No baseline data found."}
        return {"error": f"API Error: {response.text}"}
    except Exception as e:
        return {"error": str(e)}

def fetch_future_risk(lat, lon):
    """
    Fetches Future Water Stress for 2030 & 2040 (Optimistic vs BAU).
    """
    # FIX: Removed newlines and comments. 
    # We select all 8 columns in a single, flat string.
    sql_query = f"SELECT ws3024tr, ws3024tl, ws3028tr, ws3028tl, ws4024tr, ws4024tl, ws4028tr, ws4028tl FROM data WHERE ST_Intersects(the_geom, ST_GeomFromText('POINT({lon} {lat})', 4326))"
    
    url = f"https://api.resourcewatch.org/v1/query/{FUTURE_ID}"
    
    try:
        response = requests.get(url, params={"sql": sql_query})
        
        if response.status_code == 200:
            data = response.json().get('data', [])
            return data[0] if data else {"error": "No future data found."}
            
        return {"error": f"API Error {response.status_code}: {response.text}"}
        
    except Exception as e:
        return {"error": str(e)}def search_wri_datasets(term):
    url = "https://api.resourcewatch.org/v1/dataset"
    params = {"name": term, "published": "true", "limit": 10, "includes": "metadata"}
    try:
        return requests.get(url, params=params).json().get('data', [])
    except Exception:
        return []

def inspect_columns(dataset_id):
    url = f"https://api.resourcewatch.org/v1/query/{dataset_id}?sql=SELECT * FROM data LIMIT 1"
    try:
        return requests.get(url).json().get('data', [])
    except Exception:
        return None

# ---------------------------------------------------------
# 3. FRONTEND UI
# ---------------------------------------------------------
st.set_page_config(page_title="Water Risk App", page_icon="💧", layout="wide")
st.title("💧 Water Risk Intelligence")

# Inputs
col1, col2 = st.columns(2)
with col1:
    lat_input = st.number_input("Latitude", value=33.4484, format="%.4f")
with col2:
    lon_input = st.number_input("Longitude", value=-112.0740, format="%.4f")

# --- 1. BASELINE ---
st.divider()
st.subheader("1. Current Baseline")
if st.button("Check Current Risk"):
    with st.spinner("Analyzing..."):
        res = fetch_baseline_risk(lat_input, lon_input)
    if "error" in res:
        st.warning(res["error"])
    else:
        score = res.get('bws_score', 'N/A')
        label = res.get('bws_label', 'Unknown')
        
        # Simple color formatting
        s_val = float(score) if score != 'N/A' else 0
        if s_val >= 4:
            st.error(f"Score: {score} ({label})")
        elif s_val >= 3:
            st.warning(f"Score: {score} ({label})")
        else:
            st.success(f"Score: {score} ({label})")

# --- 2. FUTURE PROJECTIONS ---
st.divider()
st.subheader("2. Future Projections (2030 & 2040)")
st.caption("Comparing Optimistic (RCP4.5) vs. Business as Usual (RCP8.5)")

if st.button("Generate Projections"):
    with st.spinner("Projecting Scenarios..."):
        f_res = fetch_future_risk(lat_input, lon_input)
    
    if "error" in f_res:
        st.warning(f_res["error"])
    else:
        # Create a 2x2 grid for the data
        # Row 1: 2030
        st.markdown("### 📅 2030 Projections")
        c1, c2 = st.columns(2)
        
        with c1:
            st.write("🌱 **Optimistic (Scenario 24)**")
            st.metric("Score", f"{f_res.get('ws3024tr')} / 5", delta_color="inverse")
            st.caption(f"Risk: {f_res.get('ws3024tl')}")
            
        with c2:
            st.write("🏭 **Business as Usual (Scenario 28)**")
            st.metric("Score", f"{f_res.get('ws3028tr')} / 5", delta_color="inverse")
            st.caption(f"Risk: {f_res.get('ws3028tl')}")

        st.divider()

        # Row 2: 2040
        st.markdown("### 📅 2040 Projections")
        c3, c4 = st.columns(2)
        
        with c3:
            st.write("🌱 **Optimistic (Scenario 24)**")
            st.metric("Score", f"{f_res.get('ws4024tr')} / 5", delta_color="inverse")
            st.caption(f"Risk: {f_res.get('ws4024tl')}")
            
        with c4:
            st.write("🏭 **Business as Usual (Scenario 28)**")
            st.metric("Score", f"{f_res.get('ws4028tr')} / 5", delta_color="inverse")
            st.caption(f"Risk: {f_res.get('ws4028tl')}")

# ---------------------------------------------------------
# 4. SIDEBAR TOOLS
# ---------------------------------------------------------
st.sidebar.header("🔧 Developer Tools")
search_query = st.sidebar.text_input("Search Datasets", "Water Stress")

if st.sidebar.button("Search API"):
    results = search_wri_datasets(search_query)
    if results:
        st.sidebar.success(f"Found {len(results)} datasets")
        for ds in results:
            with st.sidebar.expander(ds['attributes']['name']):
                st.code(ds['id'])
                st.json(ds)
    else:
        st.sidebar.warning("No datasets found.")

st.sidebar.divider()
st.sidebar.subheader("Inspect Columns")
inspect_id = st.sidebar.text_input("Dataset UUID", value=FUTURE_ID)
if st.sidebar.button("Get Columns"):
    cols = inspect_columns(inspect_id)
    if cols:
        st.sidebar.write(list(cols[0].keys()))
