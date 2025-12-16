import pandas as pd
df = pd.read_csv("/Users/y_anaray/Downloads/Day_Dream_CAPSTONE/Investment product masterfile/Investment products_Masterfile_v69.csv")
print([c for c in df.columns if "id" in c.lower()])