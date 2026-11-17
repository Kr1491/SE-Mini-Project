# Performance and Scalability Testing

## 1. Objective

The purpose of this testing is to verify that StudySpace remains responsive as the number of users and the amount of data increase.

The performance requirements are based on NFR-03 and NFR-05.

**Acceptance target:** Login, material opening, quiz loading, and quiz submission should each respond within 3 seconds (3000 ms) under normal conditions.

## 2. Test Environment

- Application: StudySpace
- Server: Local development server
- Server URL: `http://127.0.0.1:8003`
- Environment: Ubuntu on WSL
- Python version: 3.12
- Testing tool: Custom Python performance benchmarking script
- Database: Demo database with seeded sample data
- Network: Localhost
- Measurement unit: Milliseconds (ms)

The tests were performed using simulated concurrent requests.

## 3. Test Conditions

Four benchmark runs were performed:

| Test | Requests per operation | Concurrent users | Quiz size |
|---|---:|---:|---:|
| Initial test | 10 | 5 | 2 questions |
| Normal load | 20 | 1 | 2 questions |
| Increased concurrency | 30 | 10 | 2 questions |
| Increased quiz data | 30 | 10 | 50 questions |

The 50-question quiz was used to check how a larger quiz affects loading and submission performance. The material catalogue remained at its seeded demo-data size.

## 4. Performance Results

All values are recorded in milliseconds.

### Test 1 — Initial test

| Operation | Average | P95 | Maximum |
|---|---:|---:|---:|
| Login | 18.55 | 61.32 | 61.32 |
| Material opening | 12.34 | 61.36 | 61.36 |
| Quiz loading | 29.93 | 60.37 | 60.37 |
| Quiz submission | 25.62 | 49.86 | 49.86 |

### Test 2 — Normal load

| Operation | Average | P95 | Maximum |
|---|---:|---:|---:|
| Login | 9.58 | 13.65 | 19.07 |
| Material opening | 2.75 | 6.67 | 7.72 |
| Quiz loading | 8.91 | 12.97 | 21.78 |
| Quiz submission | 9.45 | 12.42 | 27.53 |

### Test 3 — Increased concurrency

| Operation | Average | P95 | Maximum |
|---|---:|---:|---:|
| Login | 82.22 | 458.25 | 561.19 |
| Material opening | 44.77 | 140.75 | 318.15 |
| Quiz loading | 103.10 | 571.22 | 592.09 |
| Quiz submission | 287.27 | 2346.70 | 2458.68 |

### Test 4 — Increased quiz data

| Operation | Average | P95 | Maximum |
|---|---:|---:|---:|
| Login | 56.46 | 147.28 | 253.28 |
| Material opening | 25.09 | 121.50 | 143.00 |
| Quiz loading | 123.04 | 491.76 | 494.69 |
| Quiz submission | 80.82 | 257.99 | 446.02 |

## 5. Observations

- All four operations remained within the 3000 ms response-time target across all four tests.
- Response times increased under higher concurrency compared with the normal-load test.
- Quiz submission had the highest P95 response time during the increased-concurrency test, at 2346.70 ms.
- With a 50-question quiz and 10 concurrent users, all operations continued to meet the response-time target.
- No performance bottleneck exceeding the specified response-time limit was observed during these tests.

## 6. Conclusion

The performance tests indicate that StudySpace meets the 3-second response-time requirement under the tested normal and increased-load conditions.

Login, material opening, quiz loading, and quiz submission all remained within the specified limit.

The application has therefore passed the performance checks covered by this test. Further testing with larger material datasets, more concurrent users, and a production-like environment would provide additional confidence in its scalability.

## 7. Limitations

These tests were conducted on a local development environment using simulated users and demo data. They do not represent a production deployment or establish the maximum number of users the application can support.

The results may vary depending on hardware, database size, network conditions, and server configuration.

## 8. Extended Load and Soak Testing (ISO 9126 Efficiency and Reliability)

Date: 17 November 2026. Environment: macOS 27.0, Apple M5 (10 cores, 16 GB), Python 3.14.4, demo server on `127.0.0.1` with a fresh demo database. Server memory (RSS) and CPU were sampled with `ps` every 0.2 s during each run. The benchmark now counts failed requests instead of stopping at the first one.

### 8.1 Defect found and fixed: connections reset under burst load

At 50 or more simultaneous users, some connections were reset before reaching the application. Python's `ThreadingHTTPServer` listens with a default backlog of 5 pending connections, so a burst of students connecting at once (for example, a class starting a quiz together) overflowed it. `server.py` now uses a `StudySpaceServer` subclass with a backlog of 128.

| Concurrent users | Requests | Errors before fix | Errors after fix |
|---:|---:|---:|---:|
| 50 | 600 | 8 (1.3%) | 0 |
| 100 | 1,200 | 34 (2.8%) | 0 |

### 8.2 Results after the fix (P95 / maximum, ms)

| Concurrent users | Login | Material opening | Quiz loading | Quiz submission | Errors | Peak server memory |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0.89 / 0.93 | 0.49 / 0.62 | 0.66 / 0.70 | 0.77 / 0.78 | 0 | 32.8 MiB |
| 10 | 23.19 / 40.52 | 4.75 / 5.17 | 30.97 / 42.68 | 11.89 / 13.35 | 0 | 34.8 MiB |
| 10 (50-question quiz) | 41.40 / 42.07 | 5.02 / 13.83 | 44.69 / 65.73 | 41.08 / 65.43 | 0 | 35.8 MiB |
| 50 | 153.65 / 211.83 | 29.58 / 55.52 | 257.17 / 474.33 | 203.35 / 468.56 | 0 | 48.4 MiB |
| 100 | 367.01 / 596.56 | 24.88 / 92.89 | 562.11 / 979.45 | 560.65 / 1085.14 | 0 | 62.0 MiB |
| 200 | 666.74 / 1191.37 | 24.51 / 72.50 | 1084.14 / 1734.01 | 1086.11 / 2231.09 | 0 | 83.4 MiB |

Requests per operation were three times the user count (for example, 300 at 100 users). Peak server CPU stayed at or below 15%.

### 8.3 Soak test

The 50-user benchmark was repeated continuously for 5 minutes: 124 runs and 74,400 requests with **0 errors** and no "Request failed" entries in the server log. Worst P95 values were login 374.93 ms, material opening 42.99 ms, quiz loading 435.34 ms and quiz submission 361.63 ms. Server memory peaked at 75.2 MiB in the first minute and was 52.5 MiB in the last minute, so no memory growth was observed.

### 8.4 Conclusion

Every operation stayed within the 3000 ms target, including the worst single request, at up to 200 concurrent users, with no failed requests after the backlog fix. These are local results on one machine; a production deployment should be measured separately.

Reproduce with a demo server running on port 8003:

```bash
python3 scripts/performance_benchmark.py --users 100 --requests 300 --output var/perf-100.json
```
