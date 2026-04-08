import pandas as pd
from utils.logger_sse import log   # <-- agregado para reportar errores al frontend

def cargar_excel(path_excel):
    """
    Carga y normaliza el archivo Excel.
    - Lee encabezados de la fila 4 (índice 3).
    - Limpia espacios y normaliza campos clave.
    - Valida columnas obligatorias.
    """

    log("📄 Cargando archivo Excel...")

    try:
        df_raw = pd.read_excel(path_excel, header=None)
    except Exception as e:
        raise ValueError(f"❌ No se pudo leer el archivo Excel: {e}")

    # Validación mínima
    if df_raw.shape[0] < 5:
        raise ValueError("❌ El archivo es demasiado pequeño o no sigue el formato esperado.")

    # La fila 3 contiene los encabezados reales
    new_header = df_raw.iloc[3]

    df = df_raw[4:].copy()
    df.columns = new_header
    df = df.reset_index(drop=True)

    # Normalización segura
    def clean(col):
        return (
            col.astype(str)
               .str.replace(r"\s+", "", regex=True)
               .str.strip()
               .str.upper()
        )

    # Validar columnas necesarias
    required_cols = ["Tipo Inscripcion", "Cred", "Nro Iden"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"❌ Falta la columna obligatoria: {col}")

    # Normalizar columnas clave
    try:
        df["Tipo Inscripcion"] = clean(df["Tipo Inscripcion"])
        df["Cred"]             = clean(df["Cred"])
        df["Nro Iden"]         = clean(df["Nro Iden"])
    except Exception as e:
        raise ValueError(f"❌ Error normalizando columnas: {e}")

    log("📄 Excel cargado y normalizado correctamente.")

    return df


def cargar_y_dividir(path_excel):
    """
    Retorna los DF divididos por tipo de inscripción.
    """
    log("📄 Dividiendo Excel por tipo de inscripción...")

    df = cargar_excel(path_excel)

    df_min = df[df["Tipo Inscripcion"].str.contains("MINORIAS", na=False)].copy()
    df_ind = df[df["Tipo Inscripcion"].str.contains("INDIGENAS", na=False)].copy()

    log(f"📌 Registros MINORÍAS: {len(df_min)}")
    log(f"📌 Registros INDÍGENAS: {len(df_ind)}")

    return df_min, df_ind
