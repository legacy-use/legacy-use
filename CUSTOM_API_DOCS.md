# Custom API Documentation

This feature repurposes the existing Redoc documentation to render internal API models (stored in the database) as beautiful endpoint definitions, allowing customers to view custom API definitions in a more beautiful format.

## Overview

The custom API documentation system converts database-stored API definitions into OpenAPI 3.0 schema format and renders them using Redoc for a beautiful, interactive documentation experience. This allows customers to easily explore and understand the custom APIs available in the system.

## Features

- **Automatic OpenAPI Schema Generation**: Converts database API definitions to proper OpenAPI 3.0 format
- **Beautiful Redoc Interface**: Uses the same Redoc styling as the main API documentation
- **Parameter Type Conversion**: Automatically converts custom parameter types to proper OpenAPI types
- **Response Schema Inference**: Generates response schemas from example data
- **Archive Support**: Option to include or exclude archived API definitions
- **Real-time Updates**: Documentation reflects current database state

## Endpoints

### Main Documentation
- **URL**: `/custom-api-docs`
- **Method**: GET
- **Description**: Serves the main custom API documentation using Redoc
- **Parameters**:
  - `include_archived` (optional, boolean): Include archived API definitions (default: false)

### OpenAPI Schema
- **URL**: `/custom-openapi.json`
- **Method**: GET
- **Description**: Returns the raw OpenAPI 3.0 schema for custom API definitions
- **Parameters**:
  - `include_archived` (optional, boolean): Include archived API definitions (default: false)

### API Summary
- **URL**: `/api-definitions-summary`
- **Method**: GET
- **Description**: Returns a summary of available API definitions with metadata
- **Parameters**:
  - `include_archived` (optional, boolean): Include archived API definitions (default: false)

## Usage

### Accessing the Documentation

1. **Start your server** with `SHOW_DOCS=true` in your environment
2. **Visit the custom documentation**:
   ```
   http://localhost:8088/custom-api-docs
   ```
3. **Include archived APIs** (optional):
   ```
   http://localhost:8088/custom-api-docs?include_archived=true
   ```

### API Summary Endpoint

Get a quick overview of all available custom APIs:

```bash
curl http://localhost:8088/api-definitions-summary
```

Response example:
```json
{
  "total_count": 5,
  "active_count": 4,
  "archived_count": 1,
  "api_definitions": [
    {
      "name": "get_weather",
      "description": "Get current weather information for a location",
      "is_archived": false,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z",
      "version": "1.0.0",
      "parameter_count": 2,
      "has_response_example": true
    }
  ]
}
```

## How It Works

### 1. Database Integration

The system reads API definitions from the database tables:
- `api_definitions`: Contains basic API information (name, description, etc.)
- `api_definition_versions`: Contains parameters, prompts, and response examples

### 2. OpenAPI Schema Generation

The `CustomOpenAPIGenerator` class converts database models to OpenAPI format:

```python
# Example parameter conversion
{
  "name": "location",
  "type": "string", 
  "description": "The location to get weather for"
}

# Becomes OpenAPI schema:
{
  "location": {
    "type": "string",
    "description": "The location to get weather for"
  }
}
```

### 3. Type Conversion

Supports automatic conversion of various parameter types:
- `string`, `str` → `string`
- `integer`, `int` → `integer`
- `boolean`, `bool` → `boolean`
- `array`, `list` → `array`
- `date` → `string` with `date` format
- `email` → `string` with `email` format
- `uuid` → `string` with `uuid` format

### 4. Response Schema Inference

Automatically generates response schemas from example data:

```python
# Example response data:
{
  "temperature": 22.5,
  "humidity": 65,
  "conditions": "partly cloudy"
}

# Generated schema:
{
  "type": "object",
  "properties": {
    "temperature": {"type": "number"},
    "humidity": {"type": "integer"},
    "conditions": {"type": "string"}
  }
}
```

## Implementation Details

### File Structure

```
server/
├── utils/
│   └── openapi_generator.py    # OpenAPI schema generation
├── routes/
│   └── custom_docs.py          # Documentation endpoints
└── server.py                   # Router integration
```

### Key Components

1. **CustomOpenAPIGenerator** (`server/utils/openapi_generator.py`)
   - Generates OpenAPI 3.0 schemas from database API definitions
   - Handles type conversion and schema inference
   - Supports archived API filtering

2. **Documentation Routes** (`server/routes/custom_docs.py`)
   - `/custom-api-docs`: Serves Redoc HTML interface
   - `/custom-openapi.json`: Provides OpenAPI schema
   - `/api-definitions-summary`: Returns API metadata

3. **Server Integration** (`server/server.py`)
   - Includes documentation routes
   - Adds endpoints to authentication whitelist when `SHOW_DOCS=true`

### Security

- Documentation endpoints are protected by the same authentication system as other API endpoints
- When `SHOW_DOCS=true`, the custom documentation endpoints are added to the authentication whitelist
- No sensitive information (like prompts or internal details) is exposed in the documentation

## Customization

### Styling

The Redoc interface uses the default Redoc styling with custom fonts:
- Primary font: Montserrat
- Secondary font: Roboto

### Adding Custom Themes

You can customize the Redoc theme by modifying the HTML template in `custom_api_docs()`:

```python
# In server/routes/custom_docs.py
html_content = f"""
<script>
Redoc.init(schema, {{
    theme: {{
        colors: {{
            primary: {{
                main: '#your-color-here'
            }}
        }}
    }}
}}, document.getElementById('redoc-container'));
</script>
"""
```

## Troubleshooting

### Common Issues

1. **No APIs showing in documentation**
   - Ensure you have API definitions in the database
   - Check that APIs are not archived (unless `include_archived=true`)
   - Verify API definitions have active versions

2. **Schema generation errors**
   - Check that API definition parameters are properly formatted
   - Ensure response examples are valid JSON

3. **Documentation not accessible**
   - Verify `SHOW_DOCS=true` in your environment
   - Check that the server is running and accessible
   - Ensure authentication is properly configured

### Debug Information

Enable debug logging to see schema generation details:

```python
import logging
logging.getLogger('server.utils.openapi_generator').setLevel(logging.DEBUG)
```

## Benefits

1. **Better Customer Experience**: Beautiful, interactive documentation instead of raw API definitions
2. **Automatic Updates**: Documentation stays in sync with database changes
3. **Professional Appearance**: Uses the same high-quality Redoc interface as the main API docs
4. **Easy Integration**: Seamlessly integrates with existing authentication and server infrastructure
5. **Flexible Access**: Support for including/excluding archived APIs as needed

## Future Enhancements

Potential improvements for future versions:
- Custom Redoc themes per customer
- API definition versioning in documentation
- Interactive API testing interface
- Export functionality for API definitions
- Custom grouping and categorization of APIs