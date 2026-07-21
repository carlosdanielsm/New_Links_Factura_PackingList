export const REQUIRED_COLUMNS = [
  "DESCRIPTION NUEVA ESPAÑOL",
  "DESCRIPTION NUEVA INGLES",
  "TOTAL UNIT",
  "PRICE",
  "LINKS ORIGINAL",
] as const;

export type ProductInput = {
  descriptionEs: string;
  descriptionEn: string;
  totalUnits: string;
  targetPrice: string;
  originalLink: string;
};

export type Candidate = {
  title: string;
  url: string;
  marketplace: "Alibaba" | "Made-in-China";
  supplier: string;
  listedPrice: string;
  minimumOrder: string;
  score: number;
  confidence: "alta" | "media" | "baja";
  matches: string[];
  differences: string[];
  rationale: string;
};

export type SearchResult = {
  summary: string;
  warnings: string[];
  candidates: Candidate[];
};

export type ProductRow = ProductInput & {
  id: string;
  sourceRow: number;
  result?: SearchResult;
  status: "pendiente" | "buscando" | "listo" | "error";
  error?: string;
};
