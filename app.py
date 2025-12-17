import requests
import json

def search_future_datasets():
    """
    Searches for Aqueduct Future projections.
    """
    url = "https://api.resourcewatch.org/v1/dataset"
    
    # We search for "Aqueduct 4.0" to get the latest version
    # "Future" ensures we get projections, not baseline
    params = {
        "name": "Aqueduct 4.0 Future", 
        "published": "true",
        "limit": 5,
        "includes": "metadata"
    }

    print("🔍 Searching for Future Water Stress Datasets...")
    
    try:
        response = requests.get(url, params=params)
        data = response.json().get('data', [])
        
        if not data:
            print("❌ No datasets found.")
            return

        for ds in data:
            name = ds['attributes']['name']
            ds_id = ds['id']
            provider = ds['attributes']['provider']
            print(f"\n📂 Name: {name}")
            print(f"🆔 UUID: {ds_id}")
            print(f"🏭 Provider: {provider}")
            print("-" * 40)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    search_future_datasets()

# Add this to the bottom of wri_api.py
if __name__ == "__main__":
    print("🔍 Debug Mode: Searching for datasets...")
    results = search_future_datasets()
    
    if results:
        for ds in results:
            print(f"\n📂 Name: {ds['attributes']['name']}")
            print(f"🆔 UUID: {ds['id']}")
            print(f"🏭 Provider: {ds['attributes']['provider']}")
            print("-" * 30)
    else:
        print("❌ No datasets found or an error occurred.")
