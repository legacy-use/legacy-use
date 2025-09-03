from computer import chunks


def test_chunks():
    assert chunks('Hello, world!', 5) == ['Hello', ', wor', 'ld!']
    assert chunks('Hello, world!', 10) == ['Hello, wor', 'ld!']
    assert chunks('Hello, world!', 100) == ['Hello, world!']


def test_chunks_newline():
    assert chunks('1\n2', 100) == ['1', '\n', '2']
    assert chunks('1\n2\n3\n4', 100) == ['1', '\n', '2', '\n', '3', '\n', '4']


def test_chunks_newline_and_space():
    assert chunks('12345\n67890', 5) == [
        '12345',
        '\n',
        '67890',
    ]


def test_chunks_newline_and_space_overlap():
    assert chunks('12345\n6789\n0', 3) == [
        '123',
        '45',
        '\n',
        '678',
        '9',
        '\n',
        '0',
    ]
