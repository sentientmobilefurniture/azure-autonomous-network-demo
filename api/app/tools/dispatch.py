"""
dispatch_field_engineer — typed tool function for the declarative agent.

Simulates dispatching a field engineer by composing a structured dispatch
notification. Does not actually send email (future: use PRESENTER_EMAIL).
"""

import json
import logging
from datetime import datetime, timezone
from typing import Annotated

from pydantic import Field

logger = logging.getLogger(__name__)


async def dispatch_field_engineer(
    engineer_name: Annotated[str, Field(
        description="Full name of the on-duty field engineer from the duty roster."
    )],
    engineer_email: Annotated[str, Field(
        description="Email address of the field engineer."
    )],
    engineer_phone: Annotated[str, Field(
        description="Phone number of the field engineer."
    )],
    incident_summary: Annotated[str, Field(
        description="Brief summary of the incident and why dispatch is needed."
    )],
    destination_description: Annotated[str, Field(
        description=(
            "Human-readable description of where to go "
            "(e.g. 'Goulburn interchange splice point — 195km south of Sydney')."
        )
    )],
    destination_latitude: Annotated[float, Field(
        description="GPS latitude (WGS84) of the inspection site."
    )],
    destination_longitude: Annotated[float, Field(
        description="GPS longitude (WGS84) of the inspection site."
    )],
    physical_signs_to_inspect: Annotated[str, Field(
        description=(
            "Checklist of what to look for on arrival "
            "(e.g. 'Check fibre splice enclosure for physical damage')."
        )
    )],
    sensor_ids: Annotated[str, Field(
        description=(
            "Comma-separated sensor IDs that triggered the dispatch "
            "(e.g. 'SENS-SYD-MEL-F1-OPT-002,SENS-AMP-GOULBURN-VIB-001')."
        )
    )],
    urgency: Annotated[str, Field(
        description="Urgency level — 'CRITICAL', 'HIGH', or 'STANDARD'. Defaults to 'HIGH'."
    )] = "HIGH",
) -> str:
    """Dispatch a field engineer to a physical site to investigate a network incident.

    Composes and sends a dispatch notification (email) to the specified field
    engineer with incident details, exact GPS coordinates of the fault location,
    and a checklist of physical signs to inspect on arrival.
    """
    dispatch_time = datetime.now(timezone.utc).isoformat()
    dispatch_id = f"DISPATCH-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    maps_link = (
        f"https://www.google.com/maps?q={destination_latitude},{destination_longitude}"
    )

    email_subject = f"[{urgency}] Field Dispatch — {incident_summary[:80]}"
    email_body = f"""FIELD DISPATCH NOTIFICATION
{'=' * 50}

Dispatch ID:  {dispatch_id}
Urgency:      {urgency}
Dispatched:   {dispatch_time}

TO: {engineer_name}
Email: {engineer_email}
Phone: {engineer_phone}

{'─' * 50}
INCIDENT SUMMARY
{'─' * 50}
{incident_summary}

{'─' * 50}
DESTINATION
{'─' * 50}
Location: {destination_description}
GPS:      {destination_latitude}, {destination_longitude}
Map:      {maps_link}

{'─' * 50}
INSPECTION CHECKLIST
{'─' * 50}
{physical_signs_to_inspect}

{'─' * 50}
TRIGGERING SENSORS
{'─' * 50}
{sensor_ids}

{'─' * 50}
INSTRUCTIONS
{'─' * 50}
1. Proceed to the GPS coordinates above immediately.
2. Contact NOC on arrival: +61-2-9555-0100
3. Follow the inspection checklist above.
4. Report findings via the NOC incident channel.
5. Do NOT attempt repairs without L2 engineer authorisation.

{'=' * 50}
This dispatch was generated automatically by the Network AI Orchestrator.
"""

    logger.info(
        "Field dispatch executed: %s → %s at (%s, %s)",
        dispatch_id, engineer_name,
        destination_latitude, destination_longitude,
    )

    result = {
        "status": "dispatched",
        "dispatch_id": dispatch_id,
        "dispatch_time": dispatch_time,
        "engineer": {
            "name": engineer_name,
            "email": engineer_email,
            "phone": engineer_phone,
        },
        "destination": {
            "description": destination_description,
            "latitude": destination_latitude,
            "longitude": destination_longitude,
            "maps_link": maps_link,
        },
        "urgency": urgency,
        "sensor_ids": [s.strip() for s in sensor_ids.split(",")],
        "email_subject": email_subject,
        "email_body": email_body,
    }

    return json.dumps(result)
