import { describe, expect, it } from "vitest";

import { MAX_EDITABLE_LAYER_SIZE } from "@/lib/constants";
import { canEditLayerFeatures } from "@/lib/utils/layerPermissions";

const USER = "user-1";
const PROJECT_OWNER = "project-owner-1";

describe("canEditLayerFeatures", () => {
  it("allows the layer owner to edit their own layer", () => {
    expect(
      canEditLayerFeatures({
        currentUserId: USER,
        layerOwnerId: USER,
        projectOwnerId: PROJECT_OWNER,
        isProjectEditor: true,
      })
    ).toBe(true);
  });

  it("allows a project editor to edit a layer owned by the project owner", () => {
    expect(
      canEditLayerFeatures({
        currentUserId: USER,
        layerOwnerId: PROJECT_OWNER,
        projectOwnerId: PROJECT_OWNER,
        isProjectEditor: true,
      })
    ).toBe(true);
  });

  it("denies a project viewer even on the project owner's layer", () => {
    expect(
      canEditLayerFeatures({
        currentUserId: USER,
        layerOwnerId: PROJECT_OWNER,
        projectOwnerId: PROJECT_OWNER,
        isProjectEditor: false,
      })
    ).toBe(false);
  });

  it("denies a project viewer even on their own layer", () => {
    expect(
      canEditLayerFeatures({
        currentUserId: USER,
        layerOwnerId: USER,
        projectOwnerId: PROJECT_OWNER,
        isProjectEditor: false,
      })
    ).toBe(false);
  });

  it("denies editing a layer owned by neither the user nor the project owner", () => {
    // The backend may still allow this (a third collaborator contributed the
    // layer); the client deliberately under-approximates rather than risk
    // showing an action that 403s.
    expect(
      canEditLayerFeatures({
        currentUserId: USER,
        layerOwnerId: "someone-else",
        projectOwnerId: PROJECT_OWNER,
        isProjectEditor: true,
      })
    ).toBe(false);
  });

  it("denies editing when the layer exceeds the editable size limit", () => {
    expect(
      canEditLayerFeatures({
        currentUserId: USER,
        layerOwnerId: USER,
        projectOwnerId: PROJECT_OWNER,
        isProjectEditor: true,
        layerSize: MAX_EDITABLE_LAYER_SIZE + 1,
      })
    ).toBe(false);
  });

  it("allows editing at exactly the editable size limit", () => {
    expect(
      canEditLayerFeatures({
        currentUserId: USER,
        layerOwnerId: USER,
        projectOwnerId: PROJECT_OWNER,
        isProjectEditor: true,
        layerSize: MAX_EDITABLE_LAYER_SIZE,
      })
    ).toBe(true);
  });

  it("denies editing catalog layers", () => {
    expect(
      canEditLayerFeatures({
        currentUserId: USER,
        layerOwnerId: USER,
        projectOwnerId: PROJECT_OWNER,
        isProjectEditor: true,
        inCatalog: true,
      })
    ).toBe(false);
  });

  it("denies editing when the current user is not resolved yet", () => {
    expect(
      canEditLayerFeatures({
        currentUserId: undefined,
        layerOwnerId: USER,
        projectOwnerId: PROJECT_OWNER,
        isProjectEditor: true,
      })
    ).toBe(false);
  });

  it("falls back to ownership when the project owner is unknown", () => {
    expect(
      canEditLayerFeatures({
        currentUserId: USER,
        layerOwnerId: USER,
        projectOwnerId: undefined,
        isProjectEditor: true,
      })
    ).toBe(true);
    expect(
      canEditLayerFeatures({
        currentUserId: USER,
        layerOwnerId: "someone-else",
        projectOwnerId: undefined,
        isProjectEditor: true,
      })
    ).toBe(false);
  });
});
