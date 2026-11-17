import pandas as pd
from core.validator import validate

schema = {"columns": [
    {"name": "id", "type": "integer", "required": True, "unique": True},
    {"name": "status", "type": "string", "allowed_values": ["a", "b"]},
]}
df = pd.DataFrame({"id": ["1", "x", "1", ""], "status": ["a", "c", "b", "a"]})
structure, errs, invalid = validate(df, schema)
print(errs)
print(invalid)