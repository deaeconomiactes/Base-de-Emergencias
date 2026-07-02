import pandas as pd
from pathlib import Path

excel_path = Path(r"d:\OfIcInA\INFORMATICA\Base-de-Emergencia-main\Anibal\DTO 01-2016\DTO 2016-01.xlsx")
xl = pd.ExcelFile(excel_path)

for sheet in xl.sheet_names:
    print(f"\n================ SHEET: {sheet} ================")
    df = xl.parse(sheet)
    print(df.to_string())
