"""
=============================================================================
Exploratory Data Analysis (EDA) Script
=============================================================================
Inspects summary statistics and shapes of all tables in the dataset.
Run:
  python eda.py
"""

import pandas as pd
import glob
import os

print("=" * 60)
print("DATASET OVERVIEW & SUMMARY STATISTICS")
print("=" * 60)

csv_files = sorted(glob.glob("*.csv"))

for filepath in csv_files:
    filename = os.path.basename(filepath)
    try:
        df = pd.read_csv(filepath, nrows=5, low_memory=False)
        # Count total rows
        total_rows = sum(1 for _ in open(filepath, encoding="utf-8", errors="ignore")) - 1
        print(f"\n[FILE] {filename}")
        print(f"  • Total Rows: {total_rows:,}")
        print(f"  • Columns ({len(df.columns)}): {list(df.columns)}")
        print(f"  • First 2 sample records:")
        for idx, row in df.head(2).iterrows():
            print(f"    - Row {idx + 1}: {dict(list(row.items())[:4])}")
    except Exception as e:
        print(f"Error reading {filename}: {e}")

print("\n" + "=" * 60)
