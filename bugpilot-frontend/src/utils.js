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
