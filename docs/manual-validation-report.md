# StudySpace Manual Validation Report

**Date:** 11 November 2026  
**Environment:** Local development server  
**Mode:** Demo (`python3 server.py --demo --port 8003`)  
**Browser testing:** Completed through the local web interface

## 1. Objective

To manually validate the main StudySpace workflows for Student, Instructor, and Administrator roles using the provided demo accounts.

## 2. Student Workflow

| Test | Expected Result | Observed Result | Status |
|---|---|---|---|
| Open student dashboard | Dashboard loads with student-specific information | Dashboard loaded; groups and study partners displayed | PASS |
| Navigate to Study groups | Group listing opens | Both sample groups were displayed | PASS |
| View group membership | Membership and access information displayed | Both groups showed Member and Read access | PASS |
| Open material library | Authorized materials are displayed | Four resources were displayed | PASS |
| Download DOCX material | File downloads successfully | Download successful | PASS |
| Preview PDF material | PDF preview opens | Preview successful | PASS |
| Preview PNG material | Image preview opens | Preview successful | PASS |
| Preview Python source | Source code displays as text | Preview successful | PASS |
| Access without group membership | No group materials are visible | Student without groups saw zero materials | PASS |

## 3. Instructor Workflow

| Test | Expected Result | Observed Result | Status |
|---|---|---|---|
| Open instructor dashboard | Instructor dashboard loads | Dashboard loaded successfully | PASS |
| View teaching groups | Owned groups are displayed | Two owned groups were displayed | PASS |
| Open teaching workspace | Workspace opens | Workspace opened successfully | PASS |
| Open quiz creation workspace | Quiz creation interface loads | Workspace opened successfully | PASS |
| Create and publish quiz | Quiz can be published | Quiz creation and publishing worked | PASS |

## 4. Administrator Workflow

| Test | Expected Result | Observed Result | Status |
|---|---|---|---|
| Open administrator dashboard | Administrator dashboard loads | Dashboard loaded successfully | PASS |
| View system overview | Account, group and membership summaries appear | Summary information displayed | PASS |
| Open user management | Users and permissions page loads | Page loaded successfully | PASS |
| Open access checks | Access verification page loads | Page loaded successfully | PASS |
| Open material library | Administrator can access all demo resources | All five resources were visible | PASS |

## 5. Quiz Workflow

| Test | Expected Result | Observed Result | Status |
|---|---|---|---|
| View published quiz as student | Published quiz is visible | Quiz appeared for the student | PASS |
| Start quiz attempt | Student can begin an attempt | Worked successfully | PASS |
| Answer MCQs | Student can select answers | Worked successfully | PASS |
| Submit quiz | Submission and result are processed | Worked successfully | PASS |

## 6. Observations and Limitations

- Demo accounts and memberships are read-only fixtures. No role changes or membership modifications were attempted.
- The student account without group memberships could not see group materials.
- The administrator could see all five demo resources, while the student saw four.
- The initial material-library request returned HTTP 401. The clean `/materials` URL subsequently opened successfully.
- This validation was performed using the local demo environment. It does not establish production deployment or HTTPS behaviour.
- Only the workflows explicitly exercised during this session are marked PASS.

## 7. Conclusion

The tested Student, Instructor, and Administrator workflows operated as expected in the local demo environment.

Student material access restrictions, material previews and downloads, instructor quiz publishing, student quiz submission, and administrator workspace navigation were manually exercised successfully.

This report records observed manual validation and complements the automated unit, system, security, and coverage reports.
