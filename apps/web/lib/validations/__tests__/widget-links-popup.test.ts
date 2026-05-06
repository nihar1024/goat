import { describe, expect, it } from "vitest";

import { linksItemSchema } from "@/lib/validations/widget";

describe("linksItemSchema — per-link popup options", () => {
  it("applies default popup_type='popover' when fields are omitted", () => {
    const result = linksItemSchema.safeParse({ label: "X" });
    expect(result.success).toBe(true);
    if (!result.success) return;
    expect(result.data.popup_type).toBe("popover");
  });

  it("applies default popup_placement='auto' when fields are omitted", () => {
    const result = linksItemSchema.safeParse({ label: "X" });
    expect(result.success).toBe(true);
    if (!result.success) return;
    expect(result.data.popup_placement).toBe("auto");
  });

  it("applies default popup_size='md' when fields are omitted", () => {
    const result = linksItemSchema.safeParse({ label: "X" });
    expect(result.success).toBe(true);
    if (!result.success) return;
    expect(result.data.popup_size).toBe("md");
  });

  it("accepts all valid popup_type values", () => {
    for (const t of ["tooltip", "popover", "dialog"] as const) {
      const result = linksItemSchema.safeParse({ label: "X", popup_type: t });
      expect(result.success, `popup_type=${t} should parse`).toBe(true);
    }
  });

  it("accepts all valid popup_placement values", () => {
    for (const p of ["top", "bottom", "left", "right", "auto"] as const) {
      const result = linksItemSchema.safeParse({ label: "X", popup_placement: p });
      expect(result.success, `popup_placement=${p} should parse`).toBe(true);
    }
  });

  it("accepts all valid popup_size values", () => {
    for (const s of ["sm", "md", "lg"] as const) {
      const result = linksItemSchema.safeParse({ label: "X", popup_size: s });
      expect(result.success, `popup_size=${s} should parse`).toBe(true);
    }
  });

  it("rejects invalid popup_type", () => {
    const result = linksItemSchema.safeParse({ label: "X", popup_type: "modal" });
    expect(result.success).toBe(false);
  });

  it("rejects invalid popup_size", () => {
    const result = linksItemSchema.safeParse({ label: "X", popup_size: "huge" });
    expect(result.success).toBe(false);
  });
});
