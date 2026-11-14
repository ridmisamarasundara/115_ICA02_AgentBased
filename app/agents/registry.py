"""Creates the agents once and registers them on the shared bus."""
from app.agents.booking_agent import BookingAgent
from app.agents.bus import bus
from app.agents.notification_agent import NotificationAgent
from app.agents.ticket_agent import TicketAgent
from app.agents.venue_agent import VenueAgent

_agents = {}


def setup_agents():
    if not _agents:
        for cls in (VenueAgent, BookingAgent, TicketAgent, NotificationAgent):
            _agents[cls.name] = cls(bus)
    return _agents
