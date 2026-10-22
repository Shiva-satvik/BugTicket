export function safeArray(value) { return Array.isArray(value) ? value : []; }
export function objectOrEmpty(value) { return value && typeof value === "object" && !Array.isArray(value) ? value : {}; }
export function fmt(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return value.toLocaleString();
  return String(value).replaceAll("_", " ");
}
export function getTicketId(ticket) { return ticket?.ticket_id ?? ticket?.id ?? ticket?.ticket_code ?? "—"; }
export function getTicketTitle(ticket) { return ticket?.title ?? ticket?.summary ?? ticket?.ticket ?? ticket?.description ?? "Untitled ticket"; }
export function getStatus(ticket) { return String(ticket?.status ?? ticket?.state ?? "OPEN").toUpperCase().replaceAll(" ", "_"); }
export function getUserName(user) { return user?.full_name || user?.username || user?.email || "BugPilot user"; }
export function initials(name) { return String(name || "BP").split(/\s+/).filter(Boolean).slice(0,2).map(x => x[0].toUpperCase()).join("") || "BP"; }
export function firstName(name) { return String(name || "").trim().split(/\s+/)[0] || "there"; }
export function firstDefined(obj, keys) { for (const key of keys) if (obj?.[key] !== undefined && obj?.[key] !== null) return obj[key]; return undefined; }

/* ------------------------------------------------------------
   Suggested resolution — normalizer.
   The AI can return the resolution as a JSON-like list string
   (e.g. '[1.1, "Inspect ...", 1.2, "Review ..."]'), a real array,
   newline-separated numbered steps, or plain prose. These helpers
   turn every shape into clean numbered steps for display/PDF.
------------------------------------------------------------ */
function resolutionRawText(value) {
  let raw = Array.isArray(value) ? value.map((item) => String(item)).join("\n") : String(value);
  raw = raw.trim();
  // Strip a wrapping JSON-like [ ... ] shell if the model returned one.
  const shell = raw.match(/^\[\s*([\s\S]*)\s*\]$/);
  if (shell) raw = shell[1].trim();
  return raw;
}

export function parseResolutionSteps(value) {
  if (value === null || value === undefined) return [];
  const raw = resolutionRawText(value);
  if (!raw) return [];

  // Step markers such as 1.1 / 2.3 that begin a new step.
  const markerRe = /(?:^|[\[,;"'\n]\s*|\s(?=["']))(\d{1,2}\.\d{1,2})\s*[,:\-)]?\s*/g;
  const marks = [...raw.matchAll(markerRe)];
  if (!marks.length) return [];

  const steps = [];
  for (let index = 0; index < marks.length; index += 1) {
    const start = marks[index].index + marks[index][0].length;
    const end = index + 1 < marks.length ? marks[index + 1].index : raw.length;
    const body = raw
      .slice(start, end)
      .trim()
      .replace(/^[,:\-)\s]+/, "")
      .replace(/^["“']|["”']$/g, "")
      .replace(/[\s,]+$/, "")
      .trim();
    if (body) steps.push({ step: marks[index][1], body });
  }
  return steps;
}

export function formatResolutionSteps(value) {
  const steps = parseResolutionSteps(value);
  if (steps.length) return steps.map((item) => `${item.step}  ${item.body}`).join("\n");
  if (value === null || value === undefined) return "";
  return resolutionRawText(value);
}
