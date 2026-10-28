/**
 * The line of what is selected below a direction — a path between two
 * stops, or the pattern of the trip shown — handed from the selection
 * resolver, which reads it from the snapshot, to the map's layers, which sit
 * outside the Explorer's data (as the highlight store hands the picked
 * patterns' sections).
 */
import type { LineString } from "geojson";

let current: LineString[] | null = null;
const listeners = new Set<() => void>();

export const selectionStore = {
  subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  getSnapshot(): LineString[] | null {
    return current;
  },
  set(next: LineString[] | null): void {
    current = next;
    listeners.forEach((l) => l());
  },
};
