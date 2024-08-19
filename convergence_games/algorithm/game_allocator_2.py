import argparse
import random
import shutil
from copy import deepcopy
from dataclasses import dataclass
from itertools import groupby
from pathlib import Path
from pprint import pprint
from typing import Literal, Self, TypeAlias

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine, func, select

from convergence_games.db.base_data import ALL_BASE_DATA
from convergence_games.db.extra_types import GroupHostingMode
from convergence_games.db.models import (
    Game,
    Person,
    PersonSessionSettings,
    PersonSessionSettingsWithExtra,
    PersonWithExtra,
    SessionPreference,
    TableAllocation,
    TableAllocationWithExtra,
    TimeSlot,
    TimeSlotWithExtra,
)
from convergence_games.db.sheets_importer import GoogleSheetsImporter


# region Database initialization
def create_mock_engine(force_recreate: bool = False) -> Engine:
    mock_base_path = Path("mock_base.db")
    if force_recreate and mock_base_path.exists():
        mock_base_path.unlink()

    if not mock_base_path.exists():
        mock_base_engine = create_engine(f"sqlite:///{str(mock_base_path)}")
        SQLModel.metadata.create_all(mock_base_engine)

        with Session(mock_base_engine) as session:
            session.add_all(ALL_BASE_DATA)
            dbos = GoogleSheetsImporter.from_urls().import_all()
            session.add_all(dbos)
            session.commit()

    mock_runtime_path = Path("mock_runtime.db")
    if mock_runtime_path.exists():
        mock_runtime_path.unlink()
    shutil.copy(mock_base_path, mock_runtime_path)
    mock_runtime_engine = create_engine(f"sqlite:///{str(mock_runtime_path)}")
    SQLModel.metadata.create_all(mock_runtime_engine)

    return mock_runtime_engine


def create_simulated_player_data(args: argparse.Namespace) -> None:
    random.seed(42)

    mock_runtime_engine = create_mock_engine(force_recreate=args.force_recreate)

    with Session(mock_runtime_engine) as session:
        # SIMULATE NEW PLAYERS
        current_n_players: int = session.exec(func.count(Person.id)).scalar()

        simulated_persons = [
            Person(
                name=f"Simulated {i:03d}",
                email=f"simulated{i:03d}@email.com",
                golden_d20s=1 if i < args.n_with_golden_d20 else 0,
            )
            for i in range(current_n_players + 1, args.n_players + 1)
        ]

        session.add_all(simulated_persons)
        session.commit()

        # GET ALL TABLE ALLOCATIONS
        persons = session.exec(select(Person)).all()
        table_allocations = session.exec(select(TableAllocation)).all()
        time_slots = session.exec(select(TimeSlot)).all()

        # SIMULATE GOLDEN D20s
        people_with_golden_d20 = random.sample(persons, args.n_with_golden_d20)
        for person in people_with_golden_d20:
            person.golden_d20s = 1
        session.add_all(people_with_golden_d20)

        # SIMULATE SESSION PREFERENCES
        for person in persons:
            for table_allocation in table_allocations:
                session_preference = SessionPreference(
                    preference=random.choice([0, 1, 2, 3, 4, 5, 20]),  # TODO: Weighted preferences
                    person_id=person.id,
                    table_allocation_id=table_allocation.id,
                )
                # We also simulate _not_ having a preference for a table allocation sometimes if it's a 3 - i.e. the default
                if session_preference.preference == 3 and random.random() < 0.5:
                    continue
                session.add(session_preference)

        # SIMULATE PERSON SESSION SETTINGS
        for person in persons:
            for time_slot in time_slots:
                session.add(PersonSessionSettings(person_id=person.id, time_slot_id=time_slot.id, checked_in=True))

        # SIMULATE GROUPS
        for time_slot in time_slots:
            print("Time Slot:", time_slot)
            players_gming_this_session = session.exec(
                select(Person)
                .join(Game, Game.gamemaster_id == Person.id)
                .join(TableAllocation, TableAllocation.game_id == Game.id)
                .join(TimeSlot, TimeSlot.id == TableAllocation.time_slot_id)
                .filter(TimeSlot.id == time_slot.id)
            ).all()
            # print("GMing", len(players_gming_this_session))
            # Exclude GMs from the list of players to group
            players_eligible_to_group = [person for person in persons if person not in players_gming_this_session]
            # print("GROUPABLE", len(players_eligible_to_group))
            for group_size, n_groups in [(2, args.n_groups_of_2), (3, args.n_groups_of_3)]:
                for _ in range(n_groups):
                    group = random.sample(players_eligible_to_group, group_size)
                    for person in group:
                        players_eligible_to_group.remove(person)
                    print([person.name for person in group])
                    host_person_session_settings: PersonSessionSettings = session.exec(
                        select(PersonSessionSettings).filter(
                            (PersonSessionSettings.person_id == group[0].id)
                            & (PersonSessionSettings.time_slot_id == time_slot.id)
                        )
                    ).first()
                    host_person_session_settings.group_hosting_mode = GroupHostingMode.HOSTING
                    host_person_session_settings.group_members = group[1:]
                    session.add(host_person_session_settings)
                    for person in group[1:]:
                        person_session_settings: PersonSessionSettings = session.exec(
                            select(PersonSessionSettings).filter(
                                (PersonSessionSettings.person_id == person.id)
                                & (PersonSessionSettings.time_slot_id == time_slot.id)
                            )
                        ).first()
                        person_session_settings.group_hosting_mode = GroupHostingMode.JOINED
                        session.add(person_session_settings)

        session.commit()


def data_generation_main(args: argparse.Namespace) -> None:
    create_simulated_player_data(args)


# endregion


# region Game Allocator
person_id_t: TypeAlias = int
table_allocation_id_t: TypeAlias = int
time_slot_id_t: TypeAlias = int
game_id_t: TypeAlias = int
preference_score_t: TypeAlias = Literal[0, 1, 2, 3, 4, 5, 20]


@dataclass
class Group:
    person_ids: list[person_id_t]
    preferences: dict[table_allocation_id_t, preference_score_t]
    average_compensation: float = 0.0

    @classmethod
    def from_person_and_session_settings(
        cls, person: PersonWithExtra, session_settings: PersonSessionSettingsWithExtra
    ) -> Self:
        persons = [person] + (
            list(session_settings.group_members)
            if session_settings.group_hosting_mode == GroupHostingMode.HOSTING
            else []
        )
        person_ids = {person.id for person in persons}
        # Just in case, to deduplicate
        persons = [[p for p in persons if p.id == person_id][0] for person_id in person_ids]
        preferences = {
            session_preference.table_allocation_id: session_preference.preference
            for session_preference in person.session_preferences
            if session_preference.table_allocation.time_slot_id == session_settings.time_slot_id
        }
        average_compensation = sum([person.compensation for person in persons]) / len(persons)
        return cls(person_ids=person_ids, preferences=preferences, average_compensation=average_compensation)

    def __len__(self) -> int:
        return len(self.person_ids)


@dataclass
class GameAllocationResult:
    group: Group
    table_allocation_id: int


class GameAllocator:
    def __init__(self, engine: Engine, time_slot_id: time_slot_id_t) -> None:
        self.engine = engine
        self.time_slot_id = time_slot_id
        self._setup()

    def _setup(self) -> None:
        # Get all the data we need from the database to do the allocation
        # End result
        # self.groups: list[Group] = []
        # self.table_allocations: list[TableAllocationWithExtra] = []

        with Session(self.engine) as session:
            solo_or_hosts: list[tuple[Person, PersonSessionSettings]] = session.exec(
                select(Person, PersonSessionSettings)
                .join(Person, Person.id == PersonSessionSettings.person_id)
                .filter(
                    (PersonSessionSettings.time_slot_id == self.time_slot_id)
                    & (
                        (
                            # Solo players
                            (PersonSessionSettings.checked_in)
                            & (PersonSessionSettings.group_hosting_mode == GroupHostingMode.NOT_IN_GROUP)
                        )
                        # Hosts
                        | (PersonSessionSettings.group_hosting_mode == GroupHostingMode.HOSTING)
                    )
                )
            ).all()
            self.groups = [
                Group.from_person_and_session_settings(
                    PersonWithExtra.model_validate(person),
                    PersonSessionSettingsWithExtra.model_validate(person_session_settings),
                )
                for person, person_session_settings in solo_or_hosts
            ]
            self.table_allocations = [
                TableAllocationWithExtra.model_validate(table_allocation)
                for table_allocation in session.exec(
                    select(TableAllocation).filter(TableAllocation.time_slot_id == self.time_slot_id)
                ).all()
            ]

    def allocate(self) -> list[GameAllocationResult]:
        print("Groups")
        # pprint(self.groups)
        print(len(self.groups))
        print("Table Allocations")
        # pprint(self.table_allocations)
        print(len(self.table_allocations))


def allocate(engine: Engine, time_slot_id: time_slot_id_t) -> list[GameAllocationResult]:
    game_allocator = GameAllocator(engine, time_slot_id)
    return game_allocator.allocate()


def end_to_end_main(args: argparse.Namespace) -> None:
    # Setup
    mock_runtime_engine = create_engine("sqlite:///mock_runtime.db")
    SQLModel.metadata.create_all(mock_runtime_engine)

    all_time_slot_ids = range(1, 5 + 1)
    first_time_slot_ids = [1]

    # Doing each round of allocations
    for time_slot_id in first_time_slot_ids:
        allocate(mock_runtime_engine, time_slot_id)


# endregion

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers()
    # data_generation
    data_generation_parser = subparsers.add_parser("data_generation")
    data_generation_parser.set_defaults(func=data_generation_main)
    data_generation_parser.add_argument("--force-recreate", action="store_true")
    data_generation_parser.add_argument("--n-players", type=int, default=160)  # Inclusive of existing GMs
    data_generation_parser.add_argument("--n-with-golden-d20", type=int, default=30)
    data_generation_parser.add_argument("--n-groups-of-2", type=int, default=10)  # 2 * 10 = 20
    data_generation_parser.add_argument("--n-groups-of-3", type=int, default=10)  # 3 * 10 = 30
    # end_to_end
    end_to_end_parser = subparsers.add_parser("end_to_end")
    end_to_end_parser.set_defaults(func=end_to_end_main)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()
