#include "duckdb_setup.h"

#include <duckdb.hpp>
#include <stdexcept>

namespace routing::data
{

    void ensure_required_extensions_loaded(duckdb::Connection &con)
    {
        auto install_h3 = con.Query("INSTALL h3 FROM community");
        if (install_h3->HasError())
            throw std::runtime_error("Failed to install DuckDB H3 extension: " +
                                     install_h3->GetError());
        auto load_h3 = con.Query("LOAD h3");
        if (load_h3->HasError())
            throw std::runtime_error("Failed to load DuckDB H3 extension: " +
                                     load_h3->GetError());

        auto install_spatial = con.Query("INSTALL spatial");
        if (install_spatial->HasError())
            throw std::runtime_error("Failed to install DuckDB spatial extension: " +
                                     install_spatial->GetError());
        auto load_spatial = con.Query("LOAD spatial");
        if (load_spatial->HasError())
            throw std::runtime_error("Failed to load DuckDB spatial extension: " +
                                     load_spatial->GetError());
    }

} // namespace routing::data
