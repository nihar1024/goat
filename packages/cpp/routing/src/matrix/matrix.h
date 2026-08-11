#pragma once

#include "../types.h"

namespace routing::matrix
{

    // Many-to-many travel-cost matrix between cfg.origins and cfg.destinations:
    // street Dijkstra (forward, or reverse on the transposed graph) or
    // per-origin PT. Writes a parquet of (origin, destination, travel_cost) to
    // cfg.output_path. Reverse PT is rejected here (use compute_od_costs).
    void compute(MatrixConfig const &cfg);

} // namespace routing::matrix
