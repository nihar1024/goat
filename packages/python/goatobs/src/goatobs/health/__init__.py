"""Dependency health: the framework, not the probes.

Runs a set of checks on a timer and reports each as a gauge. Knows nothing
about object storage or databases — the probes live in goatlib, where the
clients already are, so this package keeps its dependencies to OpenTelemetry
and the standard library.

Probing happens in ONE prober rather than in every pod: shared
infrastructure asked ten times tells you nothing that asking once does. It
is also deliberately kept out of readiness probes — if object storage goes
down and every pod marks itself unready, Kubernetes pulls the whole service
out of the load balancer, turning a degraded service into a total outage.
"""

from goatobs.health.prober import Prober
from goatobs.health.runner import Check, CheckResult, run_all, run_check

__all__ = ["Check", "CheckResult", "Prober", "run_all", "run_check"]
