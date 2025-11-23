"""
MediaType enumeration for ROMA v2.0 Multimodal Context.

Defines the media types supported in the multimodal context builder.
MVP implementation supports TEXT and FILE, with extensibility for future types.
"""

from enum import Enum
from typing import Literal


class MediaType(str, Enum):
    """
    Media type enumeration for multimodal context handling.

    MVP supports TEXT and FILE types. Future extensions will include
    IMAGE, AUDIO, VIDEO, and other multimedia types.
    """

    TEXT = "text"  # Text content (goals, results, descriptions)
    FILE = "file"  # File artifacts (documents, data files, etc.)
    IMAGE = "image"  # Image content and artifacts
    AUDIO = "audio"  # Audio recordings and transcripts
    VIDEO = "video"  # Video content and metadata

    def __str__(self) -> str:
        return self.value

    @classmethod
    def from_string(cls, value: str) -> "MediaType":
        """
        Convert string to MediaType.

        Args:
            value: String representation of media type

        Returns:
            MediaType enum value

        Raises:
            ValueError: If value is not a valid media type
        """
        try:
            return cls(value.lower())
        except ValueError:
            valid_types = [t.value for t in cls]
            raise ValueError(
                f"Invalid media type '{value}'. Valid types: {valid_types}"
            )

    @property
    def is_text(self) -> bool:
        """Check if this is a TEXT media type."""
        return self == MediaType.TEXT

    @property
    def is_file(self) -> bool:
        """Check if this is a FILE media type."""
        return self == MediaType.FILE

    @property
    def is_image(self) -> bool:
        """Check if this is an IMAGE media type."""
        return self == MediaType.IMAGE

    @property
    def is_audio(self) -> bool:
        """Check if this is an AUDIO media type."""
        return self == MediaType.AUDIO

    @property
    def is_video(self) -> bool:
        """Check if this is a VIDEO media type."""
        return self == MediaType.VIDEO

    @property
    def requires_storage(self) -> bool:
        """Check if this media type requires external storage."""
        return self in [
            MediaType.FILE,
            MediaType.IMAGE,
            MediaType.AUDIO,
            MediaType.VIDEO,
        ]

    @property
    def supports_inline(self) -> bool:
        """Check if this media type can be included inline in context."""
        return self == MediaType.TEXT


# Type hints for use in other modules
MediaTypeLiteral = Literal["text", "file", "image", "audio", "video"]
