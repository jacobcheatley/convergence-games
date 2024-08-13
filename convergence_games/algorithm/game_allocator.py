import random
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from itertools import groupby
from pathlib import Path
from pprint import pprint
from typing import TypeAlias

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine, select

from convergence_games.db.models import (
    Game,
    Person,
    SessionPreference,
    SessionPreferenceWithExtra,
    System,
    TableAllocation,
    TableAllocationWithExtra,
    TimeSlot,
    TimeSlotWithExtra,
)


@dataclass
class MockSessionData:
    games: list[Game]
    table_allocations: list[TableAllocation]
    gms: list[Person]
    players: list[Person]
    session_preferences: list[SessionPreference]


N_GAMES = 30
N_PLAYERS = 150
N_POPULAR_GAMES = 10
N_UNPOPULAR_GAMES = 10
# N_GAMES = 5
# N_PLAYERS = 20
# N_POPULAR_GAMES = 1
# N_UNPOPULAR_GAMES = 1

assert N_GAMES >= N_POPULAR_GAMES + N_UNPOPULAR_GAMES

POPULAR_GAMES = set(range(N_POPULAR_GAMES))
UNPOPULAR_GAMES = set(range(N_POPULAR_GAMES, N_POPULAR_GAMES + N_UNPOPULAR_GAMES))


def create_mock_data() -> Engine:
    random.seed(42)

    mock_gms = [
        Person(
            id=i,
            name=f"GM {i}",
            email=f"gm{i}@email.com",
        )
        for i in range(N_GAMES)
    ]

    mock_players = [
        Person(
            id=N_GAMES + i,
            name=f"Player {i}",
            email=f"player{i}@email.com",
            golden_d20s=random.choice([0, 0, 0, 0, 0, 1]),
        )
        for i in range(N_PLAYERS)
    ]

    mock_games = [
        Game(
            id=i,
            title=f"Game {i}",
            description=f"Description {i}",
            gamemaster_id=i,
            system_id=1,
            minimum_players=(x := random.randint(2, 4)),
            optimal_players=(y := random.randint(x, 5)),
            maximum_players=(z := random.randint(y, 7)),
        )
        for i in range(N_GAMES)
    ]

    mock_table_allocations = [
        TableAllocation(
            id=game.id,
            game_id=game.id,
            time_slot_id=1,
            table_number=game.id,
        )
        for game in mock_games
    ]

    def make_preference(golden_d20s, game_index) -> int:
        if game_index in POPULAR_GAMES:
            # print(f"{game_index} is POPULAR")
            return random.choice([3, 4, 5, 20] if golden_d20s else [3, 4, 5])
        elif game_index in UNPOPULAR_GAMES:
            # print(f"{game_index} is UNPOPULAR")
            return random.choice([0, 0, 1, 2])

        return random.choice([0, 1, 2, 3, 4, 5, 20] if golden_d20s else [0, 1, 2, 3, 4, 5])

    mock_session_preferences = [
        SessionPreference(
            person_id=player.id,
            table_allocation_id=table_allocation.id,
            preference=make_preference(player.golden_d20s, table_allocation.id),
        )
        for player in mock_players
        for table_allocation in mock_table_allocations
    ]

    engine_path = Path("mock_data.db")
    if engine_path.exists():
        engine_path.unlink()
    engine = create_engine(f"sqlite:///{engine_path}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(System(id=1, name="Mock System"))
        session.add(TimeSlot(id=1, name="Mock Time Slot 1", start_time=datetime.now(), end_time=datetime.now()))
        session.add_all(mock_gms)
        session.add_all(mock_players)
        session.add_all(mock_games)
        session.add_all(mock_table_allocations)
        session.add_all(mock_session_preferences)
        session.commit()

    return engine


# Table allocation ID
ta_id_t: TypeAlias = int
# Loss value for a table allocation
ta_loss_t: TypeAlias = int  # 0 is BEST, 6 is WORST - we want to minimise this
# Player ID
player_id_t: TypeAlias = int


class GameAllocator:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def _order_preferences_for_player(self, preferences: list[SessionPreference]) -> dict[ta_loss_t, list[ta_id_t]]:
        # Grouping together things with the same preference value
        # Sorting groups by preference value
        # Sorting within groups by random order
        groups = [
            random.sample(ll := list(v), len(ll))
            for k, v in groupby(
                sorted(
                    preferences,
                    key=lambda preference: preference.preference,
                    reverse=True,  # Reverse so that the best preferences are first
                ),
                key=lambda preference: preference.preference,
            )
        ]
        result = dict(enumerate([[sp.table_allocation_id for sp in g] for g in groups]))
        return result

    def allocate(self, time_slot_id: int) -> None:
        # Get a final allocation for each player and game session

        all_table_allocations: list[TableAllocationWithExtra] = []
        table_allocation_lookup: dict[ta_id_t, TableAllocationWithExtra] = {}
        all_preferences_by_player: dict[player_id_t, list[SessionPreference]] = {}

        with Session(self.engine) as session:
            statement = session.get(TimeSlot, time_slot_id)
            time_slot = TimeSlotWithExtra.model_validate(statement)

            for table_allocation in time_slot.table_allocations:
                all_table_allocations.append(table_allocation)
                table_allocation_lookup[table_allocation.id] = TableAllocationWithExtra.model_validate(table_allocation)
                for session_preference in table_allocation.session_preferences:
                    all_preferences_by_player.setdefault(session_preference.person_id, []).append(session_preference)

        # TODO: Golden D20s

        # Generate each players preference 'loss' for each table allocation
        ordered_preferences_by_player = {
            player_id: self._order_preferences_for_player(preferences)
            for player_id, preferences in all_preferences_by_player.items()
        }
        print("Ordered Preferences by Player")
        pprint(ordered_preferences_by_player)
        loss_by_player_and_table: dict[player_id_t, dict[ta_id_t, ta_loss_t]] = {
            player_id: {ta_id: ta_loss for ta_loss, ta_ids in ordered_preferences.items() for ta_id in ta_ids}
            for player_id, ordered_preferences in ordered_preferences_by_player.items()
        }

        def initial_allocate(
            current_allocations: dict[ta_id_t, list[player_id_t]],
            player_id: player_id_t,
        ) -> tuple[dict[ta_id_t, list[player_id_t]], bool]:
            our_preferences = ordered_preferences_by_player[player_id]
            for our_ta_loss, table_allocation_ids in our_preferences.items():
                print(f"Player {player_id} testing {our_ta_loss}")
                # Politely try to join available tables with our highest preference
                ta_ids_sorted_by_missing_players = sorted(
                    table_allocation_ids,
                    key=lambda ta_id: table_allocation_lookup[ta_id].game.maximum_players
                    - len(current_allocations[ta_id]),
                )
                # for ta_id in random.sample(table_allocation_ids, len(table_allocation_ids)):
                for ta_id in ta_ids_sorted_by_missing_players:
                    print(f"Player {player_id} trying table {ta_id}")
                    if len(current_allocations[ta_id]) < table_allocation_lookup[ta_id].game.maximum_players:
                        current_allocations[ta_id].append(player_id)
                        return current_allocations, True

                print(f"Player {player_id} didn't find a table at {our_ta_loss}, attempting to move")

                # All of our highest preference tables are full
                # so we'll do one more try which is less polite and can move players as long as they don't lose preference
                for ta_id in random.sample(table_allocation_ids, len(table_allocation_ids)):
                    print(f"Player {player_id} trying move people from {ta_id}")
                    other_players_at_table = current_allocations[ta_id]
                    for other_player_id in other_players_at_table:
                        other_ta_loss = loss_by_player_and_table[other_player_id][ta_id]
                        if other_ta_loss >= our_ta_loss:
                            # Their preference is worse than ours (higher loss), so we can see if they have other options at the same loss level
                            other_preferences = ordered_preferences_by_player[other_player_id]
                            for other_ta_id in random.sample(
                                other_preferences[other_ta_loss], len(other_preferences[other_ta_loss])
                            ):
                                if (
                                    len(current_allocations[other_ta_id])
                                    < table_allocation_lookup[other_ta_id].game.maximum_players
                                ):
                                    print("Moving player", other_player_id, "from", ta_id, "to", other_ta_id)
                                    # They have another table at the same loss level that isn't full
                                    # So we can move them there
                                    current_allocations[ta_id].remove(other_player_id)
                                    current_allocations[other_ta_id].append(other_player_id)
                                    current_allocations[ta_id].append(player_id)
                                    return current_allocations, True

            return current_allocations, False

        def try_make_up_numbers(
            current_allocations: dict[ta_id_t, list[player_id_t]],
            ta_id: ta_id_t,
            tables_with_more_than_sweet_spot: list[ta_id_t],
        ) -> tuple[dict[ta_id_t, list[player_id_t]], bool]:
            minimum_deficit = table_allocation_lookup[ta_id].game.minimum_players - len(current_allocations[ta_id])
            sweetspot_deficit = table_allocation_lookup[ta_id].game.optimal_players - len(current_allocations[ta_id])
            print(f"Table {ta_id} has {len(current_allocations[ta_id])} players, needs {minimum_deficit} more")
            # Find players with an equal or higher preference for this table
            possible_players_to_move: list[ta_id_t, player_id_t] = []
            for other_ta_id in tables_with_more_than_sweet_spot:
                if other_ta_id == ta_id:
                    continue
                for other_player_id in current_allocations[other_ta_id]:
                    other_ta_loss = loss_by_player_and_table[other_player_id][other_ta_id]
                    if other_ta_loss > loss_by_player_and_table[other_player_id][ta_id]:
                        # The player has a higher preference for the table they're currently at, don't move
                        continue
                    if ta_id in ordered_preferences_by_player[other_player_id][other_ta_loss]:
                        print(
                            f"Player {other_player_id} has a preference for {other_ta_id} of {other_ta_loss} and this table of {loss_by_player_and_table[other_player_id][ta_id]}"
                        )
                        possible_players_to_move.append((other_ta_id, other_player_id))
            print(f"Possible players to move: {possible_players_to_move}")
            if len(possible_players_to_move) < minimum_deficit:
                print("Not enough players to move")
                return current_allocations, False

            selected_players_to_move = []
            for other_ta_id, other_player_id in random.sample(possible_players_to_move, len(possible_players_to_move)):
                # If no longer above sweet spot in this game, don't move
                current_players_in_other_ta_if_post_move = len(current_allocations[other_ta_id]) - len(
                    [t for t, p in selected_players_to_move if t == other_ta_id]
                )
                if (
                    current_players_in_other_ta_if_post_move
                    <= table_allocation_lookup[other_ta_id].game.optimal_players
                ):
                    # Don't move this player as it would take the other table below the sweet spot
                    continue
                selected_players_to_move.append((other_ta_id, other_player_id))
                if len(selected_players_to_move) == sweetspot_deficit:
                    break

            if len(selected_players_to_move) < minimum_deficit:
                print("Not enough players to move without disrupting sweet spots")
                return current_allocations, False

            print(f"Moving {selected_players_to_move} players to table {ta_id}")
            for other_ta_id, other_player_id in selected_players_to_move:
                current_allocations[other_ta_id].remove(other_player_id)
                current_allocations[ta_id].append(other_player_id)
            return current_allocations, True

        def evaluate_total_loss(current_allocations: dict[ta_id_t, list[player_id_t]]) -> ta_loss_t:
            # Calculate the total loss for the current allocation
            total_loss = 0
            for ta_id, player_ids in current_allocations.items():
                for player_id in player_ids:
                    total_loss += loss_by_player_and_table[player_id][ta_id]
            return total_loss

        def evaluate_loss_breakdown(current_allocations: dict[ta_id_t, list[player_id_t]]) -> dict[ta_loss_t, int]:
            # Calculate the total loss for the current allocation
            loss_breakdown = {}
            for ta_id, player_ids in current_allocations.items():
                for player_id in player_ids:
                    loss = loss_by_player_and_table[player_id][ta_id]
                    loss_breakdown[loss] = loss_breakdown.get(loss, 0) + 1
            return loss_breakdown

        def evaluate_delta_from_sweetspot_breakdown(
            current_allocations: dict[ta_id_t, list[player_id_t]],
        ) -> dict[int, int]:
            # Calculate the signed difference between the number of players at each table and the sweet spot
            # Positive = too many players, negative = too few players
            # Get a count of each delta
            delta_from_sweetspot_breakdown: dict[int, int] = {}
            for ta_id, player_ids in current_allocations.items():
                delta = len(player_ids) - table_allocation_lookup[ta_id].game.optimal_players
                delta_from_sweetspot_breakdown[delta] = delta_from_sweetspot_breakdown.get(delta, 0) + 1
                if delta > 2:
                    print(f"Table {ta_id} has {delta} too many players")
                    print(table_allocation_lookup[ta_id].game)
            return dict(sorted(delta_from_sweetspot_breakdown.items()))

        best_loss = None
        best_allocations = None
        best_loss_each_iteration = []

        n_trials = 10
        for seed in range(1, n_trials + 1):
            current_allocations = {table_allocation.id: [] for table_allocation in all_table_allocations}

            # Put every player into a random one of their first choices
            # If a table is over the maximum number of players, try another table if possible, find a player with another highest choice in a non full table and move them to another table
            # Repeat until no more players can be moved

            shuffled_player_ids = random.sample(list(all_preferences_by_player.keys()), len(all_preferences_by_player))

            for player_id in shuffled_player_ids:
                current_allocations, success = initial_allocate(current_allocations, player_id)
                if not success:
                    # TODO: This really really shouldn't ever happen
                    # It can only happen if there are more players than the sum of the maximum number of players for each game
                    # In which case we should just give up and cry
                    print(f"Failed to allocate player {player_id} in trial {seed}")
                    raise ValueError("Failed to allocate all players")
                print("----")

            # print(current_allocations)
            # print(f"Games with too few players: {len(games_with_too_few_players)}")
            tables_with_too_many_players = [
                ta.id for ta in all_table_allocations if len(current_allocations[ta.id]) > ta.game.maximum_players
            ]
            # print(f"Games with too many players: {len(games_with_too_many_players)}")
            assert not tables_with_too_many_players

            # Print number of games with less than the minimum number of players
            tables_with_too_few_players = [
                ta.id for ta in all_table_allocations if len(current_allocations[ta.id]) < ta.game.minimum_players
            ]
            print(f"Tables with too few players: {len(tables_with_too_few_players)}")

            # Then find each table with less than the minimum number of players and
            # move a player from a table with more than the sweet spot number of players to it if this doesn't result in a loss of preference
            # Repeat until no more players can be moved
            for ta_id in tables_with_too_few_players:
                tables_with_more_than_sweet_spot = [
                    ta.id for ta in all_table_allocations if len(current_allocations[ta.id]) > ta.game.optimal_players
                ]
                print(f"Tables with more than sweet spot: {len(tables_with_more_than_sweet_spot)}")
                current_allocations, success = try_make_up_numbers(
                    current_allocations, ta_id, tables_with_more_than_sweet_spot
                )
                if not success:
                    # TODO: Remove this game from running since we can't make up numbers
                    print(f"Failed to make up numbers for table {ta_id} in trial {seed}")
                    raise ValueError("Failed to make up numbers")
            tables_with_too_few_players = [
                ta.id for ta in all_table_allocations if len(current_allocations[ta.id]) < ta.game.minimum_players
            ]
            print(f"Tables with too few players after make up: {len(tables_with_too_few_players)}")

            # TODO: Now we have everyone allocated, trial moving players to minimise different to sweet spot

            loss = evaluate_total_loss(current_allocations)
            if best_loss is None or loss < best_loss:
                best_loss = loss
                best_allocations = deepcopy(current_allocations)

            best_loss_each_iteration.append(best_loss)

        print("Best loss", best_loss)
        print("Best allocations")
        pprint(best_allocations)
        print("Best loss each iteration")
        pprint(best_loss_each_iteration)
        loss_breakdown = evaluate_loss_breakdown(best_allocations)
        print("Loss breakdown")
        pprint(loss_breakdown)
        delta_from_sweetspot_breakdown = evaluate_delta_from_sweetspot_breakdown(best_allocations)
        print("Delta from sweetspot breakdown")
        pprint(delta_from_sweetspot_breakdown)

        # print("All games")
        # pprint(
        #     [
        #         f"Game {ta.game.id} ({ta.game.minimum_players} - {ta.game.maximum_players})"
        #         for ta in all_table_allocations
        #     ]
        # )


if __name__ == "__main__":
    engine = create_mock_data()
    game_allocator = GameAllocator(engine)
    game_allocator.allocate(time_slot_id=1)