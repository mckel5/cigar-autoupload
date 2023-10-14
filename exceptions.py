class HttpRequestException(Exception):
    """An HTTP request returned a non-OK status code."""
    pass


class MalformedDataException(Exception):
    """Some data isn't formatted properly for uploading to WordPress."""
    pass
