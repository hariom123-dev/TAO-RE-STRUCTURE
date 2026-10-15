"""
Prometheus & Grafana OpenMetrics Exporter for TAO Oversight Gateway.
Emits Prometheus-compliant telemetry text format (version 0.0.4) with zero external dependencies.

Tracks:
- tao_requests_total (by tier)
- tao_latency_ms (histogram buckets & sum)
- tao_caselaw_cache_hits_total / misses
- tao_usd_savings_total (by source)
- tao_stego_alerts_total & cusum alerts
- tao_tool_calls_blocked_total
- tao_prompt_injections_blocked_total
- tao_active_constitutional_principles (gauge)
- tao_defensive_success_rate (gauge)
"""

import threading
import time
from typing import Optional


class PrometheusExporter:
    """Thread-safe telemetry aggregator and Prometheus metrics generator."""

    LATENCY_BUCKETS = [20.0, 50.0, 100.0, 250.0, 500.0, 1000.0, 2500.0, 5000.0]

    def __init__(self):
        self._lock = threading.Lock()
        self._requests_total: dict[str, int] = {
            "tier_minus_1": 0,
            "tier_0": 0,
            "tier_1": 0,
            "tier_2": 0,
            "tier_3": 0,
        }
        self._latency_bucket_counts: dict[float, int] = {b: 0 for b in self.LATENCY_BUCKETS}
        self._latency_inf_count: int = 0
        self._latency_sum_ms: float = 0.0
        self._latency_count: int = 0

        self._cache_hits: int = 0
        self._cache_misses: int = 0
        self._usd_saved_cache: float = 0.0
        self._usd_saved_routing: float = 0.0

        self._stego_alerts: int = 0
        self._cusum_alerts: int = 0
        self._tool_blocks: int = 0
        self._injection_blocks: int = 0

        self._active_principles_count: int = 12
        self._defensive_success_rate: float = 100.0

    def record_request(self, tier_label: str, latency_ms: float):
        with self._lock:
            key = tier_label.lower().replace("-", "_")
            self._requests_total[key] = self._requests_total.get(key, 0) + 1

            self._latency_count += 1
            self._latency_sum_ms += latency_ms
            self._latency_inf_count += 1
            for b in self.LATENCY_BUCKETS:
                if latency_ms <= b:
                    self._latency_bucket_counts[b] += 1

    def record_cache_hit(self, tokens_saved: int = 2800, usd_saved: float = 0.042):
        with self._lock:
            self._cache_hits += 1
            self._usd_saved_cache += usd_saved

    def record_cache_miss(self):
        with self._lock:
            self._cache_misses += 1

    def record_usd_savings(self, routing_usd: float = 0.0, cache_usd: float = 0.0):
        with self._lock:
            self._usd_saved_routing += routing_usd
            self._usd_saved_cache += cache_usd

    def record_stego_alert(self, is_cusum: bool = False):
        with self._lock:
            if is_cusum:
                self._cusum_alerts += 1
            else:
                self._stego_alerts += 1

    def record_tool_block(self):
        with self._lock:
            self._tool_blocks += 1

    def record_prompt_injection_block(self):
        with self._lock:
            self._injection_blocks += 1
            self._requests_total["tier_minus_1"] += 1

    def set_active_principles(self, count: int):
        with self._lock:
            self._active_principles_count = count

    def set_defensive_success_rate(self, rate_percent: float):
        with self._lock:
            self._defensive_success_rate = round(rate_percent, 2)

    def export_metrics(self) -> str:
        """Render Prometheus exposition format v0.0.4."""
        lines = []
        with self._lock:
            # 1. Total Requests
            lines.append("# HELP tao_requests_total Total number of queries processed by TAO oversight tiers")
            lines.append("# TYPE tao_requests_total counter")
            for tier, count in self._requests_total.items():
                lines.append(f'tao_requests_total{{tier="{tier}"}} {count}')

            # 2. Latency Histogram
            lines.append("# HELP tao_request_duration_ms Latency of TAO pipeline evaluation in milliseconds")
            lines.append("# TYPE tao_request_duration_ms histogram")
            for b in self.LATENCY_BUCKETS:
                lines.append(f'tao_request_duration_ms_bucket{{le="{b}"}} {self._latency_bucket_counts[b]}')
            lines.append(f'tao_request_duration_ms_bucket{{le="+Inf"}} {self._latency_inf_count}')
            lines.append(f"tao_request_duration_ms_sum {round(self._latency_sum_ms, 2)}")
            lines.append(f"tao_request_duration_ms_count {self._latency_count}")

            # 3. Case Law Cache Hits/Misses
            lines.append("# HELP tao_caselaw_cache_hits_total Number of queries resolved via Case Law vector precedent")
            lines.append("# TYPE tao_caselaw_cache_hits_total counter")
            lines.append(f"tao_caselaw_cache_hits_total {self._cache_hits}")
            lines.append("# HELP tao_caselaw_cache_misses_total Number of queries that required fresh Tier 2 debate")
            lines.append("# TYPE tao_caselaw_cache_misses_total counter")
            lines.append(f"tao_caselaw_cache_misses_total {self._cache_misses}")

            # 4. USD Cost Savings
            lines.append("# HELP tao_usd_savings_total Estimated USD saved by cache hits and low-tier routing")
            lines.append("# TYPE tao_usd_savings_total counter")
            lines.append(f'tao_usd_savings_total{{source="cache"}} {round(self._usd_saved_cache, 4)}')
            lines.append(f'tao_usd_savings_total{{source="routing"}} {round(self._usd_saved_routing, 4)}')

            # 5. Security Alerts
            lines.append("# HELP tao_stego_alerts_total Statistical steganography and KL divergence alerts triggered")
            lines.append("# TYPE tao_stego_alerts_total counter")
            lines.append(f"tao_stego_alerts_total {self._stego_alerts}")
            lines.append("# HELP tao_cusum_drift_alerts_total Sustained multi-turn KL drift alerts triggered")
            lines.append("# TYPE tao_cusum_drift_alerts_total counter")
            lines.append(f"tao_cusum_drift_alerts_total {self._cusum_alerts}")

            # 6. Intercepted Attacks
            lines.append("# HELP tao_tool_calls_blocked_total Destructive Bash, SQL, or AST tool calls halted by firewall")
            lines.append("# TYPE tao_tool_calls_blocked_total counter")
            lines.append(f"tao_tool_calls_blocked_total {self._tool_blocks}")
            lines.append("# HELP tao_prompt_injections_blocked_total Prompt injections and jailbreaks blocked at Tier -1")
            lines.append("# TYPE tao_prompt_injections_blocked_total counter")
            lines.append(f"tao_prompt_injections_blocked_total {self._injection_blocks}")

            # 7. Gauges
            lines.append("# HELP tao_active_constitutional_principles Active safety principles loaded in Tier 1")
            lines.append("# TYPE tao_active_constitutional_principles gauge")
            lines.append(f"tao_active_constitutional_principles {self._active_principles_count}")

            lines.append("# HELP tao_defensive_success_rate Percentage of adversarial red-team attacks successfully intercepted")
            lines.append("# TYPE tao_defensive_success_rate gauge")
            lines.append(f"tao_defensive_success_rate {self._defensive_success_rate}")

        return "\n".join(lines) + "\n"


prometheus_exporter = PrometheusExporter()
