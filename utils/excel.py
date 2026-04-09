import pandas as pd

def generar_excel_coloreado(df, output):
    """
    Genera un Excel con la columna 'EstadoDescarga' coloreada:
    - OK     → azul
    - ERROR  → rojo
    - NO_APLICA -> gris
    """

    if "EstadoDescarga" not in df.columns:
        raise ValueError("❌ La columna 'EstadoDescarga' no existe en el DataFrame.")

    priority_columns = [
        column for column in ["EstadoDescarga", "DetalleDescarga"] if column in df.columns
    ]
    remaining_columns = [column for column in df.columns if column not in priority_columns]
    df = df[priority_columns + remaining_columns].copy()

    # Writer seguro para Docker
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="RESULTADOS")

        wb = writer.book
        ws = writer.sheets["RESULTADOS"]

        # Formatos
        header_fmt = wb.add_format({
            "bold": True,
            "font_color": "#FFFFFF",
            "bg_color": "#1F4E78",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        })
        azul = wb.add_format({
            "font_color": "#0B5394",
            "bg_color": "#D9EAF7",
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
        })
        rojo = wb.add_format({
            "font_color": "#990000",
            "bg_color": "#F4CCCC",
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
        })
        gris = wb.add_format({
            "font_color": "#666666",
            "bg_color": "#EDEDED",
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
        })
        amarillo = wb.add_format({
            "font_color": "#8A5A00",
            "bg_color": "#FCE8B2",
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "border": 1,
        })
        row_ok_fmt = wb.add_format({
            "valign": "top",
            "border": 1,
            "bg_color": "#EDF7ED",
        })
        row_ok_wrap_fmt = wb.add_format({
            "text_wrap": True,
            "valign": "top",
            "border": 1,
            "bg_color": "#EDF7ED",
        })
        row_ok_center_fmt = wb.add_format({
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "bg_color": "#EDF7ED",
        })
        row_error_fmt = wb.add_format({
            "valign": "top",
            "border": 1,
            "bg_color": "#FDECEC",
        })
        row_error_wrap_fmt = wb.add_format({
            "text_wrap": True,
            "valign": "top",
            "border": 1,
            "bg_color": "#FDECEC",
        })
        row_error_center_fmt = wb.add_format({
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "bg_color": "#FDECEC",
        })
        row_timeout_fmt = wb.add_format({
            "valign": "top",
            "border": 1,
            "bg_color": "#FFF8E1",
        })
        row_timeout_wrap_fmt = wb.add_format({
            "text_wrap": True,
            "valign": "top",
            "border": 1,
            "bg_color": "#FFF8E1",
        })
        row_timeout_center_fmt = wb.add_format({
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "bg_color": "#FFF8E1",
        })
        row_na_fmt = wb.add_format({
            "valign": "top",
            "border": 1,
            "bg_color": "#F2F2F2",
        })
        row_na_wrap_fmt = wb.add_format({
            "text_wrap": True,
            "valign": "top",
            "border": 1,
            "bg_color": "#F2F2F2",
        })
        row_na_center_fmt = wb.add_format({
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "bg_color": "#F2F2F2",
        })
        text_fmt = wb.add_format({
            "valign": "top",
            "border": 1,
        })
        wrap_fmt = wb.add_format({
            "text_wrap": True,
            "valign": "top",
            "border": 1,
        })
        text_fmt_alt = wb.add_format({
            "valign": "top",
            "border": 1,
            "bg_color": "#F8FBFF",
        })
        wrap_fmt_alt = wb.add_format({
            "text_wrap": True,
            "valign": "top",
            "border": 1,
            "bg_color": "#F8FBFF",
        })
        center_fmt = wb.add_format({
            "align": "center",
            "valign": "vcenter",
            "border": 1,
        })
        center_fmt_alt = wb.add_format({
            "align": "center",
            "valign": "vcenter",
            "border": 1,
            "bg_color": "#F8FBFF",
        })

        # Encabezados en negrita
        for idx, col_name in enumerate(df.columns):
            ws.write(0, idx, col_name, header_fmt)

        # Congelar encabezados y activar filtro
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(df), len(df.columns) - 1)
        ws.set_row(0, 24)

        # Identificar la columna de estado
        col = df.columns.get_loc("EstadoDescarga")
        detail_col = df.columns.get_loc("DetalleDescarga") if "DetalleDescarga" in df.columns else None

        # Recorrer filas de datos (empezando en 1 por el header)
        for row, estado in enumerate(df["EstadoDescarga"], start=1):
            estado_txt = str(estado).upper().strip()
            detail_value = df.iloc[row - 1, detail_col] if detail_col is not None else ""
            detail_text = "" if pd.isna(detail_value) else str(detail_value)
            is_timeout = "TIMEOUT" in detail_text.upper()

            if is_timeout:
                fmt = amarillo
                row_base_fmt = row_timeout_fmt
                row_wrap_fmt = row_timeout_wrap_fmt
                row_center_fmt = row_timeout_center_fmt
            elif estado_txt == "OK":
                fmt = azul
                row_base_fmt = row_ok_fmt
                row_wrap_fmt = row_ok_wrap_fmt
                row_center_fmt = row_ok_center_fmt
            elif estado_txt == "NO_APLICA":
                fmt = gris
                row_base_fmt = row_na_fmt
                row_wrap_fmt = row_na_wrap_fmt
                row_center_fmt = row_na_center_fmt
            else:
                fmt = rojo
                row_base_fmt = row_error_fmt
                row_wrap_fmt = row_error_wrap_fmt
                row_center_fmt = row_error_center_fmt

            if estado_txt not in {"OK", "NO_APLICA", "ERROR"}:
                row_base_fmt = text_fmt_alt if row % 2 == 0 else text_fmt
                row_wrap_fmt = wrap_fmt_alt if row % 2 == 0 else wrap_fmt
                row_center_fmt = center_fmt_alt if row % 2 == 0 else center_fmt

            ws.write(row, col, estado_txt, fmt)

            if detail_col is not None:
                ws.write(row, detail_col, detail_text, row_wrap_fmt)

            ws.set_row(row, 22)

            for idx, col_name in enumerate(df.columns):
                if idx in {col, detail_col}:
                    continue

                cell_value = df.iloc[row - 1, idx]
                fmt_to_use = row_center_fmt if col_name in {"Cred", "Nro Iden", "Opcion", "Tipo Iden"} else row_base_fmt
                ws.write(row, idx, "" if pd.isna(cell_value) else cell_value, fmt_to_use)

        # Auto-ajustar el ancho de columnas
        for idx, col_name in enumerate(df.columns):
            if col_name == "EstadoDescarga":
                ws.set_column(idx, idx, 18)
                continue
            if col_name == "DetalleDescarga":
                ws.set_column(idx, idx, 48)
                continue
            if col_name in {"Cred", "Nro Iden"}:
                ws.set_column(idx, idx, 16)
                continue
            if col_name in {"Opcion", "Tipo Iden", "Ti Cod", "Cod Cra"}:
                ws.set_column(idx, idx, 12)
                continue

            max_len = max(df[col_name].astype(str).str.len().max(), len(col_name)) + 2
            ws.set_column(idx, idx, min(max_len, 28))
