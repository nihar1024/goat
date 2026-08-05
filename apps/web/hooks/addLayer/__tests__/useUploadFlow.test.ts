import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

// The flow is headless, so it can be exercised without mounting a dialog — which
// is the point of the controller/host split, and impossible with the modal this
// replaces. Only the edges are mocked: the network, the store, and the parser.
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@/lib/api/datasets", () => ({ requestDatasetUpload: vi.fn() }));
vi.mock("@/lib/api/layers", () => ({ createLayer: vi.fn() }));
vi.mock("@/lib/api/processes", () => ({ useJobs: () => ({ mutate: vi.fn() }) }));
vi.mock("@/lib/api/projects", () => ({ useProject: () => ({ project: undefined }) }));
vi.mock("@/lib/services/s3", () => ({ uploadFileToS3: vi.fn() }));
vi.mock("@/lib/utils/tabular-preview", () => ({
  parseTabularPreview: () =>
    Promise.resolve({ headers: ["a"], rows: [["1"]], totalRows: 1, sheetNames: [] }),
}));
vi.mock("@/hooks/store/ContextHooks", () => ({
  useAppDispatch: () => vi.fn(),
  useAppSelector: () => [],
}));

const FOLDERS = [{ id: "folder-1", name: "Home" }];
vi.mock("@/lib/api/folders", () => ({
  useFolders: () => ({ folders: FOLDERS }),
  getWritableFolders: (folders: unknown) => folders,
}));

import { useUploadFlow } from "@/hooks/addLayer/useUploadFlow";

const file = (name: string) => new File(["x"], name, { type: "application/octet-stream" });

describe("useUploadFlow", () => {
  it("starts on the file step, blocked until a file is chosen", () => {
    const { result } = renderHook(() => useUploadFlow({}));
    expect(result.current.steps).toEqual([
      "select_file",
      "destination_and_metadata",
      "confirmation",
    ]);
    expect(result.current.step).toBe(0);
    expect(result.current.action).toMatchObject({ label: "next", disabled: true });

    act(() => result.current.upload.setFile(file("roads.geojson")));
    expect(result.current.action.disabled).toBe(false);
  });

  it("rejects a file type the backend cannot read, and keeps the step blocked", () => {
    const { result } = renderHook(() => useUploadFlow({}));
    act(() => result.current.upload.setFile(file("notes.txt")));
    expect(result.current.upload.file).toBeUndefined();
    expect(result.current.upload.fileError).toBeTruthy();
    expect(result.current.action.disabled).toBe(true);
  });

  it("adds a configuration step for tabular files only", () => {
    const { result } = renderHook(() => useUploadFlow({}));
    act(() => result.current.upload.setFile(file("table.csv")));
    expect(result.current.upload.isTabular).toBe(true);
    expect(result.current.steps).toEqual([
      "select_file",
      "preview_and_configure",
      "destination_and_metadata",
      "confirmation",
    ]);

    act(() => result.current.upload.setFile(file("roads.gpkg")));
    expect(result.current.upload.isTabular).toBe(false);
    expect(result.current.steps).toHaveLength(3);
  });

  it("suggests the file's own name, without its extension", () => {
    const { result } = renderHook(() => useUploadFlow({}));
    act(() => result.current.upload.setFile(file("Vienna trees.geojson")));
    expect(result.current.upload.suggestedName).toBe("Vienna trees");
  });

  it("blocks the metadata step until the form validates and a folder is chosen", async () => {
    const { result } = renderHook(() => useUploadFlow({}));
    act(() => result.current.upload.setFile(file("roads.geojson")));
    act(() => result.current.action.run());
    expect(result.current.step).toBe(1);
    // No name entered yet, so the form is invalid whatever the folder says.
    expect(result.current.action.disabled).toBe(true);
  });

  it("switches the primary action to upload on the last step", () => {
    const { result } = renderHook(() => useUploadFlow({}));
    act(() => result.current.upload.setFile(file("roads.geojson")));
    act(() => result.current.goTo(2));
    expect(result.current.action.label).toBe("upload");
  });

  it("resets everything, so a reopened host starts clean", () => {
    const { result } = renderHook(() => useUploadFlow({}));
    act(() => result.current.upload.setFile(file("roads.geojson")));
    act(() => result.current.goTo(2));
    act(() => result.current.reset());
    expect(result.current.step).toBe(0);
    expect(result.current.upload.file).toBeUndefined();
    expect(result.current.action).toMatchObject({ label: "next", disabled: true });
  });
});
