from typing import Optional, Any, List
from pydantic import BaseModel


# ── Twilio Voice ──────────────────────────────────────────────────────────────

class TwilioVoiceWebhook(BaseModel):
    CallSid: str
    AccountSid: str
    From: str
    To: str
    CallStatus: str
    Direction: Optional[str] = None
    SpeechResult: Optional[str] = None
    Confidence: Optional[str] = None
    RecordingUrl: Optional[str] = None
    RecordingSid: Optional[str] = None
    Digits: Optional[str] = None

    model_config = {"extra": "allow"}


# ── Meta WhatsApp Cloud API ───────────────────────────────────────────────────

class WAProfile(BaseModel):
    name: str


class WAContact(BaseModel):
    profile: WAProfile
    wa_id: str


class WATextBody(BaseModel):
    body: str


class WAImage(BaseModel):
    id: str
    mime_type: Optional[str] = None
    sha256: Optional[str] = None
    caption: Optional[str] = None


class WAMessage(BaseModel):
    id: str
    from_: str
    timestamp: str
    type: str
    text: Optional[WATextBody] = None
    image: Optional[WAImage] = None

    model_config = {"populate_by_name": True, "extra": "allow"}

    # Meta sends "from" which is a Python reserved word
    @classmethod
    def model_validate(cls, obj: Any, *args, **kwargs):
        if isinstance(obj, dict) and "from" in obj:
            obj = dict(obj)
            obj["from_"] = obj.pop("from")
        return super().model_validate(obj, *args, **kwargs)


class WAValue(BaseModel):
    messaging_product: str
    metadata: Optional[dict] = None
    contacts: Optional[List[WAContact]] = None
    messages: Optional[List[WAMessage]] = None
    statuses: Optional[List[dict]] = None

    model_config = {"extra": "allow"}


class WAChange(BaseModel):
    value: WAValue
    field: str


class WAEntry(BaseModel):
    id: str
    changes: List[WAChange]


class WAWebhookPayload(BaseModel):
    object: str
    entry: List[WAEntry]
