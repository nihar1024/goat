import type { SupportTicket } from "@/lib/validations/support";

/** Who the "needs your reply" banner names: the agent who wrote the latest message, else the handler, else the team. */
export const supportReplyAgent = (
  ticket: Pick<SupportTicket, "latest_message_is_agent" | "latest_message_author" | "agent_name">,
  teamName: string
): string =>
  (ticket.latest_message_is_agent ? ticket.latest_message_author : null) ?? ticket.agent_name ?? teamName;
