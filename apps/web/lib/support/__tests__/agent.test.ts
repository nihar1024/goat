import { describe, expect, it } from "vitest";

import { supportReplyAgent } from "../agent";

const ticket = (o: object) => ({
  latest_message_is_agent: true,
  latest_message_author: "Jonas",
  agent_name: "Lena",
  ...o,
});

describe("supportReplyAgent", () => {
  it("names the agent who wrote the latest message", () => {
    expect(supportReplyAgent(ticket({}), "GOAT team")).toBe("Jonas");
  });

  it("falls back to the handler, then the team", () => {
    expect(supportReplyAgent(ticket({ latest_message_author: null }), "GOAT team")).toBe("Lena");
    expect(supportReplyAgent(ticket({ latest_message_is_agent: false }), "GOAT team")).toBe("Lena");
    expect(supportReplyAgent(ticket({ latest_message_author: null, agent_name: null }), "GOAT team")).toBe(
      "GOAT team"
    );
  });
});
