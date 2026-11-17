import pandas as pd

for name in ["races", "results", "constructors", "circuits"]:
    df = pd.read_csv(f"data/{name}.csv", na_values=["\\N"])
    print(name, list(df.columns))