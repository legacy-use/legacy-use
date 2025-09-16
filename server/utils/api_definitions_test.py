from server.utils.api_definitions import infer_schema_from_response_example


def test_infer_schema_types():
    example = {
        'id': 123,
        'name': 'Alice',
        'active': True,
        'float': 1.23,
        'items': [],
        'dict': {},
    }
    schema = infer_schema_from_response_example(example)
    assert schema.get('type') == 'object'
    assert schema.get('properties', {}).get('id').get('type') == 'integer'
    assert schema.get('properties', {}).get('name').get('type') == 'string'
    assert schema.get('properties', {}).get('active').get('type') == 'boolean'
    assert schema.get('properties', {}).get('items').get('type') == 'array'
    assert schema.get('properties', {}).get('dict').get('type') == 'object'


def test_infer_schema_nested_objects():
    example = {
        'shallow_value': 123,
        'nested_value': {
            'id': 123,
            'name': 'Alice',
            'active': True,
            'float': 1.23,
            'items': [],
            'dict': {},
        },
    }
    schema = infer_schema_from_response_example(example)
    assert schema.get('type') == 'object'
    assert schema.get('properties', {}).get('shallow_value').get('type') == 'integer'
    assert schema.get('properties', {}).get('nested_value').get('type') == 'object'
    assert (
        schema.get('properties', {})
        .get('nested_value')
        .get('properties', {})
        .get('id')
        .get('type')
        == 'integer'
    )
    assert (
        schema.get('properties', {})
        .get('nested_value')
        .get('properties', {})
        .get('name')
        .get('type')
        == 'string'
    )
    assert (
        schema.get('properties', {})
        .get('nested_value')
        .get('properties', {})
        .get('active')
        .get('type')
        == 'boolean'
    )
    assert (
        schema.get('properties', {})
        .get('nested_value')
        .get('properties', {})
        .get('items')
        .get('type')
        == 'array'
    )
    assert (
        schema.get('properties', {})
        .get('nested_value')
        .get('properties', {})
        .get('dict')
        .get('type')
        == 'object'
    )


def test_infer_schema_from_response_example_duplicate_array_items():
    """Test schema inference for arrays with duplicate item types."""
    example = {
        'homogeneous_array': [1, 2, 3],
        'heterogeneous_array': [1, 'string', True],
        'duplicate_types_array': [1, 2, 'string', 'another_string', 3],
    }
    schema = infer_schema_from_response_example(example)

    # Homogeneous array should have single item type
    homogeneous_items = (
        schema.get('properties', {}).get('homogeneous_array', {}).get('items', {})
    )
    assert homogeneous_items.get('type') == 'integer'

    # Heterogeneous array should use anyOf
    heterogeneous_items = (
        schema.get('properties', {}).get('heterogeneous_array', {}).get('items', {})
    )
    assert 'anyOf' in heterogeneous_items
    any_of_types = [item.get('type') for item in heterogeneous_items.get('anyOf', [])]
    assert 'integer' in any_of_types
    assert 'string' in any_of_types
    assert 'boolean' in any_of_types

    # Array with duplicate types should deduplicate in anyOf
    duplicate_items = (
        schema.get('properties', {}).get('duplicate_types_array', {}).get('items', {})
    )
    assert 'anyOf' in duplicate_items
    any_of_schemas = duplicate_items.get('anyOf', [])
    # Should only have 2 unique schemas: integer and string
    assert len(any_of_schemas) == 2
    any_of_types = [item.get('type') for item in any_of_schemas]
    assert 'integer' in any_of_types
    assert 'string' in any_of_types


def test_infer_schema_from_response_example_nested_objects_in_arrays():
    # Test nested objects in arrays
    nested_example = {
        'array_with_nested_objects': [
            {'id': 1, 'name': 'first'},
            {'id': 2, 'number': 0},
            'string_item',
        ]
    }
    nested_schema = infer_schema_from_response_example(nested_example)

    nested_array_items = (
        nested_schema.get('properties', {})
        .get('array_with_nested_objects', {})
        .get('items', {})
    )
    assert 'anyOf' in nested_array_items
    any_of_schemas = nested_array_items.get('anyOf', [])
    assert len(any_of_schemas) == 3

    # Should have object type and string type
    types = [item.get('type') for item in any_of_schemas]
    assert 'object' in types
    assert 'string' in types

    # Should have two different object schemas
    object_schemas = [item for item in any_of_schemas if item.get('type') == 'object']
    assert len(object_schemas) == 2

    # Check each object schema individually
    obj1_properties = object_schemas[0].get('properties', {})
    obj2_properties = object_schemas[1].get('properties', {})

    # First object should have 'id' and 'name'
    assert obj1_properties.get('id', {}).get('type') == 'integer'
    assert obj1_properties.get('name', {}).get('type') == 'string'

    # Second object should have 'id' and 'number'
    assert obj2_properties.get('id', {}).get('type') == 'integer'
    assert obj2_properties.get('number', {}).get('type') == 'integer'
