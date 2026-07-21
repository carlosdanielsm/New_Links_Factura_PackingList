import OpenAI from "openai";
import { NextResponse } from "next/server";
import { z } from "zod";

export const runtime = "nodejs";
export const maxDuration = 120;

const requestSchema = z.object({
  descriptionEs: z.string().max(4000),
  descriptionEn: z.string().max(4000),
  totalUnits: z.string().max(100),
  targetPrice: z.string().max(100),
  originalLink: z.string().max(2000),
});

const resultSchema = {
  type: "object",
  properties: {
    summary: { type: "string" },
    warnings: {
      type: "array",
      items: { type: "string" },
    },
    candidates: {
      type: "array",
      maxItems: 5,
      items: {
        type: "object",
        properties: {
          title: { type: "string" },
          url: { type: "string" },
          marketplace: {
            type: "string",
            enum: ["Alibaba", "Made-in-China"],
          },
          supplier: { type: "string" },
          listedPrice: { type: "string" },
          minimumOrder: { type: "string" },
          score: { type: "integer", minimum: 0, maximum: 100 },
          confidence: {
            type: "string",
            enum: ["alta", "media", "baja"],
          },
          matches: {
            type: "array",
            items: { type: "string" },
          },
          differences: {
            type: "array",
            items: { type: "string" },
          },
          rationale: { type: "string" },
        },
        required: [
          "title",
          "url",
          "marketplace",
          "supplier",
          "listedPrice",
          "minimumOrder",
          "score",
          "confidence",
          "matches",
          "differences",
          "rationale",
        ],
        additionalProperties: false,
      },
    },
  },
  required: ["summary", "warnings", "candidates"],
  additionalProperties: false,
} as const;

type CandidateResult = {
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

type SupplierSearchResult = {
  summary: string;
  warnings: string[];
  candidates: CandidateResult[];
};

function isAllowedCandidate(candidate: { url?: string }) {
  try {
    const hostname = new URL(candidate.url ?? "").hostname.toLowerCase();
    return (
      hostname === "alibaba.com" ||
      hostname.endsWith(".alibaba.com") ||
      hostname === "made-in-china.com" ||
      hostname.endsWith(".made-in-china.com")
    );
  } catch {
    return false;
  }
}

function normalizeText(value: string) {
  return value
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9ñ\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function hasAny(text: string, terms: string[]) {
  return terms.some((term) => text.includes(term));
}

function getCandidateText(candidate: CandidateResult) {
  return normalizeText([
    candidate.title,
    candidate.supplier,
    candidate.matches.join(" "),
    candidate.differences.join(" "),
    candidate.rationale,
  ].join(" "));
}

function clearMismatchReason(
  product: z.infer<typeof requestSchema>,
  candidate: CandidateResult,
) {
  const original = normalizeText([
    product.descriptionEs,
    product.descriptionEn,
    product.originalLink,
  ].join(" "));
  const candidateText = getCandidateText(candidate);

  const babyTerms = ["bebe", "baby", "infant", "newborn", "toddler", "kid", "kids", "child", "children", "nino", "nina", "niño", "niña"];
  const adultTerms = ["sexy", "lingerie", "lenceria", "adult", "erotic", "erotica", "pantyhose", "fishnet", "stocking", "stockings", "thigh high"];
  const cottonTerms = ["algodon", "cotton"];
  const nylonTerms = ["nylon", "nailon", "polyamide", "poliamida"];
  const sockTerms = ["media", "medias", "calcetin", "calcetines", "sock", "socks"];
  const chargerTerms = ["cargador", "charger", "adapter", "adaptador", "power supply", "fuente"];
  const jewelryTerms = ["jewelry", "joyeria", "necklace", "collar", "bracelet", "pulsera", "earring", "arete", "bangle"];
  const jeansTerms = ["jeans", "denim", "pantalon", "pants"];

  if (hasAny(original, babyTerms) && hasAny(candidateText, adultTerms)) {
    return "El producto original es para bebé/niños y el candidato apunta a lencería/adulto.";
  }

  if (hasAny(original, babyTerms) && !hasAny(candidateText, babyTerms)) {
    return "El producto original indica bebé/niños y el candidato no confirma ese público.";
  }

  if (hasAny(original, cottonTerms) && hasAny(candidateText, nylonTerms) && !hasAny(candidateText, cottonTerms)) {
    return "El material principal no coincide: original de algodón y candidato de nailon/poliamida.";
  }

  if (hasAny(original, sockTerms) && hasAny(candidateText, adultTerms)) {
    return "El candidato parece medias/lencería de adulto, no medias/calcetines equivalentes al original.";
  }

  if (hasAny(original, chargerTerms) && !hasAny(candidateText, chargerTerms)) {
    return "El original es cargador/fuente y el candidato no confirma esa función.";
  }

  if (hasAny(original, jewelryTerms) && !hasAny(candidateText, jewelryTerms)) {
    return "El original es joyería/accesorios y el candidato no confirma esa categoría.";
  }

  if (hasAny(original, jeansTerms) && !hasAny(candidateText, jeansTerms)) {
    return "El original es jeans/denim y el candidato no confirma esa categoría.";
  }

  return undefined;
}

const genericStopWords = new Set([
  "para",
  "with",
  "and",
  "the",
  "una",
  "uno",
  "los",
  "las",
  "por",
  "con",
  "sin",
  "set",
  "new",
  "de",
  "la",
  "el",
  "en",
  "del",
  "y",
  "or",
  "for",
  "of",
  "to",
  "un",
]);

function extractImportantTerms(text: string) {
  return normalizeText(text)
    .split(" ")
    .filter((word) => word.length >= 4 && !genericStopWords.has(word))
    .slice(0, 18);
}

function weakSemanticOverlapReason(
  product: z.infer<typeof requestSchema>,
  candidate: CandidateResult,
) {
  const originalTerms = Array.from(new Set(extractImportantTerms([
    product.descriptionEs,
    product.descriptionEn,
  ].join(" "))));

  if (originalTerms.length < 3) return undefined;

  const candidateText = getCandidateText(candidate);
  const matches = originalTerms.filter((term) => candidateText.includes(term));
  const ratio = matches.length / originalTerms.length;

  if (ratio < 0.18 && candidate.confidence !== "alta") {
    return `El candidato comparte muy pocos términos decisivos con el original (${matches.length}/${originalTerms.length}).`;
  }

  return undefined;
}

function filterClearlyWrongCandidates(
  product: z.infer<typeof requestSchema>,
  candidates: CandidateResult[],
) {
  const kept: CandidateResult[] = [];
  const removedReasons = new Set<string>();

  for (const candidate of candidates) {
    const reason = clearMismatchReason(product, candidate);
    if (reason) {
      removedReasons.add(reason);
      continue;
    }
    const weakOverlapReason = weakSemanticOverlapReason(product, candidate);
    if (weakOverlapReason) {
      removedReasons.add(weakOverlapReason);
      continue;
    }
    kept.push(candidate);
  }

  return {
    candidates: kept,
    warnings: Array.from(removedReasons).map(
      (reason) => `Se descartaron candidatos por baja equivalencia: ${reason}`,
    ),
  };
}

function normalizeNumberToken(value: string) {
  const token = value.replace(/[^\d.,]/g, "");
  const lastDot = token.lastIndexOf(".");
  const lastComma = token.lastIndexOf(",");

  if (lastDot >= 0 && lastComma >= 0) {
    const decimalSeparator = lastDot > lastComma ? "." : ",";
    const thousandsSeparator = decimalSeparator === "." ? "," : ".";
    return Number(token.replaceAll(thousandsSeparator, "").replace(decimalSeparator, "."));
  }

  if (lastComma >= 0) {
    const decimals = token.length - lastComma - 1;
    return Number(token.replaceAll(".", "").replace(",", decimals <= 2 ? "." : ""));
  }

  return Number(token.replaceAll(",", ""));
}

function extractNumbers(value: string) {
  return Array.from(value.matchAll(/\d+(?:[.,]\d+)*/g))
    .map((match) => normalizeNumberToken(match[0]))
    .filter((number) => Number.isFinite(number) && number > 0 && number < 100000);
}

function pickClosestPrice(listedPrice: string, targetPrice: number) {
  const prices = extractNumbers(listedPrice);
  if (!prices.length) return undefined;

  return prices.reduce((closest, price) =>
    Math.abs(price - targetPrice) < Math.abs(closest - targetPrice) ? price : closest,
  );
}

function priceScoreFromRatio(ratio: number) {
  if (ratio <= 0.1) return 100;
  if (ratio <= 0.25) return 90;
  if (ratio <= 0.5) return 70;
  if (ratio <= 1) return 45;
  if (ratio <= 2) return 20;
  return 5;
}

function rerankByTargetPrice(
  candidates: CandidateResult[],
  targetPriceText: string,
) {
  const targetPrice = extractNumbers(targetPriceText)[0];
  if (!targetPrice) return candidates;

  return candidates
    .map((candidate) => {
      const candidatePrice = pickClosestPrice(candidate.listedPrice, targetPrice);

      if (!candidatePrice) {
        const score = Math.min(75, Math.round(candidate.score * 0.75));
        return {
          ...candidate,
          score,
          confidence: candidate.confidence === "alta" ? "media" : candidate.confidence,
          differences: [
            ...candidate.differences,
            "No se pudo comparar el precio porque el precio publicado no es visible o no es numérico.",
          ],
          rationale: `${candidate.rationale} Precio objetivo: ${targetPriceText}. Precio publicado no comparable, por eso se limita el puntaje.`,
        };
      }

      const differenceRatio = Math.abs(candidatePrice - targetPrice) / targetPrice;
      const direction = candidatePrice > targetPrice ? "por encima" : "por debajo";
      const differencePercent = Math.round(differenceRatio * 100);
      const priceScore = priceScoreFromRatio(differenceRatio);
      let score = Math.round(candidate.score * 0.55 + priceScore * 0.45);

      if (differenceRatio > 1.5) score = Math.min(score, 45);
      else if (differenceRatio > 0.75) score = Math.min(score, 62);
      else if (differenceRatio > 0.35) score = Math.min(score, 78);

      const priceNote =
        `Precio comparable aprox. ${candidatePrice}; está ${differencePercent}% ${direction} del objetivo ${targetPrice}.`;

      return {
        ...candidate,
        score,
        differences:
          differenceRatio > 0.35
            ? [...candidate.differences, priceNote]
            : candidate.differences,
        matches:
          differenceRatio <= 0.25
            ? [...candidate.matches, priceNote]
            : candidate.matches,
        rationale: `${candidate.rationale} ${priceNote}`,
      };
    })
    .sort((a, b) => b.score - a.score);
}

export async function POST(request: Request) {
  if (!process.env.OPENAI_API_KEY) {
    return NextResponse.json(
      { error: "Falta configurar OPENAI_API_KEY en .env.local." },
      { status: 503 },
    );
  }

  const parsed = requestSchema.safeParse(await request.json());
  if (!parsed.success) {
    return NextResponse.json(
      { error: "Los datos del producto no son válidos." },
      { status: 400 },
    );
  }

  const product = parsed.data;
  if (!product.descriptionEs && !product.descriptionEn && !product.originalLink) {
    return NextResponse.json(
      { error: "La fila no contiene información suficiente para buscar." },
      { status: 400 },
    );
  }

  try {
    const client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
    const configuredModel = process.env.OPENAI_MODEL?.trim();
    const model =
      configuredModel && configuredModel !== "gpt-5.4-mini"
        ? configuredModel
        : "gpt-4.1-mini";

    const response = await client.responses.create({
      model,
      store: false,
      tools: [
        {
          type: "web_search",
          search_context_size: "low",
        },
      ],
      tool_choice: "auto",
      text: {
        format: {
          type: "json_schema",
          name: "supplier_product_candidates",
          strict: true,
          schema: resultSchema,
        },
      },
      input: [
        {
          role: "system",
          content:
            "Eres analista de compras internacionales. Busca productos reales y visibles en Alibaba y Made-in-China. La equivalencia real del producto es obligatoria: mismo tipo de producto, mismo uso, mismo público objetivo, material principal compatible y especificaciones clave compatibles. No inventes datos: usa 'No visible' cuando la página no los muestre. Rechaza productos que sólo compartan una palabra genérica pero pertenezcan a otra categoría, uso, material o público objetivo. Ejemplo: si el original son medias/calcetines de algodón para bebé, no aceptes medias de nailon, lencería, pantimedias sexy, stockings/fishnet o productos para adulto. Si no encuentras equivalentes razonables, devuelve pocos candidatos o cero candidatos; es mejor no devolver nada que devolver enlaces engañosos. El precio objetivo es importante, pero nunca debe pesar más que la equivalencia real del producto. Prioriza precio unitario visible cercano al objetivo, idealmente dentro de ±25%. Devuelve como máximo cinco candidatos, ordenados primero por equivalencia técnica real y luego por cercanía de precio. Una URL debe apuntar a una ficha concreta del producto, no a una búsqueda, categoría o página principal. Asigna confianza baja si faltan especificaciones decisivas o si hay duda de equivalencia.",
        },
        {
          role: "user",
          content: `Producto de referencia:
- Descripción en español: ${product.descriptionEs || "No disponible"}
- Descripción en inglés: ${product.descriptionEn || "No disponible"}
- Unidades solicitadas: ${product.totalUnits || "No disponible"}
- Precio objetivo: ${product.targetPrice || "No disponible"}
- Enlace original para identificar el producto: ${product.originalLink || "No disponible"}

Busca alternativas lo más parecidas posible, pero descarta opciones de otra categoría, otro material principal, otro uso o diferente público objetivo. Si la descripción incluye edad, género, bebé/niño/adulto, material o estilo, esos datos son obligatorios para aceptar un candidato. Explica coincidencias y diferencias verificables.`,
        },
      ],
    });

    const result = JSON.parse(response.output_text) as SupplierSearchResult;
    if (Array.isArray(result.candidates)) {
      const domainFiltered = result.candidates.filter(isAllowedCandidate);
      const equivalenceFiltered = filterClearlyWrongCandidates(product, domainFiltered);
      result.candidates = rerankByTargetPrice(
        equivalenceFiltered.candidates,
        product.targetPrice,
      );
      result.warnings = [...result.warnings, ...equivalenceFiltered.warnings];
    } else {
      result.candidates = [];
    }

    return NextResponse.json(result);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Error desconocido de búsqueda.";
    console.error("OpenAI product search failed:", message);
    return NextResponse.json(
      { error: "No se pudo completar la búsqueda. Revisa la clave, saldo y conexión." },
      { status: 502 },
    );
  }
}
