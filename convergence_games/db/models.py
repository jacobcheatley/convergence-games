from __future__ import annotations

import datetime as dt
from typing import TypeAlias

from advanced_alchemy.base import BigIntAuditBase as Base
from sqlalchemy import ForeignKey, ForeignKeyConstraint, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from convergence_games.db.enums import GameCrunch, GameNarrativism, GameTone

# Types
MEDIA_LINK: TypeAlias = str


# Game Information Link Models
class GameGenreLink(Base):
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    genre_id: Mapped[int] = mapped_column(ForeignKey("genre.id"), primary_key=True)

    game: Mapped[Game] = relationship(back_populates="genre_links")
    genre: Mapped[Genre] = relationship(back_populates="game_links")


class GameContentWarningLink(Base):
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    content_warning_id: Mapped[int] = mapped_column(ForeignKey("content_warning.id"), primary_key=True)

    game: Mapped[Game] = relationship(back_populates="content_warning_links")
    content_warning: Mapped[ContentWarning] = relationship(back_populates="game_links")


class GameExtraGamemasterLink(Base):
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), primary_key=True)
    gamemaster_id: Mapped[int] = mapped_column(ForeignKey("user.id"), primary_key=True)

    game: Mapped[Game] = relationship(back_populates="extra_gamemaster_links")
    gamemaster: Mapped[User] = relationship(back_populates="extra_game_links")


# Game Information Models
class Venue(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str]
    address: Mapped[str]
    profile_picture: Mapped[MEDIA_LINK]

    # Relationships
    rooms: Mapped[list[Room]] = relationship(back_populates="venue")
    events: Mapped[list[Event]] = relationship(back_populates="venue")


class Event(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str]
    start_date: Mapped[dt.datetime] = mapped_column(index=True)
    end_date: Mapped[dt.datetime] = mapped_column(index=True)
    profile_picture: Mapped[MEDIA_LINK]

    # Foreign Keys
    venue_id: Mapped[int] = mapped_column(ForeignKey("venue.id"), index=True)

    # Relationships
    venue: Mapped[Venue] = relationship(back_populates="events")
    sessions: Mapped[list[Session]] = relationship(back_populates="event")
    user_event_infos: Mapped[list[UserEventInfo]] = relationship(back_populates="event")
    time_slots: Mapped[list[TimeSlot]] = relationship(back_populates="event")
    games: Mapped[list[Game]] = relationship(back_populates="event")


class System(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str]
    profile_picture: Mapped[MEDIA_LINK]

    # Relationships
    games: Mapped[list[Game]] = relationship(back_populates="system")


class Genre(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str]

    # Relationships
    games: Mapped[list[Game]] = relationship(back_populates="genres", secondary=GameGenreLink.__table__, viewonly=True)

    # Assocation Proxy Relationships
    game_links: Mapped[list[GameGenreLink]] = relationship(back_populates="genre")


class ContentWarning(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    description: Mapped[str]

    # Relationships
    games: Mapped[list[Game]] = relationship(
        back_populates="content_warnings", secondary=GameContentWarningLink.__table__, viewonly=True
    )

    # Assocation Proxy Relationships
    game_links: Mapped[list[GameContentWarningLink]] = relationship(back_populates="content_warning")


class Game(Base):
    name: Mapped[str] = mapped_column(index=True, unique=True)
    tagline: Mapped[str]
    description: Mapped[str]
    min_age: Mapped[int]
    crunch: Mapped[GameCrunch] = mapped_column(default=GameCrunch.MEDIUM, index=True)
    narrativism: Mapped[GameNarrativism] = mapped_column(default=GameNarrativism.BALANCED, index=True)
    tone: Mapped[GameTone] = mapped_column(default=GameTone.LIGHT_HEARTED, index=True)
    player_count_minimum: Mapped[int]
    player_count_optimal: Mapped[int]
    player_count_maximum: Mapped[int]
    nz_made: Mapped[bool] = mapped_column(default=False)
    designer_run: Mapped[bool] = mapped_column(default=False)
    profile_picture: Mapped[MEDIA_LINK]

    # Foreign Keys
    system_id: Mapped[int] = mapped_column(ForeignKey("system.id"), index=True)
    gamemaster_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)

    # Relationships
    system: Mapped[System] = relationship(back_populates="games")
    gamemaster: Mapped[User] = relationship(back_populates="games")
    event: Mapped[Event] = relationship(back_populates="games")
    sessions: Mapped[list[Session]] = relationship(back_populates="game", foreign_keys="Session.game_id")
    genres: Mapped[list[Genre]] = relationship(back_populates="games", secondary=GameGenreLink.__table__, viewonly=True)
    content_warnings: Mapped[list[ContentWarning]] = relationship(
        back_populates="games", secondary=GameContentWarningLink.__table__, viewonly=True
    )
    extra_gamemasters: Mapped[list[User]] = relationship(
        back_populates="extra_games", secondary=GameExtraGamemasterLink.__table__, viewonly=True
    )

    # Assocation Proxy Relationships
    genre_links: Mapped[list[GameGenreLink]] = relationship(back_populates="game")
    content_warning_links: Mapped[list[GameContentWarningLink]] = relationship(back_populates="game")
    extra_gamemaster_links: Mapped[list[GameExtraGamemasterLink]] = relationship(back_populates="game")

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )


# Timetable Information Models
class TimeSlot(Base):
    name: Mapped[str]
    start_time: Mapped[dt.datetime]
    end_time: Mapped[dt.datetime]

    # Foreign Keys
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="time_slots")
    sessions: Mapped[list[Session]] = relationship(back_populates="time_slot", foreign_keys="Session.time_slot_id")
    groups: Mapped[list[Group]] = relationship(back_populates="time_slot")
    compensations: Mapped[list[Compensation]] = relationship(back_populates="time_slot")

    __table_args__ = (
        # This redundant constraint is necessary for the foreign key constraint in Session
        UniqueConstraint("id", "event_id"),
    )


class Room(Base):
    name: Mapped[str]
    description: Mapped[str]

    # Foreign Keys
    venue_id: Mapped[int] = mapped_column(ForeignKey("venue.id"), index=True)

    # Relationships
    venue: Mapped[Venue] = relationship(back_populates="rooms")
    tables: Mapped[list[Table]] = relationship(back_populates="room")


class Table(Base):
    name: Mapped[str]

    # Foreign Keys
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), index=True)

    # Relationships
    room: Mapped[Room] = relationship(back_populates="tables")
    sessions: Mapped[list[Session]] = relationship(back_populates="table")


class Session(Base):
    # Foreign Keys
    game_id: Mapped[int] = mapped_column(ForeignKey("game.id"), index=True)
    table_id: Mapped[int] = mapped_column(ForeignKey("table.id"), index=True)
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slot.id"), index=True)
    event_id: Mapped[int] = mapped_column(
        ForeignKey("event.id"), index=True
    )  # Logically redundant, but necessary for constraints

    # Relationships
    game: Mapped[Game] = relationship(back_populates="sessions", foreign_keys=game_id)
    table: Mapped[Table] = relationship(back_populates="sessions")
    time_slot: Mapped[TimeSlot] = relationship(back_populates="sessions", foreign_keys=time_slot_id)
    event: Mapped[Event] = relationship(back_populates="sessions")
    group_session_preferences: Mapped[list[GroupSessionPreference]] = relationship(back_populates="session")
    allocation_results: Mapped[list[AllocationResult]] = relationship(back_populates="session")

    __table_args__ = (
        # https://dba.stackexchange.com/a/58972
        # These two constraints ensure that the Game and TimeSlot are part of the same Event
        ForeignKeyConstraint(
            ["game_id", "event_id"],
            ["game.id", "game.event_id"],
            name="fk_session_game_id_event_id_game",
        ),
        ForeignKeyConstraint(
            ["time_slot_id", "event_id"],
            ["time_slot.id", "time_slot.event_id"],
            name="fk_session_time_slot_id_event_id_time_slot",
        ),
    )


# User Information Models
class UserEventInfo(Base):
    golden_d20s: Mapped[int] = mapped_column(default=0)
    compensation: Mapped[int] = mapped_column(default=0)

    # Foreign Keys
    event_id: Mapped[int] = mapped_column(ForeignKey("event.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), index=True)

    # Relationships
    event: Mapped[Event] = relationship(back_populates="user_event_infos")
    user: Mapped[User] = relationship(back_populates="user_event_infos")
    compensations: Mapped[list[Compensation]] = relationship(back_populates="user_event_info")


class User(Base):
    name: Mapped[str] = mapped_column(index=True)
    email: Mapped[str] = mapped_column(index=True, unique=True)
    date_of_birth: Mapped[dt.date] = mapped_column(default=dt.date(1900, 1, 1))
    description: Mapped[str]
    profile_picture: Mapped[MEDIA_LINK | None]

    # Relationships
    games: Mapped[list[Game]] = relationship(back_populates="gamemaster")
    user_event_infos: Mapped[list[UserEventInfo]] = relationship(back_populates="user")
    extra_games: Mapped[list[Game]] = relationship(
        back_populates="extra_gamemasters", secondary=GameExtraGamemasterLink.__table__, viewonly=True
    )

    # Assocation Proxy Relationships
    extra_game_links: Mapped[list[GameExtraGamemasterLink]] = relationship(back_populates="gamemaster")


# Player Game Selection Models
class Group(Base):
    join_code: Mapped[str] = mapped_column(index=True)
    checked_in: Mapped[bool] = mapped_column(default=False)

    # Foreign Keys
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slot.id"), index=True)

    # Relationships
    time_slot: Mapped[TimeSlot] = relationship(back_populates="groups")
    group_session_preferences: Mapped[list[GroupSessionPreference]] = relationship(back_populates="group")
    allocation_results: Mapped[list[AllocationResult]] = relationship(back_populates="group")

    __table_args__ = (UniqueConstraint("time_slot_id", "join_code"),)


class GroupSessionPreference(Base):
    preference: Mapped[int]

    # Foreign Keys
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id"), index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("session.id"), index=True)

    # Relationships
    group: Mapped[Group] = relationship(back_populates="group_session_preferences")
    session: Mapped[Session] = relationship(back_populates="group_session_preferences")

    __table_args__ = (UniqueConstraint("group_id", "session_id"),)


# Allocation Base Models
class AllocationResult(Base):
    committed: Mapped[bool] = mapped_column(default=False)

    # Foreign Keys
    session_id: Mapped[int] = mapped_column(ForeignKey("session.id"), index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id"), index=True)

    # Relationships
    session: Mapped[Session] = relationship(back_populates="allocation_results")
    group: Mapped[Group] = relationship(back_populates="allocation_results")

    __table_args__ = (UniqueConstraint("session_id", "group_id"),)


class Compensation(Base):
    compensation_delta: Mapped[int] = mapped_column(default=0)
    golden_d20s_delta: Mapped[int] = mapped_column(default=0)
    applied: Mapped[bool] = mapped_column(default=False)
    reset: Mapped[bool] = mapped_column(default=False)

    # Foreign Keys
    user_event_info_id: Mapped[int] = mapped_column(ForeignKey("user_event_info.id"), index=True)
    time_slot_id: Mapped[int] = mapped_column(ForeignKey("time_slot.id"), index=True)

    # Relationships
    user_event_info: Mapped[UserEventInfo] = relationship(back_populates="compensations")
    time_slot: Mapped[TimeSlot] = relationship(back_populates="compensations")

    __table_args__ = (UniqueConstraint("user_event_info_id", "time_slot_id"),)
