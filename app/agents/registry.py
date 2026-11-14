"""Creates the agents once and registers them on the shared bus."""
from app.agents.bus import bus
from app.agents.notification_agent import NotificationAgent
from app.agents.venue_agent import VenueAgent

_agents = {}


def setup_agents():
    if not _agents:
        _agents["VenueAgent"] = VenueAgent(bus)
        _agents["NotificationAgent"] = NotificationAgent(bus)
    return _agents
