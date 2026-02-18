# game/arena_battle_system.py
import random
import math
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict

@dataclass
class BattleCard:
    """Карта в бою"""
    id: int
    user_card_id: int
    name: str
    rarity: str
    anime: str
    power: int
    health: int
    max_health: int
    attack: int
    defense: int
    level: int
    image_url: Optional[str] = None
    position: int = 0

    def take_damage(self, damage: int) -> int:
        """Получить урон, возвращает фактический урон"""
        actual_damage = min(damage, self.health)
        self.health -= actual_damage
        return actual_damage

    def is_alive(self) -> bool:
        return self.health > 0

    def to_dict(self) -> dict:
        """Конвертация в словарь для API"""
        return {
            "id": self.id,
            "user_card_id": self.user_card_id,
            "name": self.name,
            "rarity": self.rarity,
            "power": self.power,
            "health": max(0, self.health),
            "max_health": self.max_health,
            "attack": self.attack,
            "defense": self.defense,
            "level": self.level,
            "image_url": self.image_url,
            "position": self.position,
            "is_alive": self.is_alive()
        }

@dataclass
class BattleAction:
    """Действие в бою"""
    attacker_id: int
    attacker_name: str
    defender_id: int
    defender_name: str
    damage: int
    is_critical: bool = False
    is_dodged: bool = False
    is_dead: bool = False

class ArenaBattle:
    """Система боя на арене"""

    def __init__(self, player_cards: List[BattleCard], enemy_cards: List[BattleCard]):
        self.player_cards = {c.id: c for c in player_cards}
        self.enemy_cards = {c.id: c for c in enemy_cards}
        self.turn = 0
        self.actions: List[BattleAction] = []
        self.winner: Optional[str] = None  # 'player', 'enemy', или None

        # Проверяем синергии в колоде
        self.player_synergies = self._check_synergies(list(self.player_cards.values()))
        self.enemy_synergies = self._check_synergies(list(self.enemy_cards.values()))

    def _check_synergies(self, cards: List[BattleCard]) -> Dict[str, int]:
        """Проверяет синергии в колоде (карты из одного аниме)"""
        anime_counts = {}
        for card in cards:
            if card.anime:
                anime_counts[card.anime] = anime_counts.get(card.anime, 0) + 1

        synergies = {}
        for anime, count in anime_counts.items():
            if count >= 3:
                synergies[anime] = 15  # +15% к статам
            elif count >= 2:
                synergies[anime] = 10  # +10% к статам

        return synergies

    def _calculate_damage(self, attacker: BattleCard, defender: BattleCard) -> Tuple[int, bool]:
        """Расчет урона с учетом критов"""
        # Базовая атака минус защита
        base_damage = max(1, attacker.attack - defender.defense // 2)

        # Шанс крита (10%)
        is_critical = random.random() < 0.1
        if is_critical:
            base_damage = int(base_damage * 1.5)

        # Рандомный разброс ±20%
        damage = int(base_damage * random.uniform(0.8, 1.2))

        return max(1, damage), is_critical

    def _get_alive_cards(self, is_player: bool) -> List[BattleCard]:
        """Получить живые карты стороны"""
        cards_dict = self.player_cards if is_player else self.enemy_cards
        return [c for c in cards_dict.values() if c.is_alive()]

    def next_turn(self) -> List[BattleAction]:
        """Выполнить следующий ход"""
        if self.winner:
            return []

        self.turn += 1
        turn_actions = []

        # Получаем живые карты
        alive_players = self._get_alive_cards(True)
        alive_enemies = self._get_alive_cards(False)

        # Если кто-то остался без карт - битва окончена
        if not alive_players:
            self.winner = 'enemy'
            return []
        if not alive_enemies:
            self.winner = 'player'
            return []

        # Копируем списки для безопасной модификации
        players_to_attack = alive_players.copy()
        enemies_to_attack = alive_enemies.copy()

        # Все живые карты игрока атакуют случайных врагов
        for player in players_to_attack:
            # Проверяем что есть живые враги
            current_alive_enemies = [c for c in enemies_to_attack if c.is_alive()]
            if not current_alive_enemies:
                break

            target = random.choice(current_alive_enemies)
            damage, is_critical = self._calculate_damage(player, target)

            actual_damage = target.take_damage(damage)

            action = BattleAction(
                attacker_id=player.id,
                attacker_name=player.name,
                defender_id=target.id,
                defender_name=target.name,
                damage=actual_damage,
                is_critical=is_critical,
                is_dead=not target.is_alive()
            )
            turn_actions.append(action)

        # Обновляем список живых врагов после атак игрока
        alive_enemies = self._get_alive_cards(False)
        enemies_to_attack = alive_enemies.copy()

        # Все живые карты врага атакуют случайных игроков
        for enemy in enemies_to_attack:
            # Проверяем что есть живые игроки
            current_alive_players = [c for c in players_to_attack if c.is_alive()]
            if not current_alive_players:
                break

            target = random.choice(current_alive_players)
            damage, is_critical = self._calculate_damage(enemy, target)

            actual_damage = target.take_damage(damage)

            action = BattleAction(
                attacker_id=enemy.id,
                attacker_name=enemy.name,
                defender_id=target.id,
                defender_name=target.name,
                damage=actual_damage,
                is_critical=is_critical,
                is_dead=not target.is_alive()
            )
            turn_actions.append(action)

        # Проверяем победителя после хода
        alive_players = self._get_alive_cards(True)
        alive_enemies = self._get_alive_cards(False)

        if not alive_players:
            self.winner = 'enemy'
        elif not alive_enemies:
            self.winner = 'player'

        self.actions.extend(turn_actions)
        return turn_actions

    def get_battle_state(self) -> dict:
        """Получить текущее состояние боя"""
        return {
            "turn": self.turn,
            "winner": self.winner,
            "player_cards": [c.to_dict() for c in self.player_cards.values()],
            "enemy_cards": [c.to_dict() for c in self.enemy_cards.values()],
            "player_synergies": self.player_synergies,
            "enemy_synergies": self.enemy_synergies,
            "actions": [asdict(a) for a in self.actions[-10:]]  # Последние 10 действий
        }

    def auto_battle(self) -> List[BattleAction]:
        """Автоматический бой до конца"""
        all_actions = []
        while not self.winner:
            turn_actions = self.next_turn()
            all_actions.extend(turn_actions)
        return all_actions
        