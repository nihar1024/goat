import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PropertiesPanel from "@/components/map/panels/properties/Properties";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("@/i18n/utils", () => ({ useDateFnsLocale: () => undefined }));

const CATALOG_ITEM = {
  id: "da6143c8-519a-4f10-8095-b87c8f34ce74",
  publisher: "Landesamt für Umwelt (LfU)",
  updated: "2026-08-16T10:55:42Z",
};

const layer = (other_properties?: unknown) =>
  ({
    id: 1,
    layer_id: "layer-1",
    updated_at: "2026-08-28T18:50:55Z",
    other_properties,
  }) as never;

describe("PropertiesPanel", () => {
  it("says a catalog layer came from the catalog, and links back to its entry", () => {
    render(<PropertiesPanel activeLayer={layer({ catalog_item: CATALOG_ITEM })} />);

    expect(screen.getByText("source")).toBeDefined();
    expect(screen.getByRole("link", { name: "catalog_open_entry" }).getAttribute("href")).toBe(
      `/catalog/${CATALOG_ITEM.id}`
    );
  });

  it("says nothing about a source for an ordinary layer", () => {
    render(<PropertiesPanel activeLayer={layer({})} />);

    expect(screen.queryByText("source")).toBeNull();
  });

  it("has no link when the snapshot predates the id being kept", () => {
    render(<PropertiesPanel activeLayer={layer({ catalog_materialize: { status: "ready" } })} />);

    expect(screen.getByText("source")).toBeDefined();
    expect(screen.queryByRole("link")).toBeNull();
  });
});
