"""Who works on which ticket: matching by skill and balancing the load."""

from __future__ import annotations

from collections.abc import Iterable

from helpdesk.models import Agent, Ticket


class AssignmentBoard:
    """The support agents and how many unresolved tickets each one holds."""

    def __init__(self, agents: Iterable[Agent]) -> None:
        self._agents: dict[str, Agent] = {}
        for agent in agents:
            if agent.username in self._agents:
                raise ValueError(f"duplicate agent: {agent.username}")
            self._agents[agent.username] = agent

    def agent(self, username: str) -> Agent:
        """Return the agent called ``username``; an unknown name raises ``KeyError``."""
        return self._agents[username]

    def pick(self, category: str) -> Agent | None:
        """The agent to take a ticket of ``category``.

        Only agents with the skill and spare capacity qualify; among them the one
        with the fewest open tickets wins, ties going to the earlier username.
        Returns None when nobody qualifies.
        """
        candidates = [a for a in self._agents.values() if category in a.skills and a.has_capacity]
        if not candidates:
            return None
        return min(candidates, key=lambda a: (a.open_tickets, a.username))

    def _check_can_take(self, agent: Agent, ticket: Ticket) -> None:
        if ticket.category not in agent.skills:
            raise ValueError(f"{agent.username} does not handle {ticket.category} tickets")
        if not agent.has_capacity:
            raise ValueError(f"{agent.username} already holds {agent.open_tickets} tickets")

    def assign(self, ticket: Ticket, username: str) -> None:
        """Give an unassigned ticket to an agent; it counts towards their load."""
        if ticket.assignee is not None:
            raise ValueError(f"ticket {ticket.id} is already assigned to {ticket.assignee}")
        agent = self.agent(username)
        self._check_can_take(agent, ticket)
        ticket.assignee = agent.username
        agent.open_tickets += 1

    def reassign(self, ticket: Ticket, username: str) -> None:
        """Move an assigned ticket to another agent.

        The ticket now counts towards the new agent's load instead of the
        previous agent's.
        """
        if ticket.assignee is None:
            raise ValueError(f"ticket {ticket.id} is not assigned yet")
        if ticket.assignee == username:
            return
        new_agent = self.agent(username)
        self._check_can_take(new_agent, ticket)
        self.release(ticket)
        ticket.assignee = new_agent.username
        new_agent.open_tickets += 1

    def release(self, ticket: Ticket) -> None:
        """Stop counting a resolved ticket towards its agent's load."""
        if ticket.assignee is None:
            return
        agent = self.agent(ticket.assignee)
        agent.open_tickets = max(0, agent.open_tickets - 1)

    def take_back(self, ticket: Ticket) -> None:
        """Count a reopened ticket towards its agent's load again."""
        if ticket.assignee is not None:
            self.agent(ticket.assignee).open_tickets += 1
