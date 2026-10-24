import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import { AlertCircle, CheckCircle2, Database, Download, FileText, ShieldAlert, Sparkles } from "lucide-react";
import { jsPDF } from "jspdf";
import { ticketApi, errorMessage } from "../api/services";
import { objectOrEmpty, safeArray, fmt, parseResolutionSteps } from "../utils";
import { PageHeader, ResultBlock } from "../components/Common.jsx";

/* Pinned font versions (avoid "@latest" so the report never changes unexpectedly). */
const INTER_REGULAR_URL = "https://cdn.jsdelivr.net/fontsource/fonts/inter@5.0.8/latin-400-normal.ttf";
const INTER_BOLD_URL = "https://cdn.jsdelivr.net/fontsource/fonts/inter@5.0.8/latin-700-normal.ttf";

/* Convert a confidence score (0–1 or 0–100) to a whole percentage, or null if missing/invalid. */
function toPercent(score) {
  if (score === undefined || score === null || score === "") return null;
  const n = Number(score);
  if (!Number.isFinite(n)) return null;
  return Math.round(n <= 1 ? n * 100 : n);
}

export default function AIAnalysisPage() {
  const location = useLocation();
  const [ticket, setTicket] = useState(location.state?.ticketText || "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (location.state?.ticketText) {
      setTicket(location.state.ticketText);
      setResult(null);
    }
  }, [location.state]);

  async function downloadReport() {
    if (!result) return;

    const pdf = new jsPDF({ unit: "pt", format: "a4" });

    /* BugPilot design tokens — mirrors the light theme in src/theme.css */
    const C = {
      navy: "#2f4ac0",       // --accent-hover — header & footer bands
      accent: "#3b5bdb",     // --accent
      accentSoft: "#edf1ff", // --accent-soft
      ink: "#111827",        // --text
      text2: "#444c5e",      // --text-2
      muted: "#6f778a",      // --muted
      border: "#e2e5ec",     // --border
      track: "#eceef3",      // --surface-3
      danger: "#c92a2a", dangerSoft: "#fdeaea",
      warning: "#a86400", warningSoft: "#fdf1d8",
      success: "#12805c", successSoft: "#e4f6ee",
      info: "#1c7ed6", infoSoft: "#e7f3fd",
      white: "#ffffff",
    };

    // Load the app's UI font (Inter). Falls back to built-in Helvetica if the files can't be fetched.
    async function loadFont(url, fileKey, style) {
      try {
        const response = await fetch(url);
        if (!response.ok) return false;
        const bytes = new Uint8Array(await response.arrayBuffer());
        let binary = "";
        const chunk = 0x8000;
        for (let i = 0; i < bytes.length; i += chunk) {
          binary += String.fromCharCode(...bytes.subarray(i, i + chunk));
        }
        pdf.addFileToVFS(fileKey, btoa(binary));
        pdf.addFont(fileKey, "Inter", style);
        return true;
      } catch {
        return false; // graceful fallback to Helvetica
      }
    }

    const hasRegular = await loadFont(INTER_REGULAR_URL, "Inter-Regular.ttf", "normal");
    const hasBold = await loadFont(INTER_BOLD_URL, "Inter-Bold.ttf", "bold");
    const BODY = hasRegular ? "Inter" : "helvetica";
    const BOLD = hasBold ? "Inter" : "helvetica";
    const MONO = "courier"; // built-in mono for ticket/document codes

    const margin = 46;
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const contentWidth = pageWidth - margin * 2;
    const footerH = 30;
    const maxY = pageHeight - footerH - 24;
    let y = 0;

    const set = (family, style, size, color) => {
      pdf.setFont(family, style);
      pdf.setFontSize(size);
      pdf.setTextColor(color);
    };

    const newPage = () => {
      pdf.addPage();
      pdf.setFillColor(C.accent);
      pdf.rect(0, 0, pageWidth, 2.5, "F");
      y = 44;
    };

    const ensure = (height) => {
      if (y + height > maxY) newPage();
    };

    const chip = (text, fg, bg, x, top) => {
      set(BOLD, "bold", 8.5, fg);
      const w = pdf.getTextWidth(text) + 18;
      pdf.setFillColor(bg);
      pdf.roundedRect(x, top, w, 16, 8, 8, "F");
      pdf.text(text, x + w / 2, top + 11, { align: "center" });
      return w;
    };

    const severityStyle = (value) => {
      const key = String(value || "").toLowerCase();
      if (["critical", "high"].includes(key)) return { fg: C.danger, bg: C.dangerSoft };
      if (key === "medium") return { fg: C.warning, bg: C.warningSoft };
      if (key === "low") return { fg: C.success, bg: C.successSoft };
      return { fg: C.info, bg: C.infoSoft };
    };

    const confidenceStyle = (value) => {
      const key = String(value || "").toLowerCase();
      if (key === "high") return { fg: C.success, bg: C.successSoft };
      if (key === "medium") return { fg: C.info, bg: C.infoSoft };
      return { fg: C.warning, bg: C.warningSoft };
    };

    const heading = (text, badge) => {
      ensure(90); // keep headings together with at least some following content
      y += 8;
      set(BOLD, "bold", 12.5, C.navy);
      pdf.text(text, margin, y + 9);
      if (badge) {
        const textWidth = pdf.getTextWidth(text);
        chip(badge.text, badge.fg, badge.bg, margin + textWidth + 10, y);
      }
      pdf.setDrawColor(C.border);
      pdf.setLineWidth(0.75);
      pdf.line(margin, y + 16, pageWidth - margin, y + 16);
      pdf.setFillColor(C.accent);
      pdf.rect(margin, y + 14.6, 24, 2.8, "F");
      y += 30;
    };

    const paragraph = (text, { size = 10, color = C.text2 } = {}) => {
      set(BODY, "normal", size, color);
      const rows = pdf.splitTextToSize(String(text ?? "—"), contentWidth);
      const lineHeight = size * 1.55;
      ensure(Math.min(rows.length, 3) * lineHeight + 8);
      for (const row of rows) {
        if (y + lineHeight > maxY) {
          newPage();
          set(BODY, "normal", size, color); // restore font state after page break
        }
        pdf.text(row, margin, y + size);
        y += lineHeight;
      }
      y += 8;
    };

    const callout = (text) => {
      set(BODY, "normal", 10, C.ink);
      const rows = pdf.splitTextToSize(String(text ?? "—"), contentWidth - 30);
      const lineHeight = 10 * 1.55;
      const height = rows.length * lineHeight + 20;
      ensure(height + 8);
      pdf.setFillColor(C.accentSoft);
      pdf.roundedRect(margin, y, contentWidth, height, 6, 6, "F");
      pdf.setFillColor(C.accent);
      pdf.rect(margin, y + 7, 3, height - 14, "F");
      set(BODY, "normal", 10, C.ink);
      rows.forEach((row, index) => pdf.text(row, margin + 16, y + 18 + index * lineHeight));
      y += height + 16;
    };

    const metaCards = () => {
      const gap = 10;
      const cardW = (contentWidth - gap * 2) / 3;
      const cardH = 62;
      ensure(cardH + 8);
      const top = y;
      const cards = [
        {
          label: "SEVERITY",
          render: (x) => {
            const value = fmt(result.severity) === "—" ? "Not rated" : fmt(result.severity);
            const style = severityStyle(value);
            chip(value, style.fg, style.bg, x + 12, top + 28);
          },
        },
        {
          label: "CONFIDENCE",
          render: (x) => {
            const pct = toPercent(result.confidence_score);
            set(BOLD, "bold", 14, C.navy);
            pdf.text(pct === null ? "—" : `${pct}%`, x + 12, top + 41);
            if (pct !== null) {
              const trackW = cardW - 24;
              pdf.setFillColor(C.track);
              pdf.roundedRect(x + 12, top + 47, trackW, 4.5, 2.25, 2.25, "F");
              pdf.setFillColor(C.accent);
              pdf.roundedRect(x + 12, top + 47, Math.max((trackW * Math.min(pct, 100)) / 100, 4.5), 4.5, 2.25, 2.25, "F");
            }
          },
        },
        {
          label: "CATEGORY & MODULE",
          render: (x) => {
            const value = [result.category, result.module].filter(Boolean).join(" · ") || "Not specified";
            set(BODY, "normal", 8.5, C.text2);
            const rows = pdf.splitTextToSize(value, cardW - 24);
            rows.slice(0, 2).forEach((row, index) => pdf.text(row, x + 12, top + 33 + index * 11));
          },
        },
      ];

      cards.forEach((card, index) => {
        const x = margin + index * (cardW + gap);
        pdf.setFillColor(C.white);
        pdf.setDrawColor(C.border);
        pdf.setLineWidth(0.75);
        pdf.roundedRect(x, top, cardW, cardH, 6, 6, "FD");
        set(BODY, "normal", 7, C.muted);
        pdf.text(card.label, x + 12, top + 16, { charSpace: 0.6 });
        card.render(x);
      });
      y = top + cardH + 16;
    };

    const sourceList = (items, emptyText, mapItem) => {
      if (!items.length) {
        paragraph(emptyText, { size: 9.5, color: C.muted });
        return;
      }
      for (const item of items) {
        const { code, rest } = mapItem(item);
        set(MONO, "bold", 9, C.accent);
        const codeWidth = pdf.getTextWidth(code);
        const restX = margin + 12 + codeWidth + 8;
        set(BODY, "normal", 9.5, C.text2);
        const rows = pdf.splitTextToSize(rest, pageWidth - margin - restX);
        const lineHeight = 13;
        ensure(rows.length * lineHeight + 6);
        pdf.setFillColor(C.accent);
        pdf.rect(margin + 1, y + 4, 3.5, 3.5, "F");
        set(MONO, "bold", 9, C.accent);
        pdf.text(code, margin + 12, y + 10);
        set(BODY, "normal", 9.5, C.text2);
        rows.forEach((row, index) => pdf.text(row, restX, y + 10 + index * lineHeight));
        y += rows.length * lineHeight + 7;
      }
      y += 4;
    };

    /* ---- Page 1 header band ---- */
    const headerH = 96;
    pdf.setFillColor(C.navy);
    pdf.rect(0, 0, pageWidth, headerH, "F");
    pdf.setFillColor(C.accent);
    pdf.rect(0, headerH, pageWidth, 3, "F");

    set(MONO, "bold", 8, C.accentSoft);
    pdf.text("BUGPILOT · AI TRIAGE", margin, 30, { charSpace: 1.4 });
    set(BOLD, "bold", 20, C.white);
    pdf.text("AI Analysis Report", margin, 58);
    set(BODY, "normal", 8.5, C.accentSoft);
    pdf.text(`Generated: ${new Date().toLocaleString()}`, margin, 78);

    y = headerH + 27;

    /* ---- Report body (section order preserved) ---- */
    heading("Reported issue");
    callout(ticket);

    heading("Summary");
    paragraph(result.summary || result.problem || "Ticket analysis completed.");
    metaCards();

    heading("Ticket understanding");
    paragraph(result.problem || result.ticket || ticket);

    heading("Detailed analysis");
    paragraph(result.analysis || "Not available");

    heading("Historical evidence");
    paragraph(result.historical_evidence || "No historical evidence was returned.");

    heading("Likely cause");
    paragraph(result.likely_cause || "Not specified");

    heading("Suggested resolution");
    const resolutionSteps = parseResolutionSteps(result.suggested_resolution);
    if (!resolutionSteps.length) {
      paragraph(result.suggested_resolution || "Not specified");
    } else {
      for (const step of resolutionSteps) {
        set(BODY, "normal", 10, C.ink);
        const numW = 30;
        const rows = pdf.splitTextToSize(step.body, contentWidth - numW);
        const lineHeight = 10 * 1.55;
        const height = Math.max(rows.length * lineHeight, 18);
        ensure(height + 10);
        pdf.setFillColor(C.accentSoft);
        pdf.roundedRect(margin, y, 26, 15, 4.5, 4.5, "F");
        set(BOLD, "bold", 8.5, C.navy);
        pdf.text(String(step.step), margin + 13, y + 10.5, { align: "center" });
        set(BODY, "normal", 10, C.ink);
        rows.forEach((row, index) => pdf.text(row, margin + numW, y + 10 + index * lineHeight));
        y += height + 9;
      }
      y += 6;
    }

    const levelBadge = result.confidence_level
      ? { text: String(result.confidence_level).toUpperCase(), ...confidenceStyle(result.confidence_level) }
      : undefined;
    heading("Confidence check", levelBadge);
    paragraph(result.confidence_reason || "Not specified");

    const ticketSources = safeArray(result.retrieval_diagnostics?.ticket_sources);
    const documentSources = safeArray(result.retrieval_diagnostics?.financial_document_sources);

    heading("Retrieved historical tickets");
    sourceList(
      ticketSources,
      "No historical tickets were retrieved for this query.",
      (item) => ({
        code: item.ticket_code || "Ticket",
        rest: `${item.module || "Module unknown"} — ${item.category || "Category unknown"}`,
      }),
    );

    heading("Retrieved financial documents");
    sourceList(
      documentSources,
      "No financial documents were retrieved for this query.",
      (item) => ({
        code: item.document_code || "Document",
        rest: `${item.title || "Untitled"} — ${item.module || "Module unknown"}`,
      }),
    );

    /* ---- Navy footer bar on every page ---- */
    const totalPages = pdf.getNumberOfPages();
    for (let page = 1; page <= totalPages; page += 1) {
      pdf.setPage(page);
      const top = pageHeight - footerH;
      pdf.setFillColor(C.navy);
      pdf.rect(0, top, pageWidth, footerH, "F");
      pdf.setFillColor(C.accent);
      pdf.rect(0, top - 3, pageWidth, 3, "F");
      set(BODY, "normal", 7.5, C.white);
      pdf.text("BugPilot — AI Analysis Report", margin, top + footerH / 2 + 2.5);
      pdf.text(`Page ${page} of ${totalPages}`, pageWidth - margin, top + footerH / 2 + 2.5, { align: "right" });
    }

    const safeName =
      String(result.summary || "bugpilot-ai-analysis")
        .replace(/[^a-z0-9_-]+/gi, "-")
        .replace(/^-+|-+$/g, "")
        .slice(0, 50) || "bugpilot-ai-analysis";

    pdf.save(`${safeName}.pdf`);
  }

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setResult(null);
    try {
      const { data } = await ticketApi.analyze(ticket.trim());
      setResult(objectOrEmpty(data));
    } catch (err) {
      setError(errorMessage(err, "AI ticket analysis failed."));
    } finally {
      setBusy(false);
    }
  }

  const confidencePct = result ? toPercent(result.confidence_score) : null;
  const ticketSources = safeArray(result?.retrieval_diagnostics?.ticket_sources);
  const documentSources = safeArray(result?.retrieval_diagnostics?.financial_document_sources);
  const diag = result?.retrieval_diagnostics;

  return (
    <>
      <PageHeader
        eyebrow="AI TRIAGE"
        title="AI ticket analysis"
        description="Use BugPilot's existing analysis workflow to understand a reported issue and review suggested next steps."
      />

      <div className="analysis-layout">
        {/* Ticket input form */}
        <form className="panel analysis-form" onSubmit={submit}>
          <div className="panel-heading">
            <div>
              <h2>Describe the issue</h2>
              <p>Provide the ticket details in plain language.</p>
            </div>
            <span className="ai-chip">
              <Sparkles size={15} />
              AI assisted
            </span>
          </div>

          <textarea
            className="text-input analysis-textarea"
            value={ticket}
            onChange={(event) => setTicket(event.target.value)}
            minLength={5}
            maxLength={10000}
            placeholder="Example: Payroll users receive an error when exporting the monthly salary report. The export worked last week, but now the generated file is empty…"
            required
          />

          <div className="analysis-form-bottom">
            <span>{ticket.length.toLocaleString()} / 10,000 characters</span>
            <button
              type="submit"
              className="button button-primary"
              disabled={busy || ticket.trim().length < 5}
            >
              {busy ? (
                <>
                  <span className="spinner" />
                  Analyzing…
                </>
              ) : (
                <>
                  <Sparkles size={17} />
                  Analyze ticket
                </>
              )}
            </button>
          </div>

          {error && (
            <div className="alert alert-error">
              <AlertCircle size={17} />
              <span>{error}</span>
            </div>
          )}
        </form>

        {/* Keep the introduction in place; results open in a focused modal. */}
        <div className="panel analysis-explainer">
          <div className="explainer-art">
            <div className="orbit orbit-one" />
            <div className="orbit orbit-two" />
            <div className="explainer-bot"><Sparkles size={36} /></div>
            <span className="orbit-dot dot-one" />
            <span className="orbit-dot dot-two" />
            <span className="orbit-dot dot-three" />
          </div>
          <h3>Clarity for every ticket</h3>
          <p>Submit an issue to receive a structured analysis from your connected BugPilot backend.</p>
          <div className="explainer-list">
            <div><CheckCircle2 size={16} />Summary and categorization</div>
            <div><CheckCircle2 size={16} />Severity assessment and confidence guidance</div>
            <div><CheckCircle2 size={16} />Suggested resolution and confidence reason</div>
          </div>
          <small>Results depend on backend availability and your account's access.</small>
        </div>
      </div>

      {result && createPortal(
        <div
          className="modal-backdrop ai-result-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setResult(null);
          }}
        >
          <section className="ticket-modal ai-result-modal" role="dialog" aria-modal="true" aria-labelledby="ai-result-title">
            <div className="ai-modal-header">
              <div>
                <div className="eyebrow">AI ANALYSIS RESULT</div>
                <h2 id="ai-result-title">{result.summary || "Ticket analysis completed"}</h2>
                <p>Review the submitted issue and the AI-generated recommendations.</p>
              </div>
              <button type="button" className="icon-button border-button" aria-label="Close analysis result" onClick={() => setResult(null)}>×</button>
            </div>

            <div className="ai-query-block">
              <span>YOUR QUERY</span>
              <p>{ticket}</p>
            </div>

            {/* Banner keys off llm_status so it only appears for genuinely degraded results
                (the fast pipeline returns analysis_mode "llm_rag_fast" on success). */}
            {result.llm_status && result.llm_status !== "available" && (
              <div className="alert alert-warning analysis-mode-warning">
                <ShieldAlert size={17} />
                <span>
                  <b>Fallback / degraded analysis.</b> The AI model call failed, so this result came from the rule-based fallback instead of a real LLM analysis.
                  {result.llm_error ? ` Reason: ${result.llm_error}` : " Check the backend terminal for the underlying failure."}
                  {" "}Fix: start Ollama (ollama serve) and pull the model (ollama pull llama3.2:latest). If the reason mentions JSONDecodeError, the model returned malformed output; simply retry. You can also set HF_TOKEN in .env to enable the Hugging Face cloud fallback.
                </span>
              </div>
            )}

            <div className="retrieval-status-grid">
              <div><Database size={17} /><span><small>Historical tickets retrieved</small><b>{diag?.ticket_count ?? 0}</b></span></div>
              <div><FileText size={17} /><span><small>Financial documents retrieved</small><b>{diag?.financial_document_count ?? 0}</b></span></div>
              <div><Sparkles size={17} /><span><small>LLM provider</small><b>{result.llm_status || "unknown"}</b></span></div>
            </div>

            <div className="result-metrics">
              <div><span>Severity</span><b>{fmt(result.severity)}</b></div>
              <div><span>Confidence</span><b>{confidencePct === null ? "—" : `${confidencePct}%`}</b></div>
            </div>

            <ResultBlock title="Category & module" body={[result.category, result.module].filter(Boolean).join(" · ") || "Not specified"} />
            <ResultBlock title="Ticket understanding" body={result.problem || result.ticket || ticket} />
            <ResultBlock title="Detailed analysis" body={result.analysis} />
            <ResultBlock title="Historical evidence" body={result.historical_evidence} />
            <ResultBlock title="Likely cause" body={result.likely_cause} />

            <section className="result-block">
              <h3>Suggested resolution</h3>
              {(() => {
                const steps = parseResolutionSteps(result.suggested_resolution);
                if (!steps.length) {
                  return <p>{result.suggested_resolution || "No information returned for this field."}</p>;
                }
                return (
                  <ul className="resolution-steps">
                    {steps.map((item) => (
                      <li key={item.step}>
                        <span className="resolution-step-id">{item.step}</span>
                        <span>{item.body}</span>
                      </li>
                    ))}
                  </ul>
                );
              })()}
            </section>

            <ResultBlock title={`Confidence check · ${result.confidence_level || "Unrated"}`} body={result.confidence_reason} />

            <section className="result-block evidence-sources">
              <h3>Retrieved sources</h3>

              <h4>Historical tickets</h4>
              {ticketSources.length ? (
                <ul>
                  {ticketSources.map((item, index) => (
                    <li key={item.ticket_code || index}>
                      <b>{item.ticket_code}</b> · {item.module || "Module unknown"} · {item.category || "Category unknown"}{" "}
                      <small>({safeArray(item.retrieved_by).join(" + ") || "retrieval source unknown"})</small>
                    </li>
                  ))}
                </ul>
              ) : (
                <p>No historical tickets were retrieved for this query.</p>
              )}

              <h4>Financial SOPs / policies</h4>
              {documentSources.length ? (
                <ul>
                  {documentSources.map((item, index) => (
                    <li key={item.document_code || index}>
                      <b>{item.document_code}</b> · {item.title} · {item.module || "Module unknown"}
                    </li>
                  ))}
                </ul>
              ) : (
                <p>No financial documents were retrieved for this query.</p>
              )}

              {(diag?.semantic_error || diag?.keyword_error || diag?.financial_document_error) && (
                <>
                  <h4>Retrieval diagnostics</h4>
                  {diag?.semantic_error && <p>Semantic retrieval error: {diag.semantic_error}</p>}
                  {diag?.keyword_error && <p>Keyword retrieval error: {diag.keyword_error}</p>}
                  {diag?.financial_document_error && <p>Document retrieval error: {diag.financial_document_error}</p>}
                </>
              )}
            </section>

            {safeArray(result.missing_information).length > 0 && (
              <ResultBlock title="Information to collect" body={safeArray(result.missing_information).join(" · ")} />
            )}

            <div className="modal-actions">
              <button type="button" className="button button-secondary" onClick={downloadReport}>
                <Download size={16} /> Download report as PDF
              </button>
              <button type="button" className="button button-secondary" onClick={() => setResult(null)}>
                Close results
              </button>
            </div>
          </section>
        </div>,
        document.body
      )}
    </>
  );
}
