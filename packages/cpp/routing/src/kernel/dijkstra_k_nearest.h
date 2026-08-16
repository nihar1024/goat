#pragma once

#include "../types.h"

#include <algorithm>
#include <cstdint>
#include <queue>
#include <tuple>
#include <vector>

namespace routing::kernel
{

// ---------------------------------------------------------------------------
// k-nearest multi-source Dijkstra
// ---------------------------------------------------------------------------
//
// One traversal that yields, per node, the k cheapest costs to k *distinct*
// source groups — a group being a set of seed nodes that count as one origin
// (e.g. all nodes an opportunity snapped to). Replaces running one Dijkstra per
// group when the consumer only needs each node's k nearest (ClosestAverage),
// turning O(groups) traversals into roughly O(k).
//
// Pruning rule: a label (v, g) is dropped when v already holds k labels all
// cheaper than it. That is safe for the per-cell k-smallest that ClosestAverage
// computes from node samples — if k groups are strictly closer than g at v, each
// of them also has a cell cost no greater than its cost at v, so k groups
// already beat g in v's cell.
//
// It is NOT sufficient for samples interpolated along an edge: those need the
// cost of the same group at *both* endpoints, and pruning can discard one side.
// Callers must treat edge-interpolated coverage as approximate and validate
// against the per-group path.

struct KNearestScratch
{
    // Labels are stored in a flat node-major array of stride k, kept sorted
    // ascending by cost within each node. `count[v]` is how many are live.
    std::vector<double> cost;
    std::vector<std::int32_t> group;
    std::vector<std::uint8_t> count;
    std::vector<std::uint32_t> gen;  // gen[v]==cur ⟺ count[v] valid this run
    std::uint32_t cur = 0u;
    std::int32_t k = 1;

    KNearestScratch(std::size_t node_count, std::int32_t k_)
        : cost(node_count * static_cast<std::size_t>(k_)),
          group(node_count * static_cast<std::size_t>(k_)),
          count(node_count, 0u),
          gen(node_count, 0u),
          k(k_)
    {
    }

    void begin()
    {
        if (++cur == 0u)
        {
            std::fill(gen.begin(), gen.end(), 0u);
            cur = 1u;
        }
    }

    bool reached(std::int32_t v) const { return gen[v] == cur; }

    std::int32_t n_labels(std::int32_t v) const
    {
        return reached(v) ? static_cast<std::int32_t>(count[v]) : 0;
    }

    std::size_t base(std::int32_t v) const
    {
        return static_cast<std::size_t>(v) * static_cast<std::size_t>(k);
    }

    // Insert (g, c) into v's label set, keeping it sorted and at most k long.
    // Returns true if the set changed, i.e. the caller should relax from v.
    bool offer(std::int32_t v, std::int32_t g, double c)
    {
        if (!reached(v))
        {
            gen[v] = cur;
            count[v] = 0u;
        }
        std::size_t const b = base(v);
        std::int32_t n = static_cast<std::int32_t>(count[v]);

        // Already have this group: keep the cheaper, re-sort if improved.
        for (std::int32_t i = 0; i < n; ++i)
        {
            if (group[b + i] != g) continue;
            if (cost[b + i] <= c) return false;
            // Improved: remove then re-insert so the array stays sorted.
            for (std::int32_t j = i; j + 1 < n; ++j)
            {
                cost[b + j] = cost[b + j + 1];
                group[b + j] = group[b + j + 1];
            }
            --n;
            count[v] = static_cast<std::uint8_t>(n);
            break;
        }

        if (n == k && c >= cost[b + n - 1]) return false;  // worse than worst

        std::int32_t pos = n;
        while (pos > 0 && cost[b + pos - 1] > c)
        {
            if (pos < k)
            {
                cost[b + pos] = cost[b + pos - 1];
                group[b + pos] = group[b + pos - 1];
            }
            --pos;
        }
        if (pos < k)
        {
            cost[b + pos] = c;
            group[b + pos] = g;
            if (n < k) count[v] = static_cast<std::uint8_t>(n + 1);
        }
        return true;
    }

    // Cost of group `g` at v, or a negative sentinel when v holds no label for
    // it (pruned or unreached).
    double cost_of(std::int32_t v, std::int32_t g) const
    {
        if (!reached(v)) return -1.0;
        std::size_t const b = base(v);
        std::int32_t const n = static_cast<std::int32_t>(count[v]);
        for (std::int32_t i = 0; i < n; ++i)
            if (group[b + i] == g) return cost[b + i];
        return -1.0;
    }
};

// A network node together with the source group it belongs to.
struct DijkstraSource
{
    std::int32_t node;
    std::int32_t group;
};

// Run the traversal. Returns every node that ended up with at least one label,
// in no particular order; read each node's labels via the scratch.
inline std::vector<std::int32_t>
dijkstra_k_nearest(std::vector<std::vector<AdjEntry>> const &adj,
                   std::vector<DijkstraSource> const &sources,
                   double travel_budget, bool use_distance,
                   KNearestScratch &scratch)
{
    scratch.begin();
    std::vector<std::int32_t> labelled;
    if (sources.empty()) return labelled;

    // (cost, node, group); greater<> turns the heap into a min-heap.
    using PQEntry = std::tuple<double, std::int32_t, std::int32_t>;
    std::priority_queue<PQEntry, std::vector<PQEntry>, std::greater<>> pq;

    for (auto const &src : sources)
    {
        if (src.node < 0 || src.node >= static_cast<std::int32_t>(adj.size()))
            continue;
        bool const was_unreached = !scratch.reached(src.node);
        if (scratch.offer(src.node, src.group, 0.0))
        {
            if (was_unreached) labelled.push_back(src.node);
            pq.push({0.0, src.node, src.group});
        }
    }

    while (!pq.empty())
    {
        auto [d, u, g] = pq.top();
        pq.pop();
        // Stale entry: this label was improved (or evicted) after being queued.
        double const held = scratch.cost_of(u, g);
        if (held < 0.0 || held < d) continue;

        for (auto const &e : adj[u])
        {
            // Same unit convention as dijkstra_reached: adjacency costs are
            // seconds, so a time budget needs them in minutes.
            double const edge_cost = use_distance ? e.cost : (e.cost / 60.0);
            double const new_cost = d + edge_cost;
            if (new_cost > travel_budget) continue;
            bool const was_unreached = !scratch.reached(e.target);
            if (scratch.offer(e.target, g, new_cost))
            {
                if (was_unreached) labelled.push_back(e.target);
                pq.push({new_cost, e.target, g});
            }
        }
    }
    return labelled;
}

} // namespace routing::kernel
