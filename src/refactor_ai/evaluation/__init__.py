"""Evaluation of the A/B/C/D comparison (data and evaluation workstream).

protocol: arms, budgets, fixed generation settings and the test-split guard.
cases: dataset records as trusted ReferenceCase objects.
records: the case-level record written for every (case, arm) attempt.
harness: runs arms through the workflow coordinator and writes records.
report: tables and figures computed only from the retained records.
"""
