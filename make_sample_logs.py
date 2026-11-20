"""
make_sample_logs.py
-------------------
Creates SIMULATED logs (no real data) for demos and tests.
Run:  python make_sample_logs.py
"""

import random
from datetime import datetime, timedelta

random.seed(42)  # same output every time, so tests are repeatable


def stamp(base, seconds):
    return (base + timedelta(seconds=seconds)).strftime("%Y-%m-%d %H:%M:%S,") + f"{random.randint(0, 999):03d}"


def write(filename, lines):
    lines = sorted(lines)  # lines start with a timestamp, so sorting puts them in time order
    with open(f"sample_logs/{filename}", "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote sample_logs/{filename} ({len(lines)} lines)")


# ---------- 1) The example from the assignment: payment timeouts + database failures ----------
def payment_and_database_incident():
    t0 = datetime(2026, 11, 18, 10, 0, 0)
    L = []
    for s in range(0, 600, 120):
        L.append(f"{stamp(t0, s)} INFO  [payment-service] Payment processed order=ORD-{random.randint(1000, 9999)} amount=1499")
    L.append(f"{stamp(t0, 650)} WARN  [db-proxy] Connection pool usage at 85% (43/50)")
    L.append(f"{stamp(t0, 700)} WARN  [db-proxy] Connection pool usage at 96% (48/50)")
    L.append(f"{stamp(t0, 730)} WARN  [monitoring] Disk usage at 78% on /var/log")
    L.append(f"{stamp(t0, 760)} ERROR [db-proxy] Connection pool exhausted: 50/50 connections active, 12 requests waiting")
    for i in range(6):
        order = random.randint(1000, 9999)
        L.append(f"{stamp(t0, 770 + i * 9)} ERROR [order-service] Failed to save order=ORD-{order}: could not acquire DB connection after 5000ms")
    for i in range(8):
        order = random.randint(1000, 9999)
        L.append(f"{stamp(t0, 800 + i * 11)} ERROR [payment-service] Payment API timeout after {30000 + random.randint(0, 90)}ms calling gateway order=ORD-{order}")
        if i % 2 == 0:
            L.append(f"{stamp(t0, 801 + i * 11)} WARN  [payment-service] Retry {1 + i % 3}/3 for order=ORD-{order}")
    L.append(f"{stamp(t0, 900)} ERROR [payment-service] Database connection failure: SQLException: Connection is not available, request timed out")
    L.append(f"{stamp(t0, 905)} ERROR [payment-service] Database connection failure: SQLException: Connection is not available, request timed out")
    L.append(f"{stamp(t0, 910)} WARN  [api-gateway] Deprecated endpoint /v1/cart called by client=mobile-app")
    L.append(f"{stamp(t0, 930)} ERROR [api-gateway] Upstream payment-service responded 503 Service Unavailable")
    L.append(f"{stamp(t0, 945)} ERROR [payment-service] Customer email=ravi.k@example.com payment failed, token=abc123secret")
    for s in range(960, 1080, 40):
        L.append(f"{stamp(t0, s)} INFO  [health-check] payment-service health check failed (attempt {(s - 960) // 40 + 1})")
    write("payment_and_database_incident.log", L)


# ---------- 2) A memory leak that ends in a crash (expect Critical because of FATAL) ----------
def memory_leak_crash():
    t0 = datetime(2026, 11, 18, 14, 0, 0)
    L = []
    for i, pct in enumerate([55, 63, 71, 79, 86, 92]):
        level = "INFO " if pct < 80 else "WARN "
        L.append(f"{stamp(t0, i * 300)} {level} [report-service] Heap memory usage at {pct}%")
    for i in range(4):
        L.append(f"{stamp(t0, 1800 + i * 20)} ERROR [report-service] java.lang.OutOfMemoryError: Java heap space while generating report id={random.randint(100, 999)}")
    L.append(f"{stamp(t0, 1900)} FATAL [report-service] JVM terminated due to OutOfMemoryError, restarting")
    L.append(f"{stamp(t0, 1930)} INFO  [report-service] Service restarted successfully")
    write("memory_leak_crash.log", L)


# ---------- 3) Mostly healthy: few isolated problems (expect Low) ----------
def mostly_healthy():
    t0 = datetime(2026, 11, 18, 9, 0, 0)
    L = []
    for i in range(12):
        L.append(f"{stamp(t0, i * 60)} INFO  [catalog-service] Served product list in {random.randint(40, 120)}ms")
    L.append(f"{stamp(t0, 400)} WARN  [catalog-service] Cache miss rate higher than usual")
    L.append(f"{stamp(t0, 500)} ERROR [catalog-service] Image resize failed for product=SKU-{random.randint(100, 999)}: unsupported format")
    for i in range(6):
        L.append(f"{stamp(t0, 800 + i * 60)} INFO  [catalog-service] Served product list in {random.randint(40, 120)}ms")
    write("mostly_healthy.log", L)


if __name__ == "__main__":
    payment_and_database_incident()
    memory_leak_crash()
    mostly_healthy()
