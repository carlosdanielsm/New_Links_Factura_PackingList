import ExcelJS from "exceljs";
import {
  REQUIRED_COLUMNS,
  type ProductRow,
} from "@/lib/types";

function normalizeHeader(value: string) {
  return value.trim().replace(/\s+/g, " ").toUpperCase();
}

function cellText(cell: ExcelJS.Cell) {
  if (cell.hyperlink) return cell.hyperlink.trim();
  return cell.text.trim();
}

export async function readProducts(file: File): Promise<ProductRow[]> {
  const workbook = new ExcelJS.Workbook();
  const bytes = new Uint8Array(await file.arrayBuffer());
  // ExcelJS acepta Uint8Array en el navegador, aunque sus tipos declaran Buffer.
  // @ts-expect-error Desajuste conocido entre los tipos Node y la API del navegador.
  await workbook.xlsx.load(bytes);
  const firstSheet = workbook.worksheets[0];

  if (!firstSheet) {
    throw new Error("El archivo no contiene hojas.");
  }

  if (firstSheet.rowCount < 2) {
    throw new Error("La primera hoja está vacía.");
  }

  const headerMap = new Map<string, number>();
  firstSheet.getRow(1).eachCell({ includeEmpty: false }, (cell, column) => {
    headerMap.set(normalizeHeader(cell.text), column);
  });

  const missing = REQUIRED_COLUMNS.filter(
    (column) => !headerMap.has(normalizeHeader(column)),
  );

  if (missing.length > 0) {
    throw new Error(`Faltan columnas: ${missing.join(", ")}.`);
  }

  const get = (
    row: ExcelJS.Row,
    column: (typeof REQUIRED_COLUMNS)[number],
  ) => cellText(row.getCell(headerMap.get(normalizeHeader(column))!));

  const products: ProductRow[] = [];
  firstSheet.eachRow({ includeEmpty: false }, (row, rowNumber) => {
    if (rowNumber === 1) return;
    products.push({
      id: `${Date.now()}-${rowNumber}`,
      sourceRow: rowNumber,
      descriptionEs: get(row, "DESCRIPTION NUEVA ESPAÑOL"),
      descriptionEn: get(row, "DESCRIPTION NUEVA INGLES"),
      totalUnits: get(row, "TOTAL UNIT"),
      targetPrice: get(row, "PRICE"),
      originalLink: get(row, "LINKS ORIGINAL"),
      status: "pendiente",
    });
  });

  return products.filter(
    (row) => row.descriptionEs || row.descriptionEn || row.originalLink,
  );
}

export async function exportResults(rows: ProductRow[]) {
  const records = rows.flatMap<Record<string, string | number>>((row) => {
    if (!row.result?.candidates.length) {
      return [{
        "FILA ORIGINAL": row.sourceRow,
        "DESCRIPTION NUEVA ESPAÑOL": row.descriptionEs,
        "DESCRIPTION NUEVA INGLES": row.descriptionEn,
        "TOTAL UNIT": row.totalUnits,
        PRICE: row.targetPrice,
        "LINKS ORIGINAL": row.originalLink,
        ESTADO: row.status,
        ERROR: row.error ?? "",
      }];
    }

    return row.result.candidates.map((candidate, index) => ({
      "FILA ORIGINAL": row.sourceRow,
      "DESCRIPTION NUEVA ESPAÑOL": row.descriptionEs,
      "DESCRIPTION NUEVA INGLES": row.descriptionEn,
      "TOTAL UNIT": row.totalUnits,
      PRICE: row.targetPrice,
      "LINKS ORIGINAL": row.originalLink,
      "RANK CANDIDATO": index + 1,
      "PUNTAJE IA": candidate.score,
      CONFIANZA: candidate.confidence,
      MARKETPLACE: candidate.marketplace,
      PRODUCTO: candidate.title,
      PROVEEDOR: candidate.supplier,
      "PRECIO PUBLICADO": candidate.listedPrice,
      MOQ: candidate.minimumOrder,
      "ENLACE CANDIDATO": candidate.url,
      COINCIDENCIAS: candidate.matches.join(" | "),
      DIFERENCIAS: candidate.differences.join(" | "),
      JUSTIFICACION: candidate.rationale,
    }));
  });

  const workbook = new ExcelJS.Workbook();
  const sheet = workbook.addWorksheet("Resultados");
  const headers = Array.from(
    records.reduce((all, record) => {
      Object.keys(record).forEach((key) => all.add(key));
      return all;
    }, new Set<string>()),
  );

  sheet.columns = headers.map((header) => ({
    header,
    key: header,
    width: Math.min(50, Math.max(14, header.length + 2)),
  }));
  records.forEach((record) => sheet.addRow(record));
  sheet.getRow(1).font = { bold: true };
  sheet.views = [{ state: "frozen", ySplit: 1 }];

  const buffer = await workbook.xlsx.writeBuffer();
  const blob = new Blob([new Uint8Array(buffer)], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "resultados-proveedor-ia.xlsx";
  anchor.click();
  URL.revokeObjectURL(url);
}
