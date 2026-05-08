#pragma once

#include "../types.h"

#include <cstdint>
#include <string>
#include <vector>

namespace routing::output
{

// One marching-squares contour band, tagged by which origin (index into
// the request's starting points) produced it. Origin tagging is what
// makes shape_style=separated work — features from different origins can
// be kept distinct downstream.
struct TaggedFeature
{
    int32_t origin_idx;
    double step_cost;
    std::string multipolygon_wkt;
};

std::vector<double> compute_step_cutoffs(RequestConfig const &cfg);

// Build cost grid + jsolines for one reachability field, append the
// resulting bands (tagged with origin_idx) to `out`. The intermediate
// cost grid is freed before returning, so callers can stream this per
// origin without holding all grids in memory at once.
void append_field_grid_features(
    std::vector<TaggedFeature> &out,
    ReachabilityField const &field,
    int32_t origin_idx,
    int zoom,
    std::vector<double> const &cutoffs,
    RequestConfig const &cfg);

} // namespace routing::output
