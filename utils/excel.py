import pandas as pd

def generar_excel_coloreado(df, output):
    """
    Genera un Excel con la columna 'EstadoDescarga' coloreada:
    - OK     → azul
    - ERROR  → rojo
    """

    if "EstadoDescarga" not in df.columns:
        raise ValueError("❌ La columna 'EstadoDescarga' no existe en el DataFrame.")

    # Writer seguro para Docker
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="RESULTADOS")

        wb = writer.book
        ws = writer.sheets["RESULTADOS"]

        # Formatos
        azul = wb.add_format({"font_color": "blue"})
        rojo = wb.add_format({"font_color": "red"})
        bold = wb.add_format({"bold": True})

        # Encabezados en negrita
        for idx, col_name in enumerate(df.columns):
            ws.write(0, idx, col_name, bold)

        # Identificar la columna de estado
        col = df.columns.get_loc("EstadoDescarga")

        # Recorrer filas de datos (empezando en 1 por el header)
        for row, estado in enumerate(df["EstadoDescarga"], start=1):
            estado_txt = str(estado).upper().strip()

            if estado_txt == "OK":
                fmt = azul
            else:
                fmt = rojo

            ws.write(row, col, estado_txt, fmt)

        # Auto-ajustar el ancho de columnas
        for idx, col_name in enumerate(df.columns):
            max_len = max(df[col_name].astype(str).str.len().max(), len(col_name)) + 2
            ws.set_column(idx, idx, max_len)
