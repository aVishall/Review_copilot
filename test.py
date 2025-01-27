import requests
import json

# API and Headers Configuration
base_url = "https://nkb-backend-ccbp-prod-apis.ccbp.in/api/nkb_learning_resource/tutorial/details/v1/"
headers = {
    "accept": "application/json",
    "accept-language": "en-US,en;q=0.9",
    "authorization": "Bearer yRueUN4m1PjztoxXt7OCo9MR4jRlLQ",
    "content-type": "application/json",
    "origin": "https://learning.ccbp.in",
    "priority": "u=1, i",
    "referer": "https://learning.ccbp.in/",
    "sec-ch-ua": '"Not)A;Brand";v="99", "Google Chrome";v="127", "Chromium";v="127"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "x-app-version": "863",
    "x-browser-session-id": "9fce9e19-5785-4ccc-89e0-46d1fdf30339"
}


# Tutorial Entity ID
tutorial_entity_id = "a7bf5502-d2fe-4485-974d-ac8f9e0a0b99"

# Function to Fetch Tutorial Details
def fetch_tutorial_details(entity_id):
    data = {
        "data": json.dumps({"tutorial_entity_id": entity_id}),
        "clientKeyDetailsId": 1
    }
    response = requests.post(base_url, headers=headers, json=data)
    if response.status_code == 200:
        print(response.json())
        return response.json()  # Return parsed JSON
    else:
        print(f"Error fetching tutorial details: {response.status_code}")
        return None

# Function to Save or Process Tutorial Step Content
def save_tutorial_step_content(step_id, content):
    # Placeholder logic: Print content (replace with actual saving logic)
    print(f"Saving content for Step ID {step_id}:\n{content}\n")

# Main Script
tutorial_data = fetch_tutorial_details(tutorial_entity_id)

if tutorial_data:
    # Assuming the response contains a dictionary with step details
    tutorial_steps = tutorial_data.get("steps", [])  # Update key based on actual response structure

    for step in tutorial_steps:
        step_id = step.get("id")  # Update key if 'id' differs
        content = step.get("content")  # Update key if 'content' differs
        if step_id and content:
            save_tutorial_step_content(step_id, content)
        else:
            print(f"Missing data for step: {step}")
else:
    print("Failed to retrieve tutorial details.")
