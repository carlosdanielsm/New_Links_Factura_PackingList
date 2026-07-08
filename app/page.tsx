"use client";

import { useMemo, useState } from "react";
import { exportResults, readProducts } from "@/lib/spreadsheet";
import type { ProductRow, SearchResult } from "@/lib/types";

export default function Home() {
  const [rows, setRows] = useState<ProductRow[]>([]);
  const [selectedId, setSelectedId] = useState<string>();
  const [fileName, setFileName] = useState("");
  const [notice, setNotice] = useState("");
  const [searchingAll, setSearchingAll] = useState(false);

  const selected = useMemo(
    () => rows.find((row) => row.id === selectedId) ?? rows[0],
    [rows, selectedId],
  );

  async function handleFile(file?: File) {
    if (!file) return;
    setNotice("");
    setSearchingAll(false);
    try {
      const products = await readProducts(file);
      setRows(products);
      setSelectedId(products[0]?.id);
      setFileName(file.name);
      if (!products.length) setNotice("No se encontraron filas con productos.");
    } catch (error) {
      setRows([]);
      setFileName("");
      setNotice(error instanceof Error ? error.message : "No se pudo leer el archivo.");
    }
  }

  async function requestAlternatives(product: ProductRow) {
    const response = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(product),
    });

    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "La búsqueda falló.");
    return payload as SearchResult;
  }

  async function searchProduct(product: ProductRow) {
    if (product.status === "buscando") return;

    setRows((current) =>
      current.map((row) =>
        row.id === product.id
          ? { ...row, status: "buscando", error: undefined }
          : row,
      ),
    );

    try {
      const result = await requestAlternatives(product);
      setRows((current) =>
        current.map((row) =>
          row.id === product.id
            ? { ...row, status: "listo", result }
            : row,
        ),
      );
    } catch (error) {
      setRows((current) =>
        current.map((row) =>
          row.id === product.id
            ? {
                ...row,
                status: "error",
                error: error instanceof Error ? error.message : "Error inesperado.",
              }
            : row,
        ),
      );
    }
  }

  async function searchRow(id: string) {
    const product = rows.find((row) => row.id === id);
    if (!product || searchingAll) return;
    await searchProduct(product);
  }

  async function searchAllRows() {
    if (searchingAll || rows.length === 0) return;

    setSearchingAll(true);
    setNotice("Buscando alternativas para todos los productos, uno por uno.");

    const productsToSearch = rows.filter((row) => row.status !== "buscando");
    try {
      for (const product of productsToSearch) {
        setSelectedId(product.id);
        await searchProduct(product);
      }
      setNotice("Búsqueda de todos los productos finalizada.");
    } finally {
      setSearchingAll(false);
    }
  }

  const completed = rows.filter((row) => row.status === "listo").length;
  const hasRows = rows.length > 0;

  return (
    <main>
      <header className="hero">
        <div>
          <span className="eyebrow">Compras · búsqueda asistida</span>
          <h1>Proveedor IA</h1>
          <p>
            Carga la hoja, revisa cada producto y compara alternativas rastreables
            en Alibaba y Made-in-China.
          </p>
        </div>
        <div className="heroMark" aria-hidden="true">PI</div>
      </header>

      <section className="upload card">
        <div>
          <h2>1. Cargar hoja de cálculo</h2>
          <p className="muted">
            Se procesa localmente. La clave de OpenAI nunca llega al navegador.
          </p>
        </div>
        <label className="fileButton">
          <input
            type="file"
            accept=".xlsx"
            onChange={(event) => handleFile(event.target.files?.[0])}
          />
          {fileName ? "Cambiar archivo" : "Elegir archivo"}
        </label>
        {fileName && <span className="fileName">{fileName}</span>}
        {notice && <p className="notice">{notice}</p>}
      </section>

      {hasRows && (
        <div className="workspace">
          <aside className="card sidebar">
            <div className="sectionHeading">
              <div>
                <h2>2. Productos</h2>
                <p className="muted">{completed} de {rows.length} revisados</p>
              </div>
              <div className="sidebarActions">
                <button
                  className="primary compact"
                  disabled={searchingAll}
                  onClick={searchAllRows}
                >
                  {searchingAll ? "Buscando todos…" : "Buscar todos"}
                </button>
                {completed > 0 && (
                  <button className="ghost" onClick={() => exportResults(rows)}>
                    Exportar
                  </button>
                )}
              </div>
            </div>

            <div className="rowList">
              {rows.map((row) => (
                <button
                  key={row.id}
                  className={`rowItem ${selected?.id === row.id ? "active" : ""}`}
                  onClick={() => setSelectedId(row.id)}
                >
                  <span className={`status ${row.status}`} />
                  <span>
                    <strong>Fila {row.sourceRow}</strong>
                    <small>
                      {row.descriptionEn || row.descriptionEs || "Sin descripción"}
                    </small>
                  </span>
                </button>
              ))}
            </div>
          </aside>

          {selected && (
            <section className="detail">
              <article className="card productCard">
                <div className="sectionHeading">
                  <div>
                    <span className="eyebrow">Fila {selected.sourceRow}</span>
                    <h2>{selected.descriptionEn || selected.descriptionEs}</h2>
                  </div>
                  <button
                    className="primary"
                    disabled={selected.status === "buscando" || searchingAll}
                    onClick={() => searchRow(selected.id)}
                  >
                    {selected.status === "buscando"
                      ? "Buscando…"
                      : selected.status === "listo"
                        ? "Buscar de nuevo"
                        : "Buscar alternativas"}
                  </button>
                </div>

                <dl className="facts">
                  <div><dt>Descripción ES</dt><dd>{selected.descriptionEs || "—"}</dd></div>
                  <div><dt>Cantidad</dt><dd>{selected.totalUnits || "—"}</dd></div>
                  <div><dt>Precio objetivo</dt><dd>{selected.targetPrice || "—"}</dd></div>
                  <div>
                    <dt>Referencia</dt>
                    <dd>
                      {selected.originalLink ? (
                        <a href={selected.originalLink} target="_blank" rel="noreferrer">
                          Abrir enlace original ↗
                        </a>
                      ) : "—"}
                    </dd>
                  </div>
                </dl>
                {selected.error && <p className="errorBox">{selected.error}</p>}
              </article>

              {selected.result && (
                <>
                  <article className="card summary">
                    <h3>Lectura de la búsqueda</h3>
                    <p>{selected.result.summary}</p>
                    {selected.result.warnings.length > 0 && (
                      <ul>
                        {selected.result.warnings.map((warning) => (
                          <li key={warning}>{warning}</li>
                        ))}
                      </ul>
                    )}
                  </article>

                  <div className="candidates">
                    {selected.result.candidates.map((candidate, index) => (
                      <article className="card candidate" key={`${candidate.url}-${index}`}>
                        <div className="candidateTop">
                          <span className="rank">#{index + 1}</span>
                          <span className="market">{candidate.marketplace}</span>
                          <span className="score">{candidate.score}/100</span>
                        </div>
                        <h3>{candidate.title}</h3>
                        <p className="supplier">{candidate.supplier || "Proveedor no visible"}</p>
                        <div className="priceLine">
                          <span><small>Precio publicado</small>{candidate.listedPrice}</span>
                          <span><small>Pedido mínimo</small>{candidate.minimumOrder}</span>
                          <span><small>Confianza</small>{candidate.confidence}</span>
                        </div>
                        <div className="comparison">
                          <div>
                            <h4>Coincide</h4>
                            <ul>{candidate.matches.map((item) => <li key={item}>{item}</li>)}</ul>
                          </div>
                          <div>
                            <h4>Por confirmar</h4>
                            <ul>{candidate.differences.map((item) => <li key={item}>{item}</li>)}</ul>
                          </div>
                        </div>
                        <p className="rationale">{candidate.rationale}</p>
                        <a className="candidateLink" href={candidate.url} target="_blank" rel="noreferrer">
                          Ver ficha del producto ↗
                        </a>
                      </article>
                    ))}
                    {selected.result.candidates.length === 0 && (
                      <article className="card empty">
                        No se hallaron fichas confiables en los dos marketplaces.
                      </article>
                    )}
                  </div>
                </>
              )}
            </section>
          )}
        </div>
      )}

      {!hasRows && (
        <section className="emptyState">
          <span>01</span>
          <h2>Empieza con la hoja que ya conoces</h2>
          <p>
            Debe incluir exactamente las cinco columnas indicadas. El sistema no
            modifica el archivo original.
          </p>
        </section>
      )}
    </main>
  );
}
