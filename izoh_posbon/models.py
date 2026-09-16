from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class ModerationAction(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    DELETE = "delete"
    BAN = "ban"


@dataclass(frozen=True)
class Signal:
    code: str
    points: int
    detail: str


@dataclass
class ProfileSnapshot:
    user_id: int
    full_name: str
    username: str = ""
    bio: str = ""
    personal_channel_id: Optional[int] = None
    personal_channel_title: str = ""
    personal_channel_username: str = ""
    personal_channel_description: str = ""
    personal_channel_recent_text: str = ""
    photo_bytes: Optional[bytes] = None
    photo_samples: Tuple[bytes, ...] = ()


@dataclass
class ModerationContext:
    text: str
    profile: ProfileSnapshot
    chat_id: Optional[int] = None
    duplicate_count: int = 0
    coordinated_user_count: int = 0
    learned_patterns: Tuple[str, ...] = ()
    seconds_after_post: Optional[int] = None


@dataclass
class ModerationDecision:
    score: int
    action: ModerationAction
    signals: List[Signal] = field(default_factory=list)
    ai_categories: Dict[str, float] = field(default_factory=dict)
