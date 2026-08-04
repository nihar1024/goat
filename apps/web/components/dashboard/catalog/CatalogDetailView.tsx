"use client";

import { Container, Skeleton, Stack, Typography } from "@mui/material";
import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";

import type { CatalogCollection, CatalogItem } from "@/lib/validations/catalog";

import CatalogBundleDetail from "@/components/dashboard/catalog/CatalogBundleDetail";
import CatalogLayerDetail from "@/components/dashboard/catalog/CatalogLayerDetail";

/**
 * Detail view for one catalog entry, dispatching on what the id turned out to
 * be: a bundle (`/stac/resolve` says `collection`) or a single dataset.
 *
 * Nothing here reads core. A catalog entry is not a GOAT layer until a project
 * adds it (promote-on-use), so the promoted-layer components — `DatasetSummary`,
 * `DatasetTable`, `DatasetMapPreview` — would render empty rather than wrong:
 * they page rows through `useLayerFields(layer_id)` and draw the layer's tiles,
 * neither of which exists for a catalog dataset. `/datasets/[datasetId]` remains
 * the page for promoted layers.
 */

type Props = {
  entryId: string;
  collection?: CatalogCollection;
  members?: CatalogItem[];
  item?: CatalogItem;
  parent?: CatalogCollection;
  isLoading: boolean;
  isError?: boolean;
};

const CatalogDetailView = ({
  collection,
  members = [],
  item,
  parent,
  isLoading,
  isError,
}: Props) => {
  const router = useRouter();
  const { t } = useTranslation("common");

  /**
   * Saved datasets, in memory until core has somewhere to keep them.
   *
   * Favourites are user-scoped and the design puts the control on every card and
   * both detail headers, so the interaction is wired up now and persisted later.
   * The consequence is honest: a star does not survive a reload.
   */
  const [starred, setStarred] = useState<Record<string, boolean>>({});
  const toggleStar = useCallback(
    (target: CatalogItem) =>
      setStarred((prev) => ({ ...prev, [target.id]: !prev[target.id] })),
    []
  );
  const toggleAll = useCallback((targets: CatalogItem[], save: boolean) => {
    setStarred((prev) => {
      const next = { ...prev };
      for (const target of targets) next[target.id] = save;
      return next;
    });
  }, []);

  // A bundle member came from its bundle, so back belongs to the bundle rather
  // than to whatever the browser remembers.
  const parentIsBundle = (parent?.["goat:member_count"] ?? 1) > 1;

  /**
   * The one layer of a single-layer dataset, if that is what this id resolved to.
   *
   * Read from `members` rather than `goat:member_count`: the count is what the
   * mirror recorded, and this has to be the layer actually in hand to render.
   */
  const singleLayer =
    collection && (collection["goat:member_count"] ?? members.length) === 1
      ? members[0]
      : undefined;

  /**
   * Back to the list, with the search that produced it intact.
   *
   * `router.back()` rather than `push("/catalog")`, because the catalog keeps all
   * of its state in the query string: pushing the bare path throws away the
   * filters, the page, the spatial filter and the sort the user had set. Going
   * back restores that URL exactly, and also restores scroll position.
   *
   * The fallback matters for a link opened in a new tab or pasted in fresh, where
   * there is nothing to go back to — `history.length` of 1 means this entry is the
   * whole session, and a plain push is then the only sensible destination.
   */
  const backToList = useCallback(() => {
    if (typeof window !== "undefined" && window.history.length > 1) {
      router.back();
      return;
    }
    router.push("/catalog");
  }, [router]);

  return (
    <Container sx={{ py: 10, px: { xs: 4, sm: 10 } }} maxWidth="xl">
      {isLoading && (
        <Stack spacing={4}>
          <Skeleton variant="text" width={120} />
          <Skeleton variant="text" width="60%" height={44} />
          <Skeleton variant="rectangular" width="100%" height={420} />
        </Stack>
      )}

      {!isLoading && isError && (
        <Typography variant="body2" color="error">
          {t("catalog_entry_not_found")}
        </Typography>
      )}

      {/* A dataset with ONE layer is that layer. The list navigates by collection
          id (a card stands for a dataset), so without this a Feature card opened a
          page titled "BUNDLE" offering "Save all" for a bundle of one. `resolve`
          already returns the member, so this costs no extra request. */}
      {!isLoading && !isError && collection && singleLayer && (
        <CatalogLayerDetail
          item={singleLayer}
          collection={collection}
          onBack={backToList}
          starred={!!starred[singleLayer.id]}
          onToggleStar={() => toggleStar(singleLayer)}
        />
      )}

      {!isLoading && !isError && collection && !singleLayer && (
        <CatalogBundleDetail
          collection={collection}
          members={members}
          onBack={backToList}
          onOpenMember={(member) => router.push(`/catalog/${encodeURIComponent(member.id)}`)}
          starred={starred}
          onToggleStar={toggleStar}
          onToggleAll={toggleAll}
        />
      )}

      {!isLoading && !isError && item && (
        <CatalogLayerDetail
          item={item}
          collection={parent}
          onBack={() =>
            // A member goes up to its bundle; anything else goes back to the list
            // it came from, filters and all.
            //
            // `replace`, not `push`: the member is *inside* the bundle, so going
            // up should not deepen the history. Pushing left the bundle sitting on
            // top of the member, and the bundle's own Back — a `router.back()`,
            // which is what preserves the list's filters — returned to the member
            // it had just come from instead of to the list.
            parentIsBundle && parent
              ? router.replace(`/catalog/${encodeURIComponent(parent.id)}`)
              : backToList()
          }
          backLabel={parentIsBundle ? (parent?.title || undefined) : undefined}
          starred={!!starred[item.id]}
          onToggleStar={() => toggleStar(item)}
        />
      )}
    </Container>
  );
};

export default CatalogDetailView;
