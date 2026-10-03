"""Who is asking, about whom, and with what scope. Built only from the verified JWT, share link or care link,
never from anything the model or the browser claims.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.orm import Session


@dataclass
class AgentContext:
    db: Session
    role: str                       # patient | doctor  (also the agent type)
    actor_id: str                   # patient id, or doctor user id
    actor_name: str
    patient_id: str                 # the record being worked on (own record for patients, the linked patient for doctors)
    scope: str = "full"             # full | labs | medicines (share-link scopes)
    lang: str = "en"
    conversation_id: str | None = None
    file_id: str | None = None      # the file attached to this request (the router checks ownership)
    session: dict = field(default_factory=dict)  # short term facts for this chat (e.g. the last draft visit)
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    @property
    def agent_type(self) -> str:
        return self.role
