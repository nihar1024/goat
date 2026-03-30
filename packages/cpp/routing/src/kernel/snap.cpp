#include "snap.h"
#include "kdtree.h"

#include <cmath>
#include <cstdint>
#include <limits>
#include <memory>
#include <vector>

namespace routing::kernel
{

    static constexpr double kCarConnectorSpeedKmH = 80.0 * 0.7;
    static constexpr size_t kKdTreeOriginThreshold = 64;

    static std::pair<int32_t, double> find_nearest_node_linear(
        std::vector<Point3857> const &points,
        size_t point_count,
        Point3857 const &origin)
    {
        if (point_count == 0)
            return {-1, std::numeric_limits<double>::infinity()};

        int32_t best_node = -1;
        double best_d2 = std::numeric_limits<double>::infinity();
        for (int32_t i = 0; i < static_cast<int32_t>(point_count); ++i)
        {
            double d2 = sq_dist(origin, points[i]);
            if (d2 < best_d2)
            {
                best_d2 = d2;
                best_node = i;
            }
        }
        return {best_node, std::sqrt(best_d2)};
    }

    static double connector_cost(double origin_dist,
                                 RequestConfig const &cfg)
    {
        if (cfg.cost_mode == CostMode::Distance)
            return origin_dist;

        double speed_km_h = cfg.speed_km_h;
        if (cfg.mode == RoutingMode::Car)
            speed_km_h = (cfg.speed_km_h > 0.0) ? cfg.speed_km_h
                                                 : kCarConnectorSpeedKmH;

        double speed_m_s = speed_km_h / 3.6;
        if (speed_m_s <= 0.0)
            speed_m_s = kCarConnectorSpeedKmH / 3.6;

        return origin_dist / speed_m_s;
    }

    std::vector<int32_t> snap_origins(SubNetwork &net,
                                      std::vector<Point3857> const &origins,
                                      RequestConfig const &cfg)
    {
        std::vector<int32_t> start_nodes;
        start_nodes.reserve(origins.size());

        if (net.node_coords.empty())
        {
            start_nodes.assign(origins.size(), -1);
            return start_nodes;
        }

        size_t base_node_count = net.node_coords.size();
        net.node_coords.reserve(net.node_coords.size() + origins.size());

        bool use_kdtree = origins.size() >= kKdTreeOriginThreshold;
        std::unique_ptr<KdTree2D> node_tree;
        if (use_kdtree)
            node_tree = std::make_unique<KdTree2D>(net.node_coords);

        for (auto const &origin : origins)
        {
            std::pair<int32_t, double> nearest;
            if (use_kdtree)
                nearest = node_tree->nearest(origin);
            else
                nearest = find_nearest_node_linear(
                    net.node_coords, base_node_count, origin);

            auto [nearest_node, nearest_dist] = nearest;
            if (nearest_node < 0 ||
                nearest_dist == std::numeric_limits<double>::infinity())
            {
                start_nodes.push_back(-1);
                continue;
            }

            int32_t origin_node = net.node_count++;
            net.node_coords.push_back(origin);

            double connector = connector_cost(nearest_dist, cfg);
            net.source.push_back(origin_node);
            net.target.push_back(nearest_node);
            net.cost.push_back(connector);
            net.reverse_cost.push_back(connector);
            net.length_3857.push_back(nearest_dist);
            net.geom.address.push_back(0);

            start_nodes.push_back(origin_node);
        }
        return start_nodes;
    }

} // namespace routing::kernel
