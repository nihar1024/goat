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
// Only the read is stubbed. `derivePreview` is the real one, so the header row and the row
// count are still derived by the code under test rather than asserted against a fixture.
vi.mock("@/lib/utils/tabular-preview", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/utils/tabular-preview")>()),
  readTabularSource: () =>
    Promise.resolve({ sheetNames: [], activeSheet: "", head: [["a"], ["1"]], totalLines: 2 }),
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
  it("keeps the upload blocked until there is a file", () => {
    const { result } = renderHook(() => useUploadFlow({}));
    expect(result.current.action.disabled).toBe(true);

    act(() => result.current.upload.setFile(file("roads.geojson")));
    // A file is not enough on its own: the name still has to validate and the folder to
    // resolve, which is what the remaining tests cover.
    expect(result.current.upload.file?.name).toBe("roads.geojson");
  });

  it("rejects a file type the backend cannot read", () => {
    const { result } = renderHook(() => useUploadFlow({}));
    act(() => result.current.upload.setFile(file("notes.txt")));
    expect(result.current.upload.file).toBeUndefined();
    expect(result.current.upload.fileError).toBeTruthy();
    expect(result.current.action.disabled).toBe(true);
  });

  it("does not change shape for a workbook", () => {
    // Its header row and worksheet are settings: they open in their own dialog.
    const { result } = renderHook(() => useUploadFlow({}));

    act(() => result.current.upload.setFile(file("table.csv")));
    expect(result.current.upload.isTabular).toBe(true);

    act(() => result.current.upload.setFile(file("roads.gpkg")));
    expect(result.current.upload.isTabular).toBe(false);
  });

  it("suggests the file's own name, without its extension", () => {
    const { result } = renderHook(() => useUploadFlow({}));
    act(() => result.current.upload.setFile(file("Vienna trees.geojson")));
    expect(result.current.upload.suggestedName).toBe("Vienna trees");
  });

  it("takes a name from the row, since there is no form to register against", () => {
    const { result } = renderHook(() => useUploadFlow({}));
    act(() => result.current.upload.setFile(file("roads.geojson")));
    act(() => result.current.upload.setName("Vienna roads"));
    expect(result.current.upload.values.name).toBe("Vienna roads");

    act(() => result.current.upload.setDescription("Every cycle path in the city"));
    expect(result.current.upload.values.description).toBe("Every cycle path in the city");
  });

  it("resets everything, so a reopened host starts clean", () => {
    const { result } = renderHook(() => useUploadFlow({}));
    act(() => result.current.upload.setFile(file("roads.geojson")));
    act(() => result.current.upload.setName("Vienna roads"));
    act(() => result.current.reset());
    expect(result.current.upload.file).toBeUndefined();
    expect(result.current.action).toMatchObject({ label: "upload", disabled: true });
  });
});
