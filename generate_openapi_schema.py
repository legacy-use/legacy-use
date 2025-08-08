import json
import os

# Override the API_SLUG_PREFIX to be empty instead of the default '/api'
os.environ['API_SLUG_PREFIX'] = ''

from server.server import app

if __name__ == '__main__':
    schema = app.openapi()
    with open('openapi.json', 'w') as f:
        json.dump(schema, f)
