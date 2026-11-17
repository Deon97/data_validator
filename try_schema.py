from core import schema_manager as sm
import pandas as pd

df = pd.DataFrame({"id": ["1", "2"], "name": ["Ann", ""]})
cols = sm.infer_schema(df)
print(cols)
print(sm.save_schema("test_schema", cols))
print(sm.list_schemas())