import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";

import { AlertCircle, CheckCircle2, Database, Download, FileText, ShieldAlert, Sparkles } from "lucide-react";
import { jsPDF } from "jspdf";

import { ticketApi, errorMessage } from "../api/services";

import { objectOrEmpty, safeArray, fmt } from "../utils";

import { PageHeader, ResultBlock } from "../components/Common.jsx";

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

  function downloadReport() {
    if (!result) return;
    const pdf = new jsPDF({ unit: "pt", format: "a4" });
    const margin = 44;
    const pageWidth = pdf.internal.pageSize.getWidth();
    const pageHeight = pdf.internal.pageSize.getHeight();
    const maxWidth = pageWidth - margin * 2;
    let y = 48;

    const addText = (text, size = 10, bold = false, gap = 7) => {
      pdf.setFont("helvetica", bold ? "bold" : "normal");
      pdf.setFontSize(size);
      const lines = pdf.splitTextToSize(String(text ?? "—"), maxWidth);
      const lineHeight = size * 1.45;
      if (y + lines.length * lineHeight > pageHeight - margin) {
        pdf.addPage();
        y = margin;
      }
      pdf.text(lines, margin, y);
      y += lines.length * lineHeight + gap;
    };

    addText("BugPilot — AI Analysis Report", 18, true, 12);
    addText(`Generated: ${new Date().toLocaleString()}`, 9, false, 12);
    addText("Reported issue", 12, true, 4);
    addText(ticket, 10);
    addText("Summary", 12, true, 4);
    addText(result.summary || result.problem || "Ticket analysis completed.");
    addText("Severity", 12, true, 4);
    addText(fmt(result.severity), 10);
    addText("Confidence", 12, true, 4);
    addText(result.confidence_score === undefined ? "Not available" : `${Math.round(Number(result.confidence_score) <= 1 ? Number(result.confidence_score) * 100 : Number(result.confidence_score))}%`);
    addText("Category & module", 12, true, 4);
    addText([result.category, result.module].filter(Boolean).join(" · ") || "Not specified");
    addText("Ticket understanding", 12, true, 4);
    addText(result.problem || result.ticket || ticket);
    addText("Detailed analysis", 12, true, 4);
    addText(result.analysis || "Not available");
    addText("Historical evidence used by RAG", 12, true, 4);
    addText(result.historical_evidence || "No historical evidence was returned.");
    addText("Likely cause", 12, true, 4);
    addText(result.likely_cause || "Not specified");
    addText("Suggested resolution", 12, true, 4);
    addText(result.suggested_resolution || "Not specified");
    addText(`Confidence check — ${result.confidence_level || "Unrated"}`, 12, true, 4);
    addText(result.confidence_reason || "Not specified");
    const ticketSources = result.retrieval_diagnostics?.ticket_sources || [];
    const documentSources = result.retrieval_diagnostics?.financial_document_sources || [];
    addText("Retrieved historical tickets", 12, true, 4);
    addText(ticketSources.length ? ticketSources.map((item) => `${item.ticket_code || "Ticket"} — ${item.module || "Module unknown"} — ${item.category || "Category unknown"}`).join("\n") : "No historical tickets retrieved.");
    addText("Retrieved financial documents", 12, true, 4);
    addText(documentSources.length ? documentSources.map((item) => `${item.document_code || "Document"} — ${item.title || "Untitled"} — ${item.module || "Module unknown"}`).join("\n") : "No financial documents retrieved.");
    addText("Retrieval diagnostics", 12, true, 4);
    addText(`Keyword: ${result.retrieval_diagnostics?.keyword_search || "unknown"}; Semantic: ${result.retrieval_diagnostics?.semantic_search || "unknown"}; Financial documents: ${result.retrieval_diagnostics?.financial_document_search || "unknown"}`);
    const safeName = String(result.summary || "bugpilot-ai-analysis").replace(/[^a-z0-9-_]+/gi, "-").replace(/^-+|-+$/g, "").slice(0, 50) || "bugpilot-ai-analysis";
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
        </div>      </div>

      {result && createPortal(
        <div className="modal-backdrop ai-result-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setResult(null);
        }}>
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
            {result.analysis_mode && result.analysis_mode !== "llm_rag" && (
              <div className="alert alert-warning analysis-mode-warning">
                <ShieldAlert size={17} />
                <span><b>Fallback / degraded analysis.</b> This is not a fully successful Hugging Face RAG analysis. {result.llm_error || "Check the backend terminal for the underlying failure."}</span>
              </div>
            )}
            <div className="retrieval-status-grid">
              <div><Database size={17}/><span><small>Historical tickets retrieved</small><b>{result.retrieval_diagnostics?.ticket_count ?? 0}</b></span></div>
              <div><FileText size={17}/><span><small>Financial documents retrieved</small><b>{result.retrieval_diagnostics?.financial_document_count ?? 0}</b></span></div>
              <div><Sparkles size={17}/><span><small>LLM provider</small><b>{result.llm_status || "unknown"}</b></span></div>
            </div>
            <div className="result-metrics">
              <div><span>Severity</span><b>{fmt(result.severity)}</b></div>
              <div><span>Confidence</span><b>{result.confidence_score === undefined ? "—" : `${Math.round(Number(result.confidence_score) <= 1 ? Number(result.confidence_score) * 100 : Number(result.confidence_score))}%`}</b></div>
            </div>
            <ResultBlock title="Category & module" body={[result.category, result.module].filter(Boolean).join(" · ") || "Not specified"} />
            <ResultBlock title="Ticket understanding" body={result.problem || result.ticket || ticket} />
            <ResultBlock title="Detailed analysis" body={result.analysis} />
            <ResultBlock title="Historical evidence used by RAG" body={result.historical_evidence} />
            <ResultBlock title="Likely cause" body={result.likely_cause} />
            <ResultBlock title="Suggested resolution" body={result.suggested_resolution} />
            <ResultBlock title={`Confidence check · ${result.confidence_level || "Unrated"}`} body={result.confidence_reason} />
            <section className="result-block evidence-sources">
              <h3>Retrieved sources</h3>
              <h4>Historical tickets</h4>
              {result.retrieval_diagnostics?.ticket_sources?.length ? <ul>{result.retrieval_diagnostics.ticket_sources.map((item) => <li key={item.ticket_code}><b>{item.ticket_code}</b> · {item.module || "Module unknown"} · {item.category || "Category unknown"} <small>({(item.retrieved_by || []).join(" + ") || "retrieval source unknown"})</small></li>)}</ul> : <p>No historical tickets were retrieved for this query.</p>}
              <h4>Financial SOPs / policies</h4>
              {result.retrieval_diagnostics?.financial_document_sources?.length ? <ul>{result.retrieval_diagnostics.financial_document_sources.map((item) => <li key={item.document_code}><b>{item.document_code}</b> · {item.title} · {item.module || "Module unknown"}</li>)}</ul> : <p>No financial documents were retrieved for this query.</p>}
              <h4>Retrieval diagnostics</h4>
              <p>Keyword: {result.retrieval_diagnostics?.keyword_search || "unknown"} · Semantic: {result.retrieval_diagnostics?.semantic_search || "unknown"} · Financial documents: {result.retrieval_diagnostics?.financial_document_search || "unknown"}</p>
              {result.retrieval_diagnostics?.semantic_error && <p>Semantic retrieval error: {result.retrieval_diagnostics.semantic_error}</p>}
              {result.retrieval_diagnostics?.keyword_error && <p>Keyword retrieval error: {result.retrieval_diagnostics.keyword_error}</p>}
              {result.retrieval_diagnostics?.financial_document_error && <p>Document retrieval error: {result.retrieval_diagnostics.financial_document_error}</p>}
            </section>
            {result.missing_information?.length > 0 && <ResultBlock title="Information to collect" body={safeArray(result.missing_information).join(" · ")} />}
            <div className="modal-actions">
              <button type="button" className="button button-secondary" onClick={downloadReport}><Download size={16} /> Download report as PDF</button>
              <button type="button" className="button button-secondary" onClick={() => setResult(null)}>Close results</button>
            </div>
          </section>
        </div>,
        document.body
      )}
    </>
  );
}
