#pragma once

#include "../types.h"

#include <string>

namespace routing::catchment
{

    // Catchment-area orchestration: build the reachability field for
    // cfg.starting_points (street Dijkstra or PT RAPTOR) and emit it in the
    // requested catchment_type / shape_style. Returns a GeoJSON string for
    // GeoJSON output, or writes parquet to cfg.output_path and returns "".
    std::string compute(RequestConfig const &cfg);

} // namespace routing::catchment
