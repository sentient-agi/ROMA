"""
Convert Excel file of SaaS ideas to training scenarios YAML format.

Run this script on your Windows machine:
    python convert_excel_to_scenarios.py "C:\\Users\\dkell\\OneDrive\\Desktop\\SaaSIdeas\\catalog of saas ideas.xlsx"

Requirements:
    pip install pandas openpyxl pyyaml
"""

import sys
import pandas as pd
import yaml
from pathlib import Path


def convert_excel_to_scenarios(excel_path: str, output_path: str = None):
    """Convert Excel file to training scenarios YAML."""

    # Read Excel file
    print(f"Reading Excel file: {excel_path}")
    df = pd.read_excel(excel_path)

    print(f"Found {len(df)} rows")
    print(f"Columns: {df.columns.tolist()}")

    # Auto-detect column names (flexible)
    name_col = None
    desc_col = None
    category_col = None

    for col in df.columns:
        col_lower = str(col).lower()
        if 'name' in col_lower or 'title' in col_lower or 'idea' in col_lower:
            name_col = col
        elif 'desc' in col_lower or 'detail' in col_lower or 'summary' in col_lower:
            desc_col = col
        elif 'category' in col_lower or 'type' in col_lower:
            category_col = col

    # Fallback: use first columns
    if name_col is None:
        name_col = df.columns[0]
    if desc_col is None and len(df.columns) > 1:
        desc_col = df.columns[1]

    print(f"\nUsing columns:")
    print(f"  Name: {name_col}")
    print(f"  Description: {desc_col}")
    print(f"  Category: {category_col}")

    # Convert to scenarios
    scenarios = []

    for idx, row in df.iterrows():
        name = str(row[name_col]).strip() if pd.notna(row[name_col]) else f"SaaS Idea {idx+1}"

        # Get description
        if desc_col and pd.notna(row[desc_col]):
            description = str(row[desc_col]).strip()
        else:
            description = f"Build {name}"

        # Get category
        if category_col and pd.notna(row[category_col]):
            category = str(row[category_col]).lower().replace(' ', '_')
        else:
            category = "micro_saas"

        # Create scenario
        scenario = {
            "name": name,
            "goal": f"Build a complete {name}: {description}",
            "requirements": [
                "FastAPI or Flask backend",
                "RESTful API endpoints",
                "Error handling and validation",
                "Basic authentication (API keys)",
                "Database integration if needed",
            ],
            "task_type": "CODE_INTERPRET",
            "category": category,
        }

        scenarios.append(scenario)

    # Create output structure
    output = {
        "scenarios": scenarios
    }

    # Determine output path
    if output_path is None:
        excel_file = Path(excel_path)
        output_path = excel_file.parent / "training_scenarios.yaml"

    # Write YAML file
    print(f"\nWriting {len(scenarios)} scenarios to: {output_path}")

    with open(output_path, 'w') as f:
        yaml.dump(output, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    print(f"✅ Done! Created {output_path}")
    print(f"\nNext step:")
    print(f"  Copy this file to: /home/user/ROMA/training/my_scenarios.yaml")
    print(f"  Then run: python training/ace_training.py --scenarios training/my_scenarios.yaml")

    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_excel_to_scenarios.py <excel_file>")
        print("\nExample:")
        print('  python convert_excel_to_scenarios.py "C:\\Users\\dkell\\OneDrive\\Desktop\\SaaSIdeas\\catalog of saas ideas.xlsx"')
        sys.exit(1)

    excel_path = sys.argv[1]

    if not Path(excel_path).exists():
        print(f"❌ Error: File not found: {excel_path}")
        sys.exit(1)

    try:
        convert_excel_to_scenarios(excel_path)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
