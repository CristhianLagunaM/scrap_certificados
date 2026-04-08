import pandas as pd
import unicodedata
from utils.logger_sse import log   # <-- agregado para reportar errores al frontend

CANONICAL_COLUMNS = {
    "CRED": "Cred",
    "TIPO INSCRIPCION": "Tipo Inscripcion",
    "NRO IDEN": "Nro Iden",
}


def normalize_text(value):
    if pd.isna(value):
        return ""

    text = str(value).strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.upper().split())


def normalize_identifier(value):
    if pd.isna(value):
        return ""

    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return "".join(text.split()).upper()


def find_header_row(df_raw, required_keys):
    for idx in range(min(len(df_raw), 20)):
        normalized_row = {normalize_text(value) for value in df_raw.iloc[idx].tolist()}
        if required_keys.issubset(normalized_row):
            return idx
    return None


def canonicalize_columns(columns):
    final_columns = []
    used_names = {}

    for raw_column in columns:
        normalized = normalize_text(raw_column)
        canonical = CANONICAL_COLUMNS.get(normalized, str(raw_column).strip() if not pd.isna(raw_column) else "")
        canonical = canonical or "SinNombre"

        count = used_names.get(canonical, 0)
        used_names[canonical] = count + 1

        final_columns.append(canonical if count == 0 else f"{canonical}_{count + 1}")

    return final_columns


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

    if df_raw.empty:
        raise ValueError("❌ El archivo Excel está vacío.")

    # Validación mínima
    if df_raw.shape[0] < 4:
        raise ValueError("❌ El archivo es demasiado pequeño o no sigue el formato esperado.")

    required_keys = set(CANONICAL_COLUMNS.keys())
    header_row = find_header_row(df_raw, required_keys)

    if header_row is None:
        raise ValueError(
            "❌ No fue posible identificar la fila de encabezados. "
            "Verifica que el Excel contenga las columnas Cred, Tipo Inscripcion y Nro Iden."
        )

    new_header = df_raw.iloc[header_row].tolist()
    df = df_raw.iloc[header_row + 1 :].copy()
    df.columns = canonicalize_columns(new_header)
    df = df.reset_index(drop=True)
    df = df.dropna(how="all")

    # Validar columnas necesarias
    required_cols = ["Tipo Inscripcion", "Cred", "Nro Iden"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"❌ Falta la columna obligatoria: {col}")

    # Normalizar columnas clave
    try:
        df["Tipo Inscripcion"] = df["Tipo Inscripcion"].apply(normalize_text)
        df["Cred"] = df["Cred"].apply(normalize_identifier)
        df["Nro Iden"] = df["Nro Iden"].apply(normalize_identifier)
    except Exception as e:
        raise ValueError(f"❌ Error normalizando columnas: {e}")

    df = df[(df["Cred"] != "") & (df["Nro Iden"] != "")]
    df = df.reset_index(drop=True)

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
