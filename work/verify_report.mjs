import fs from "node:fs/promises";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const input = await FileBlob.load("work/sample_report.xlsx");
const workbook = await SpreadsheetFile.importXlsx(input);
workbook.recalculate();

const tableCheck = await workbook.inspect({
  kind: "table",
  range: "'Spam hisoboti'!A1:J10",
  include: "values,formulas",
  tableMaxRows: 10,
  tableMaxCols: 10,
});
console.log(tableCheck.ndjson);

const errorCheck = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final formula error scan",
});
console.log(errorCheck.ndjson);

const preview = await workbook.render({
  sheetName: "Spam hisoboti",
  range: "A1:J10",
  scale: 1,
  format: "png",
});
await fs.writeFile("work/sample_report.png", new Uint8Array(await preview.arrayBuffer()));
