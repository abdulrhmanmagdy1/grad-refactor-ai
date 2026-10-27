# helpdesk

The IT helpdesk of a mid-sized office.

- `models.py`: tickets, comments, attachments and agents. Priorities run from
  CRITICAL (1, most urgent) to LOW (4). Status changes follow `TRANSITIONS`.
- `sla.py`: the service level targets. Each priority has a first-response target and
  a resolution target, both measured from the moment the ticket was created.
- `assignment.py`: a new ticket goes to an agent who has the ticket's category as a
  skill and spare capacity, the least loaded first. An agent's load is the number of
  unresolved tickets they hold; reassigning a ticket moves it from one agent's load to
  the other's.
- `escalation.py`: when a ticket has had no response from an agent by its response
  deadline, it is escalated: its priority goes up one level (towards CRITICAL) and its
  escalation count goes up by one.
- `attachments.py`: files attached to comments are kept in the uploads folder, one
  sub-folder per ticket. Users choose the file names.
- `report.py`: the weekly SLA report, per priority, and the list of open tickets past
  their resolution deadline per agent.
- `desk.py`: the service the web views call.
