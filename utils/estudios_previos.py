from docx import Document
import pandas as pd
import zipfile
import os

class EstudiosPreviosGenerator:

    def replace_placeholder(self, container, search_text, value):
        for paragraph in container.paragraphs:
            for run in paragraph.runs:
                if search_text in run.text:
                    font = run.font
                    size = font.size
                    bold = font.bold
                    italic = font.italic
                    underline = font.underline
                    name = font.name

                    run.text = run.text.replace(search_text, value)

                    run.font.size = size
                    run.font.bold = bold
                    run.font.italic = italic
                    run.font.underline = underline
                    run.font.name = name

        if hasattr(container, "tables"):
            for table in container.tables:
                for row in table.rows:
                    for cell in row.cells:
                        self.replace_placeholder(cell, search_text, value)

    def generate(self, excel_path, word_path, output_folder):
        df = pd.read_excel(excel_path)

        zip_name = "estudios_previos.zip"
        zip_path = os.path.join(output_folder, zip_name)

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
            for i, (_, fila) in enumerate(df.iterrows(), start=1):
                doc = Document(word_path)

                data = {
                    f"-{col.strip()}": "" if pd.isna(fila[col]) else str(fila[col]).strip()
                    for col in df.columns
                }

                for placeholder, value in data.items():
                    self.replace_placeholder(doc, placeholder, value)

                out_name = f"Estudios_Previos_{i}.docx"
                out_path = os.path.join(output_folder, out_name)
                doc.save(out_path)

                zipf.write(out_path, out_name)

        return zip_name
