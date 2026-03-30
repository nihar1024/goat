#include "request_config.h"

namespace routing::input
{

    static constexpr double kCarBufferSpeedKmH = 80.0;

    std::vector<std::string> valid_classes(RoutingMode mode)
    {
        switch (mode)
        {
        case RoutingMode::Walking:
            return {"primary", "secondary", "tertiary", "residential",
                    "living_street", "trunk", "unclassified", "service",
                    "pedestrian", "footway", "steps", "path",
                    "track", "cycleway", "bridleway", "unknown"};
        case RoutingMode::Bicycle:
        case RoutingMode::Pedelec:
            return {"primary", "secondary", "tertiary", "residential",
                    "living_street", "trunk", "unclassified", "service",
                    "pedestrian", "footway", "path", "track",
                    "cycleway", "bridleway", "unknown"};
        case RoutingMode::Car:
            return {"motorway", "primary", "secondary", "tertiary",
                    "residential", "living_street", "trunk", "unclassified",
                    "service", "track"};
        case RoutingMode::PublicTransport:
            // Access/egress legs are on foot
            return {"primary", "secondary", "tertiary", "residential",
                    "living_street", "trunk", "unclassified", "service",
                    "pedestrian", "footway", "steps", "path",
                    "track", "cycleway", "bridleway", "unknown"};
        }
        return {};
    }

    double buffer_distance(RequestConfig const &cfg)
    {
        if (cfg.cost_mode == CostMode::Time)
        {
            double speed_km_h;
            if (cfg.mode == RoutingMode::Car)
                speed_km_h = kCarBufferSpeedKmH;
            else if (cfg.mode == RoutingMode::PublicTransport)
                speed_km_h = cfg.speed_km_h;  // walk speed only — transit range irrelevant
            else
                speed_km_h = cfg.speed_km_h;
            return cfg.max_traveltime * (speed_km_h * 1000.0 / 60.0);
        }
        return cfg.max_traveltime; // distance mode: value is already in meters
    }

} // namespace routing::input
