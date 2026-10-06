/** `/support/new`, carrying the page the user came from so the ticket can name it. */
export const newTicketPath = (from?: string | null): string =>
  from ? `/support/new?from=${encodeURIComponent(from)}` : "/support/new";

/** `/support/<ref>`, the page of one ticket. */
export const supportTicketPath = (ref: string): string => `/support/${encodeURIComponent(ref)}`;
