import requests
import json

def get_aqueduct_data():
    # 1. Search for the specific Aqueduct dataset
    search_url = "https://api.resourcewatch.org/v1/dataset"
    search_params = {
        "name": "Aqueduct Baseline Water Stress",
        "published": "true",
        "limit": 1,  # We only want the top match
        "includes": "metadata"
    }

    print("🔍 Searching for 'Aqueduct Baseline Water Stress'...")
    
    try:
        # SEARCH REQUEST
        response = requests.get(search_url, params=search_params)
        response.raise_for_status() # Raises error if 400/500
        
        datasets = response.json().get('data', [])
        if not datasets:
            print("❌ No dataset found. The API might use a different name.")
            return

        # Get the ID of the first result
        target_id = datasets[0]['id']
        target_name = datasets[0]['attributes']['name']
        print(f"✅ Found Dataset: {target_name}")
        print(f"🆔 UUID: {target_id}")

        # 2. Try to fetch actual data (The "API Key" Test)
        # We ask for just 1 row to test access
        print("\n🧪 Testing data access (Querying 1 row)...")
        query_url = f"https://api.resourcewatch.org/v1/query/{target_id}"
        query_params = {
            "sql": "SELECT * FROM data LIMIT 1"  # SQL-like query supported by WRI
        }

        data_response = requests.get(query_url, params=query_params)
        
        if data_response.status_code == 200:
            print("🎉 SUCCESS! Data retrieved without an API key.")
            print("-" * 30)
            print(json.dumps(data_response.json(), indent=2))
        elif data_response.status_code in [401, 403]:
            print("🔒 ACCESS DENIED. You were right - an API Key is required for data.")
        else:
            print(f"⚠️ Unexpected Status: {data_response.status_code}")
            print(data_response.text)

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    get_aqueduct_data()
