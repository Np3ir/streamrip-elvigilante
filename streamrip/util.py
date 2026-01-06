def typed(val, _type):
    if isinstance(val, _type):
        return val
    raise TypeError(f"Expected type {_type}, got {type(val)}")