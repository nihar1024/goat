#pragma once

namespace duckdb
{
    class Connection;
}

namespace routing::data
{

    // Install + load the DuckDB extensions every pipeline relies on: the h3
    // community extension and spatial. Idempotent; throws on failure.
    void ensure_required_extensions_loaded(duckdb::Connection &con);

} // namespace routing::data
