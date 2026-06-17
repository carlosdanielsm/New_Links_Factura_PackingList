import io

import pandas as pd


def generar_excel_bytes(df: pd.DataFrame) -> bytes:
    """Genera un Excel en memoria con formato básico."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Resultados")
        workbook = writer.book
        worksheet = writer.sheets["Resultados"]

        header_format = workbook.add_format({
            "bold": True,
            "text_wrap": True,
            "valign": "top",
            "fg_color": "#D9EAF7",
            "border": 1,
        })
        money_format = workbook.add_format({"num_format": "$#,##0.00"})
        percent_format = workbook.add_format({"num_format": "0.00"})
        text_wrap = workbook.add_format({"text_wrap": True, "valign": "top"})

        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            width = min(max(len(str(value)) + 2, 14), 38)
            worksheet.set_column(col_num, col_num, width, text_wrap)

        for col_name in ["PRICE", "PRECIO_ENCONTRADO"]:
            if col_name in df.columns:
                idx = df.columns.get_loc(col_name)
                worksheet.set_column(idx, idx, 14, money_format)

        if "DIFERENCIA_PRECIO" in df.columns:
            idx = df.columns.get_loc("DIFERENCIA_PRECIO")
            worksheet.set_column(idx, idx, 16, percent_format)

        worksheet.freeze_panes(1, 0)
        worksheet.autofilter(0, 0, len(df), len(df.columns) - 1)

    output.seek(0)
    return output.read()
