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