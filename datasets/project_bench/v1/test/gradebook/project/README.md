# gradebook

The grade book used by the school office and its teachers.

- `models`: students, courses with weighted assessments, and final course results.
- `grading`: weighted course percentages and letter grades (A from 90, B from 80, C from
  70, D from 60, F below), plus the quiz average that drops the lowest quiz.
- `service`: the term's grade book. Only a course's instructor may record, change or
  publish its grades.
- `gpa`: credit-weighted GPA on a 4-point scale (W and P results do not count), and
  academic standing.
- `transcript`: a student's results by term as a printable transcript.
- `importer`: loads score sheets exported from the spreadsheet; the same sheet is never
  imported twice.

Run the tests with `python -m pytest`.
