import requests
import json

# This is the UUID we found for "Aqueduct Baseline Water Stress"
# We hardcode it so we don't have to search for it every time.
DATASET_ID = "c66d7f3a-d1a8-488f-af8b-302b0f2c3840"

def get_water_risk(lat, lon):
    """
    Fetches the Baseline Water Stress for a specific coordinate.
    """
    print(f"🌍 Checking Water Stress at {lat}, {lon}...")

    # WRI allows SQL-like queries. 
    # ST_Intersects checks if our Point(lon, lat) is inside the dataset's Polygon geometry.
    # We SELECT only the useful columns (score and label) to keep the output clean.
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
                # We found a match!
                result = data[0]
                print(f"✅ Status: {result.get('bws_label', 'Unknown')}")
                print(f"📊 Score:  {result.get('bws_score', 'N/A')} / 5")
            else:
                print("🤷 No data found for this specific location (might be in the ocean or outside coverage).")
                
        else:
            print(f"❌ Error: {response.status_code}")
            print(response.text)

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Test with a location: London, UK (usually Low stress)
    get_water_risk(51.5074, -0.1278)
    
    print("-" * 20)
    
    # Test with a location: Phoenix, Arizona (High stress)
    get_water_risk(33.4484, -112.0740)
