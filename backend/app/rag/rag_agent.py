from app.rag.context_builder import build_rag_context
from app.services.llm_service import generate_response


def run_rag(query: str, k: int = 5):

    context = build_rag_context(query=query, k=k)

    prompt = f"""
You are BugPilot, an AI assistant that helps analyze
software bugs and ERP tickets.

Use the historical tickets below to analyze the new ticket.

HISTORICAL TICKET CONTEXT:
{context}   

NEW TICKET:
{query}

Analyze the issue using the historical context.
Provide the analysis using the following clean format:

Likely Issue
Explain the main issue in 2-3 concise sentences.

Similar Historical Tickets
List the most relevant historical tickets.
For each ticket, provide:
Ticket Code - Module - Category
and one short sentence explaining why it is relevant.

Likely Cause
Explain the likely cause based only on the retrieved historical tickets.
If there are multiple possible causes, list them briefly.

Suggested Resolution
Provide the recommended resolution based on what was done in similar
historical tickets. Use short numbered steps.

Missing Information
List only the information that is actually needed for further
investigation.

Formatting rules:
- Do not use Markdown tables.
- Do not use bold text.
- Do not use asterisks for formatting.
- Do not use horizontal lines or long separator characters.
- Do not use excessive numbering.
- Keep each section short and readable.
- Use simple section headings.
- Use bullet points where appropriate.
- Leave a blank line between sections.
- Do not repeat the ticket description unnecessarily.
- Do not invent information that is not supported by the historical context.Give me good response with a good visibility.s
"""

    response = generate_response(prompt)

    return {"query": query, "context": context, "response": response}
