
"""StudySpace performance benchmark for Issue #22.

Run against a local demo server:
    python scripts/performance_benchmark.py --requests 10 --users 5
"""
import argparse
import concurrent.futures
import json
import platform
import statistics
import time
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path


class Client:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.cookies = CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )
        self.csrf = None

    def request(self, method, path, data=None):
        body = None if data is None else json.dumps(data).encode()
        headers = {"Content-Type": "application/json"}
        if self.csrf:
            headers["X-CSRF-Token"] = self.csrf

        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=headers,
            method=method,
        )

        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read()
                status = response.status
        except urllib.error.HTTPError as error:
            raw = error.read()
            raise RuntimeError(
                f"{method} {path}: HTTP {error.code}: "
                f"{raw.decode(errors='replace')}"
            ) from error

        if not raw:
            return status, None

        content_type = response.headers.get("Content-Type", "")
        if "application/json" in content_type:
            return status, json.loads(raw)
        return status, raw

    def login(self, user_id=2):
        status, result = self.request(
            "POST", "/api/demo/session", {"user_id": user_id}
        )
        assert status == 200
        self.csrf = result["csrf_token"]


def percentile(values, percent):
    ordered = sorted(values)
    index = round((percent / 100) * (len(ordered) - 1))
    return ordered[index]


def measure(action, requests, users):
    """Measure an action with independent authenticated clients."""
    def one_request(_):
        client = Client(BASE_URL)

        if action == "login":
            start = time.perf_counter()
            client.login()
        else:
            client.login()

            if action == "material opening":
                start = time.perf_counter()
                client.request("GET", f"/api/materials/{MATERIAL_ID}/view")

            elif action == "quiz loading":
                start = time.perf_counter()
                client.request(
                    "POST", f"/api/quizzes/{QUIZ_ID}/attempts"
                )

            elif action == "quiz submission":
                _, attempt = client.request(
                    "POST", f"/api/quizzes/{QUIZ_ID}/attempts"
                )
                answers = [
                    {
                        "question_id": question["id"],
                        "option_id": question["options"][0]["id"],
                    }
                    for question in attempt["quiz"]["questions"]
                ]
                start = time.perf_counter()
                client.request(
                    "POST",
                    f"/api/quiz-attempts/{attempt['attempt_id']}/submit",
                    {"answers": answers},
                )

        return (time.perf_counter() - start) * 1000

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=users
    ) as executor:
        return list(executor.map(one_request, range(requests)))


def prepare():
    """Create a benchmark quiz and find a seeded public material."""
    instructor = Client(BASE_URL)
    instructor.login(user_id=1)

    quiz_data = {
        "title": "Performance Benchmark Quiz",
        "questions": [
            {
                "question": f"Benchmark question {i + 1}: What does SQL stand for?",
                "options": [
                    {"text": "Structured Query Language", "is_correct": True},
                    {"text": "Simple Question Language", "is_correct": False},
                    {"text": "System Query Logic", "is_correct": False},
                    {"text": "Standard Question List", "is_correct": False},
                ],
            }
            for i in range(QUIZ_QUESTIONS)
        ],
    }

    status, created = instructor.request(
        "POST", "/api/groups/1/quizzes", quiz_data
    )
    assert status == 201
    quiz_id = created["quiz"]["id"]

    status, _ = instructor.request(
        "POST", f"/api/quizzes/{quiz_id}/publish"
    )
    assert status == 200

    student = Client(BASE_URL)
    student.login(user_id=2)
    status, catalog = student.request("GET", "/api/materials")

    assert status == 200
    materials = catalog.get("materials", [])
    if not materials:
        raise RuntimeError("No accessible demo material was found.")

    return quiz_id, materials[0]["id"]


def main():
    global BASE_URL, QUIZ_ID, MATERIAL_ID, QUIZ_QUESTIONS

    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8003")
    parser.add_argument("--requests", type=int, default=10)
    parser.add_argument("--users", type=int, default=5)
    parser.add_argument("--quiz-questions", type=int, default=2)
    args = parser.parse_args()

    if args.requests < 1 or args.users < 1 or args.quiz_questions < 1:
        parser.error("All numeric arguments must be positive.")

    BASE_URL = args.url
    QUIZ_QUESTIONS = args.quiz_questions
    print("Preparing demo data...")
    QUIZ_ID, MATERIAL_ID = prepare()

    actions = [
        "login",
        "material opening",
        "quiz loading",
        "quiz submission",
    ]

    results = {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "requests_per_action": args.requests,
            "concurrent_users": args.users,
            "server": BASE_URL,
        },
        "measurements": {},
    }

    print("\nStudySpace Performance Results")
    print("=" * 72)
    print(f"{'Operation':<22} {'Average':>10} {'Median':>10} {'P95':>10} {'Max':>10}")
    print("-" * 72)

    for action in actions:
        timings = measure(action, args.requests, args.users)
        summary = {
            "average_ms": round(statistics.mean(timings), 2),
            "median_ms": round(statistics.median(timings), 2),
            "p95_ms": round(percentile(timings, 95), 2),
            "max_ms": round(max(timings), 2),
            "samples": len(timings),
        }
        results["measurements"][action] = summary

        print(
            f"{action:<22} "
            f"{summary['average_ms']:>9.2f} "
            f"{summary['median_ms']:>9.2f} "
            f"{summary['p95_ms']:>9.2f} "
            f"{summary['max_ms']:>9.2f}"
        )

    output = Path("performance-results.json")
    output.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("=" * 72)
    print(f"\nResults saved to: {output.resolve()}")
    print("Target: each operation should respond within 3000 ms.")


if __name__ == "__main__":
    main()