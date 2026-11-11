# Code Coverage Report

## 1. Overview

This report documents the statement coverage achieved by the automated Python test suite for StudySpace.

Coverage was measured using Coverage.py with branch tracking enabled.

## 2. Coverage Configuration

Command used:

`python3 -m coverage run --branch --source=server,study_platform -m unittest discover -s tests -p "test_*.py"`

The coverage scope includes:
- `server.py`
- Python modules inside `study_platform`

## 3. Coverage Results

| Metric | Result |
|---|---:|
| Total statements | 1,592 |
| Statements covered | 1,426 |
| Statements missed | 166 |
| Statement coverage | 89.6% |
| Overall Coverage.py coverage | 87% |

## 4. Interpretation

The automated Python tests exercised 1,426 out of 1,592 executable statements.

The remaining 166 statements were not executed during this test run. These may include error-handling paths, conditional logic, or functionality not reached by the current test cases.

## 5. Conclusion

The measured statement coverage was 89.6%. Further tests can be added to exercise currently uncovered statements and improve coverage.

These figures represent the local test execution and should not be interpreted as proof that all application functionality is defect-free.
