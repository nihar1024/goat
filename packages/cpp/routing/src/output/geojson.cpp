#include "geojson.h"

#include "hexagon_builder.h"
#include "network_builder.h"
#include "polygon_builder.h"

#include <duckdb.hpp>
#include <sstream>
#include <stdexcept>
#include <string>

namespace routing::output
{

namespace
{
std::string empty_feature_collection()
{
    return "{\"type\":\"FeatureCollection\",\"features\":[]}";
}

std::string run_single_value_query(duckdb::Connection &con,
                                   std::string const &sql,
                                   std::string const &error_prefix)
{
    auto result = con.Query(sql);
    if (result->HasError())
    {
        throw std::runtime_error(error_prefix + result->GetError());
    }
    if (result->RowCount() == 0 || result->GetValue(0, 0).IsNull())
    {
        return empty_feature_collection();
    }
    return result->GetValue(0, 0).GetValue<std::string>();
}

std::string build_network_geojson(duckdb::Connection &con)
{
    std::ostringstream sql;
    sql << "SELECT CAST(json_object("
        << "  'type', 'FeatureCollection', "
        << "  'features', COALESCE(json_group_array(feature), CAST('[]' AS JSON))"
        << ") AS VARCHAR) "
        << "FROM ("
        << "  SELECT json_object("
        << "    'type', 'Feature', "
        << "    'geometry', CAST(ST_AsGeoJSON(geometry) AS JSON), "
        << "    'properties', json_object('step_cost', step_cost)"
        << "  ) AS feature "
        << "  FROM " << network_features_table_name() << " "
        << "  ORDER BY edge_id"
        << ") t";
    return run_single_value_query(con, sql.str(), "Network GeoJSON export failed: ");
}

std::string build_hexagon_geojson(duckdb::Connection &con)
{
    std::ostringstream sql;
    sql << "SELECT CAST(json_object("
        << "  'type', 'FeatureCollection', "
        << "  'features', COALESCE(json_group_array(feature), CAST('[]' AS JSON))"
        << ") AS VARCHAR) "
        << "FROM ("
        << "  SELECT json_object("
        << "    'type', 'Feature', "
        << "    'geometry', CAST(ST_AsGeoJSON(geometry) AS JSON), "
        << "    'properties', json_object("
        << "      'h3', h3_h3_to_string(cell), "
        << "      'resolution', resolution, "
        << "      'cost', min_cost, "
        << "      'step_cost', step_cost"
        << "    )"
        << "  ) AS feature "
        << "  FROM " << hexagon_features_table_name() << " "
        << "  ORDER BY h3_h3_to_string(cell)"
        << ") t";
    return run_single_value_query(con, sql.str(), "Hexagon GeoJSON export failed: ");
}

std::string build_polygon_geojson(duckdb::Connection &con)
{
    std::ostringstream sql;
    sql << "SELECT CAST(json_object("
        << "  'type', 'FeatureCollection', "
        << "  'features', COALESCE(json_group_array(feature), CAST('[]' AS JSON))"
        << ") AS VARCHAR) "
        << "FROM ("
        << "  SELECT json_object("
        << "    'type', 'Feature', "
        << "    'geometry', CAST(ST_AsGeoJSON(geometry) AS JSON), "
        << "    'properties', json_object('step_cost', step_cost)"
        << "  ) AS feature "
        << "  FROM " << polygon_features_table_name() << " "
        << "  ORDER BY step_cost"
        << ") t";
    return run_single_value_query(con, sql.str(), "Polygon GeoJSON export failed: ");
}

} // namespace

std::string build_geojson_output(ReachabilityField const &field,
                                 RequestConfig const &cfg,
                                 duckdb::Connection &con)
{
    switch (cfg.catchment_type)
    {
    case CatchmentType::Network:
    {
        auto const feature_count = materialize_network_features_table(field, cfg, con);
        if (feature_count == 0)
        {
            return empty_feature_collection();
        }
        return build_network_geojson(con);
    }
    case CatchmentType::Polygon:
    {
        auto const feature_count = materialize_polygon_features_table(field, cfg, con);
        if (feature_count == 0)
        {
            return empty_feature_collection();
        }
        return build_polygon_geojson(con);
    }
    case CatchmentType::HexagonalGrid:
    {
        auto const feature_count = materialize_hexagon_features_table(field, cfg, con);
        if (feature_count == 0)
        {
            return empty_feature_collection();
        }
        return build_hexagon_geojson(con);
    }
    default:
        return empty_feature_collection();
    }
}

} // namespace routing::output
