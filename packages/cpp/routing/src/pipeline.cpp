#include "pipeline.h"

#include "catchment/catchment.h"
#include "heatmap/heatmap.h"
#include "matrix/matrix.h"

namespace routing
{

    std::string compute_catchment(RequestConfig const &cfg)
    {
        return catchment::compute(cfg);
    }

    void compute_travel_cost_matrix(MatrixConfig const &cfg)
    {
        matrix::compute(cfg);
    }

    void compute_heatmap(HeatmapConfig const &cfg)
    {
        heatmap::compute(cfg);
    }

    void compute_od_costs(HeatmapConfig const &cfg)
    {
        heatmap::compute_od_costs(cfg);
    }

} // namespace routing
