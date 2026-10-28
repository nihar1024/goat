// @vitest-environment node

/**
 * Paths between two stops, on the mini feed: T1 runs First → Fifth along
 * SH1, stops 0.01° (about 677 m) apart at 52.5° N; T3 runs back on the line
 * through its stops (it has no shape).
 */
import { beforeAll, describe, expect, it } from "vitest";

import { openFixtureDb } from "@/lib/explorer/__tests__/fixtureDb";
import type { SqlRunner } from "@/lib/explorer/db/types";
import { pathAt, tripPattern } from "@/lib/explorer/derive/path";

let db: SqlRunner;
const pattern = async (trip_id: string) =>
  (await tripPattern(
    db,
    (await db.all<{ trip_idx: number }>(`SELECT trip_idx FROM trips WHERE trip_id = '${trip_id}'`))[0]
      .trip_idx
  )) as number;

beforeAll(async () => {
  db = await openFixtureDb();
});

describe("a path between two stops", () => {
  it("is the stretch around the click", async () => {
    const p = await pathAt(db, await pattern("T1"), 13.416, 52.5004);
    // Between Second (13.41) and Third (13.42); stops count from 0.
    expect(p).toMatchObject({ from_i: 1, to_i: 2, from_name: "Second", to_name: "Third" });
    // Its line runs from the one stop to the other.
    expect(p?.line[0][0]).toBeCloseTo(13.41, 3);
    expect(p?.line.at(-1)?.[0]).toBeCloseTo(13.42, 3);
  });

  it("is the first or last stretch for a click beyond the ends", async () => {
    const p = await pattern("T1");
    expect(await pathAt(db, p, 13.3, 52.5)).toMatchObject({ from_i: 0, to_i: 1 });
    expect(await pathAt(db, p, 13.6, 52.5)).toMatchObject({ from_i: 3, to_i: 4, to_name: "Fifth" });
  });

  it("follows a trip without a shape along the line through its stops", async () => {
    const p = await pathAt(db, await pattern("T3"), 13.435, 52.5);
    expect(p).toMatchObject({ from_name: "Fifth", to_name: "Fourth" });
  });
});
