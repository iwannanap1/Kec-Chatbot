import json

# Read data from data.json
with open('nepali/nepaliintents.json', 'r', encoding='utf-8') as file:
    data = json.load(file)

# Create a new dictionary for responses
responses = {}

# Process data and populate responses dictionary
for intent in data['intents']:
    tag = intent['tag']
    response = intent['responses'][0]  # Assuming you want only the first response
    # formatted_response = response.encode('unicode_escape').decode('utf-8')
    # responses[tag] = formatted_response
    responses[tag]=response

# Write responses to response.json
with open('nepaliresponse.json', 'w', encoding='utf-8') as file:
    json.dump(responses, file, ensure_ascii=False, indent=4)

