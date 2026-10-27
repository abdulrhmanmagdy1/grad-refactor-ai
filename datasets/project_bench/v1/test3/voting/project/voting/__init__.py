"""Election software for a members' club.

Eligible members receive a one-time voting token, cast a ranked ballot with it, and the
ballots are counted by instant runoff once the quorum is met. Every step is written to
a tamper-evident audit log and the result is exported to a results folder.
"""

__all__ = ["audit", "ballots", "counting", "election", "export", "quorum", "voters"]
