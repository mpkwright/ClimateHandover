import streamlit as st
import requests

# ---------------------------------------------------------
# DATASET FINDER TOOL
# ---------------------------------------------------------
st.set_page_config(page_title="WRI Dataset Finder", layout="wide")
st.title("🔎 WRI Dataset Finder")

search_term = st.text_input("Search WRI API:", value="Aqueduct")

if st.button("Search Datasets"):
    url = "https://api.resourcewatch.org/v1/dataset"
    params = {
        "name": search_term,
        "published": "true",
        "limit": 100,  # Get a lot of results
        "includes": "metadata"
    }

    with st.spinner(f"Searching for '{search_term}'..."):
        try:
            response = requests.get(url, params=params)
            data = response.json().get('data', [])

            if not data:
                st.error("No datasets found.")
            else:
                st.success(f"Found {len(data)} datasets!")
                
                # Create a table of results
                for ds in data:
                    name = ds['attributes']['name']
                    ds_id = ds['id']
                    provider = ds['attributes']['provider']
                    
                    # Display each dataset in an expandable box
                    with st.expander(f"📂 {name}"):
                        st.write(f"**Provider:** {provider}")
                        st.code(ds_id, language="text") # Easy copy-paste ID
                        
                        # Button to check if this dataset has 'Future' columns
                        if st.button(f"Inspect Columns for {ds_id}", key=ds_id):
                            # Try to fetch one row to see column names
                            query_url = f"https://api.resourcewatch.org/v1/query/{ds_id}?sql=SELECT * FROM data LIMIT 1"
                            try:
                                q_res = requests.get(query_url)
                                if q_res.status_code == 200:
                                    row = q_res.json().get('data', [])[0]
                                    st.write("First row of data (Check keys for 'bau30', 'ws30', etc):")
                                    st.json(row)
                                else:
                                    st.error("Could not fetch data (might need API key or different table name).")
                            except Exception as e:
                                st.error(f"Error inspecting: {e}")

        except Exception as e:
            st.error(f"Connection Error: {e}")
