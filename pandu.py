import pandas as pd 
# print(pd.read_csv('indeed_jobs_extended.csv').iloc[0])
# print(pd.read_csv('indeed_jobs_extended.csv').columns)
# print(pd.read_csv('indeed_jobs_extended.csv').shape)
df= pd.read_csv('indeed_jobs_extended.csv')
print(df.info())
print(f"nan counts:\n{df.isna().sum()}")