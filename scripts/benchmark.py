import asyncio
import time
import os
import sys
import json
import httpx
from loguru import logger
import statistics

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def time_endpoint(client, url, payload, headers):
    start = time.perf_counter()
    try:
        res = await client.post(url, json=payload, headers=headers)
        res.raise_for_status()
    except Exception as e:
        pass # Ignore errors in simple benchmarking
    return time.perf_counter() - start

async def benchmark_latencies():
    logger.info("Benchmarking latencies...")
    base_url = "http://localhost:8001/api/v1"
    headers = {"Authorization": "Bearer MOCK_TOKEN"} # Requires auth disabled or valid token
    
    results = {}
    
    async with httpx.AsyncClient() as client:
        # We simulate the payload
        endpoints = {
            "search_deep": (f"{base_url}/search/deep", {"email": "test@example.com"}),
            "recommendations": (f"{base_url}/recommendations", {"context": {"message": "movies"}}),
            "reviews_generate": (f"{base_url}/reviews/generate", {"product_id": "test_id"})
        }
        
        for name, (url, payload) in endpoints.items():
            latencies = []
            for _ in range(10):
                lat = await time_endpoint(client, url, payload, headers)
                latencies.append(lat * 1000) # ms
                
            latencies.sort()
            results[name] = {
                "p50_ms": round(statistics.median(latencies), 2),
                "p95_ms": round(latencies[int(len(latencies)*0.95)], 2),
                "p99_ms": round(latencies[int(len(latencies)*0.99)], 2),
            }
            logger.info(f"Endpoint {name} -> p50: {results[name]['p50_ms']}ms")
            
    return results

async def benchmark_throughput():
    logger.info("Benchmarking throughput...")
    base_url = "http://localhost:8001/api/v1/recommendations"
    headers = {"Authorization": "Bearer MOCK_TOKEN"}
    payload = {"context": {"message": "movies"}}
    
    async with httpx.AsyncClient() as client:
        tasks = [client.post(base_url, json=payload, headers=headers) for _ in range(50)]
        start = time.perf_counter()
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        total_time = time.perf_counter() - start
        
        success_count = sum(1 for r in responses if not isinstance(r, Exception) and r.status_code == 200)
        
        req_sec = round(50 / total_time, 2)
        logger.info(f"Throughput: {req_sec} req/sec ({success_count}/50 successes)")
        
        return {
            "concurrent_requests": 50,
            "success_rate": f"{success_count}/50",
            "req_per_sec": req_sec,
            "avg_latency_ms": round((total_time / 50) * 1000, 2)
        }

async def run_benchmarks():
    os.makedirs("docs", exist_ok=True)
    latencies = await benchmark_latencies()
    throughput = await benchmark_throughput()
    
    metrics = {
        "latencies": latencies,
        "throughput": throughput,
        "hardware_notes": "System handles X req/sec on Y hardware (Fill before submission)"
    }
    
    with open("docs/performance_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)
        
    logger.info("Saved metrics to docs/performance_metrics.json")

if __name__ == "__main__":
    asyncio.run(run_benchmarks())
