import { describe, expect, it } from "vitest";

import { customBasemapSchema } from "@/lib/validations/project";

const baseFields = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "My basemap",
  description: null,
  thumbnail_url: null,
  created_at: "2026-04-30T00:00:00Z",
  updated_at: "2026-04-30T00:00:00Z",
};

describe("customBasemapSchema", () => {
  it("accepts a valid vector basemap", () => {
    const parsed = customBasemapSchema.parse({
      ...baseFields,
      type: "vector",
      url: "https://example.com/style.json",
    });
    expect(parsed.type).toBe("vector");
  });

  it("rejects an invalid vector URL", () => {
    expect(() =>
      customBasemapSchema.parse({
        ...baseFields,
        type: "vector",
        url: "not-a-url",
      })
    ).toThrow();
  });

  it("accepts a raster basemap with placeholders", () => {
    const parsed = customBasemapSchema.parse({
      ...baseFields,
      type: "raster",
      url: "https://example.com/{z}/{x}/{y}.png",
      attribution: "© Example",
    });
    expect(parsed.type).toBe("raster");
  });

  it("rejects raster URLs missing placeholders", () => {
    expect(() =>
      customBasemapSchema.parse({
        ...baseFields,
        type: "raster",
        url: "https://example.com/{z}/{x}.png",
      })
    ).toThrow();
  });

  it("accepts a solid color in #rrggbb form", () => {
    const parsed = customBasemapSchema.parse({
      ...baseFields,
      type: "solid",
      color: "#ff8800",
    });
    expect(parsed.type).toBe("solid");
  });

  it("accepts a solid color in #rrggbbaa form", () => {
    const parsed = customBasemapSchema.parse({
      ...baseFields,
      type: "solid",
      color: "#ff8800cc",
    });
    expect(parsed.type).toBe("solid");
  });

  it("rejects an invalid color", () => {
    expect(() =>
      customBasemapSchema.parse({
        ...baseFields,
        type: "solid",
        color: "orange",
      })
    ).toThrow();
  });

  it("rejects an unknown type", () => {
    expect(() =>
      customBasemapSchema.parse({
        ...baseFields,
        type: "wmts",
        url: "https://example.com",
      })
    ).toThrow();
  });

  it("rejects raster URL with non-http scheme", () => {
    expect(() =>
      customBasemapSchema.parse({
        ...baseFields,
        type: "raster",
        url: "ftp://example.com/{z}/{x}/{y}.png",
      })
    ).toThrow();
  });

  it("rejects raster URL missing scheme", () => {
    expect(() =>
      customBasemapSchema.parse({
        ...baseFields,
        type: "raster",
        url: "/{z}/{x}/{y}.png",
      })
    ).toThrow();
  });

  it("rejects non-ISO created_at strings", () => {
    expect(() =>
      customBasemapSchema.parse({
        ...baseFields,
        created_at: "yesterday",
        type: "vector",
        url: "https://example.com/style.json",
      })
    ).toThrow();
  });
});
