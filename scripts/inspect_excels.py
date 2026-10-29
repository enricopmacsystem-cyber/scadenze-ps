from pathlib import Path
from openpyxl import load_workbook

files = [
    Path(r"\\172.17.17.11\supporto-tecnico\Vari Excel\primo soccorso\monitoraggio_scadenze_cassette.xlsx"),
    Path(r"\\172.17.17.11\supporto-tecnico\Vari Excel\primo soccorso\CASSETTA MAGAZZINO.xlsx"),
    Path(r"\\172.17.17.11\supporto-tecnico\Vari Excel\primo soccorso\CASSETTA SHOWROOM.xlsx"),
    Path(r"\\172.17.17.11\supporto-tecnico\Vari Excel\primo soccorso\old\CASSETTE PRONTO SOCCORSO GRUARO.xlsx"),
]

for path in files:
    print("\n" + "=" * 80)
    print("FILE:", path)
    print("exists:", path.exists())
    if not path.exists():
        continue
    wb = load_workbook(path, data_only=True)
    print("sheets:", wb.sheetnames)
    for name in wb.sheetnames:
        ws = wb[name]
        print(f"\n--- sheet {name!r} max_row={ws.max_row} max_col={ws.max_column} ---")
        for r in range(1, min(ws.max_row + 1, 35)):
            vals = [ws.cell(r, c).value for c in range(1, min(ws.max_column + 1, 14))]
            if any(v is not None and str(v).strip() != "" for v in vals):
                print(r, vals)
