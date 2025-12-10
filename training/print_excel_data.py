"""
Read Excel file and print data in copy-pasteable format.

Run this on your Windows machine:
    python print_excel_data.py "C:\\Users\\dkell\\OneDrive\\Desktop\\SaaSIdeas\\catalog of saas ideas.xlsx"

Then copy the output and paste into chat.

Requirements:
    pip install pandas openpyxl
"""

import sys
import pandas as pd
from pathlib import Path


def print_excel_data(excel_path: str):
    """Read Excel and print in simple format."""

    print(f"Reading: {excel_path}\n")

    # Read Excel
    df = pd.read_excel(excel_path)

    print(f"Found {len(df)} rows\n")
    print("="*80)
    print("COPY EVERYTHING BELOW THIS LINE")
    print("="*80)
    print()

    # Print as simple delimiter-separated format
    for idx, row in df.iterrows():
        parts = []
        for col in df.columns:
            val = str(row[col]) if pd.notna(row[col]) else ""
            parts.append(val)
        print(" ||| ".join(parts))

    print()
    print("="*80)
    print("COPY EVERYTHING ABOVE THIS LINE")
    print("="*80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python print_excel_data.py "path/to/excel.xlsx"')
        sys.exit(1)

    excel_path = sys.argv[1]

    if not Path(excel_path).exists():
        print(f"File not found: {excel_path}")
        sys.exit(1)

    try:
        print_excel_data(excel_path)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
