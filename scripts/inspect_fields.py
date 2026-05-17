import pandas as pd
import os

fields_dir = r'd:\Stock Analysis\D-Energy Berater\d-ess-engine\data\fields'
files = [
    'field_01_roof_potential.parquet',
    'field_02_building_type.parquet',
    'field_03_district_heating.parquet',
    'field_04_pv_adoption.parquet',
]
for fname in files:
    path = os.path.join(fields_dir, fname)
    df = pd.read_parquet(path)
    print(fname + ':')
    print('  rows=' + str(len(df)) + '  cols=' + str(list(df.columns)))
    if 'segment_id' in df.columns:
        segs = sorted(df['segment_id'].unique())
        print('  segments=' + str(segs))
    print()
