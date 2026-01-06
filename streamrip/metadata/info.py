from dataclasses import dataclass


@dataclass(slots=True)
class AlbumInfo:
    id: str
    source: str
