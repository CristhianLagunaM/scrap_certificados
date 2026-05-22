from dataclasses import dataclass

import pandas as pd

from . import config
from .text_utils import normalize_header


@dataclass(frozen=True)
class ExcelData:
    dataframe: pd.DataFrame
    columns: dict[str, str]


def read_excel(path: str) -> ExcelData:
    try:
        dataframe = pd.read_excel(path, sheet_name=config.SHEET_NAME, dtype=str)
    except ValueError:
        dataframe = pd.read_excel(path, dtype=str)

    normalized_columns = {normalize_header(column): column for column in dataframe.columns}
    resolved: dict[str, str] = {}
    missing: list[str] = []

    for expected in config.REQUIRED_COLUMNS:
        real_name = normalized_columns.get(normalize_header(expected))
        if real_name:
            resolved[expected] = real_name
        else:
            missing.append(expected)

    if missing:
        joined = "\n- ".join(missing)
        raise ValueError(f"Faltan columnas obligatorias:\n- {joined}")

    return ExcelData(dataframe=dataframe, columns=resolved)

