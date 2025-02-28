from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class Title:
    """
    Represents the title of a gallery in different languages.

    Attributes:
        english: The English title
        japanese: The Japanese title
        pretty: A formatted/cleaned version of the title
    """

    english: str
    japanese: str
    pretty: str


@dataclass(frozen=True)
class Tag:
    """
    Represents a tag associated with a gallery.

    Attributes:
        id: Unique identifier for the tag
        type: Category of the tag (e.g., "artist", "language", "tag")
        name: Display name of the tag
        url: URL path for the tag on nhentai
        count: Number of galleries with this tag
    """

    id: int
    type: str
    name: str
    url: str
    count: int


@dataclass(frozen=True)
class Images:
    """
    Contains URLs for all images associated with a gallery.

    Attributes:
        pages: List of URLs for all pages in the gallery
        cover: URL of the gallery cover image
        thumbnail: URL of the gallery thumbnail image
    """

    pages: List[str]
    cover: str
    thumbnail: str


@dataclass(frozen=True)
class NhentaiGallery:
    """
    Represents a complete nhentai gallery with all its metadata.

    Attributes:
        id: Unique identifier for the gallery
        media_id: Internal media ID used in image URLs
        title: Title object containing different versions of the title
        images: Images object containing all image URLs
        scanlator: Name of the scanlator/translator
        upload_date: Unix timestamp of when the gallery was uploaded
        tags: List of Tag objects associated with the gallery
        num_pages: Total number of pages in the gallery
        num_favorites: Number of times the gallery has been favorited
    """

    id: int
    media_id: int
    title: Title
    images: Images
    scanlator: str
    upload_date: int
    tags: List[Tag]
    num_pages: int
    num_favorites: int
