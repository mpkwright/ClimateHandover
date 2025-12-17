import requests

def debug_search():
    """
    Broad search for ANY dataset containing 'Water Stress' in the name.
    """
    url = "https://api.resourcewatch.org/v1/dataset"
    
    # Search for "Water Stress" instead of "Aqueduct"
    params = {
        "name": "Water Stress", 
        "published": "true",
        "limit": 20, 
        "includes": "metadata"
    }

    print("🔍 Searching for 'Water Stress' datasets...")
    
    try:
        response = requests.get(url, params=params)
        data = response.json().get('data', [])
        
        if not data:
            print("❌ No datasets found.")
            return

        for ds in data:
            name = ds['attributes']['name']
            ds_id = ds['id']
            # Print cleanly so you can copy the ID
            print(f"📂 {name}")
            print(f"🆔 {ds_id}")
            print("-" * 30)

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_search()
