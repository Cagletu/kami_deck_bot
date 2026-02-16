import random
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class BattleCard:
    """Карта в бою"""
    id: int
    user_card_id: int  # ID из user_cards
    name: str
    rarity: str
    anime: str
    power: int
    health: int
    max_health: int
    attack: int
    defense: int
    level: int
    image_url: str
    position: int

@dataclass
class BattleAction:
    """Действие в бою"""
    turn: int
    attacker_id: int
    attacker_name: str
    defender_id: int
    defender_name: str
    damage: int
    defender_health_before: int
    defender_health_after: int
    is_critical: bool
    is_dodged: bool

class ArenaBattle:
    """Класс для управления боем"""

    def __init__(self, user_cards: List[BattleCard], opponent_cards: List[BattleCard]):
        self.user_cards = user_cards
        self.opponent_cards = opponent_cards
        self.turn = 0
        self.actions: List[BattleAction] = []
        self.winner = None

        # Анализируем синергии для бонусов
        self.user_synergies = self._analyze_synergies(user_cards)
        self.opponent_synergies = self._analyze_synergies(opponent_cards)

        # Применяем бонусы синергии
        self._apply_synergies(self.user_cards, self.user_synergies)
        self._apply_synergies(self.opponent_cards, self.opponent_synergies)

    def _analyze_synergies(self, cards: List[BattleCard]) -> Dict[str, int]:
        """Анализирует синергии по аниме"""
        anime_counts = {}
        for card in cards:
            if card.anime:
                anime_counts[card.anime] = anime_counts.get(card.anime, 0) + 1

        synergies = {}
        for anime, count in anime_counts.items():
            if count >= 2:
                synergies[anime] = count
        return synergies

    def _apply_synergies(self, cards: List[BattleCard], synergies: Dict):
        """Применяет бонусы синергии к картам"""
        for card in cards:
            if card.anime in synergies:
                count = synergies[card.anime]
                # Бонус: +5% за каждую карту из того же аниме (макс +25%)
                bonus = 1.0 + (count - 1) * 0.05
                card.attack = int(card.attack * bonus)
                card.defense = int(card.defense * bonus)

    def calculate_damage(self, attacker: BattleCard, defender: BattleCard) -> Tuple[int, bool, bool]:
        """Рассчитывает урон"""
        # Базовая атака минус половина защиты
        damage = max(1, attacker.attack - defender.defense // 2)

        # Шанс критического удара (10% базовый)
        is_critical = random.random() < 0.1
        if is_critical:
            damage = int(damage * 1.5)

        # Шанс уклонения (5% базовый)
        is_dodged = random.random() < 0.05
        if is_dodged:
            damage = 0

        return damage, is_critical, is_dodged

    def next_turn(self) -> List[BattleAction]:
        """Выполняет следующий ход боя"""
        self.turn += 1
        turn_actions = []

        # Живые карты с обеих сторон
        user_alive = [c for c in self.user_cards if c.health > 0]
        opponent_alive = [c for c in self.opponent_cards if c.health > 0]

        if not user_alive or not opponent_alive:
            return turn_actions

        # Все живые карты атакуют в случайном порядке
        all_fighters = user_alive + opponent_alive
        random.shuffle(all_fighters)

        for attacker in all_fighters:
            if attacker.health <= 0:
                continue

            # Выбираем случайную цель из противоположной команды
            if attacker in user_alive:
                possible_targets = [c for c in opponent_alive if c.health > 0]
            else:
                possible_targets = [c for c in user_alive if c.health > 0]

            if not possible_targets:
                continue

            target = random.choice(possible_targets)

            # Рассчитываем урон
            damage, is_critical, is_dodged = self.calculate_damage(attacker, target)

            health_before = target.health
            if not is_dodged:
                target.health = max(0, target.health - damage)
            health_after = target.health

            # Записываем действие
            action = BattleAction(
                turn=self.turn,
                attacker_id=attacker.user_card_id,
                attacker_name=attacker.name,
                defender_id=target.user_card_id,
                defender_name=target.name,
                damage=damage if not is_dodged else 0,
                defender_health_before=health_before,
                defender_health_after=health_after,
                is_critical=is_critical,
                is_dodged=is_dodged
            )

            turn_actions.append(action)

        self.actions.extend(turn_actions)

        # Проверяем победителя
        user_alive = [c for c in self.user_cards if c.health > 0]
        opponent_alive = [c for c in self.opponent_cards if c.health > 0]

        if not user_alive:
            self.winner = "opponent"
        elif not opponent_alive:
            self.winner = "user"

        return turn_actions

    def get_battle_state(self) -> Dict:
        """Возвращает текущее состояние боя"""
        return {
            "turn": self.turn,
            "winner": self.winner,
            "user_cards": [
                {
                    "id": c.user_card_id,
                    "name": c.name,
                    "health": c.health,
                    "max_health": c.max_health,
                    "attack": c.attack,
                    "defense": c.defense,
                    "image_url": c.image_url,
                    "position": c.position,
                    "is_alive": c.health > 0,
                    "rarity": c.rarity,
                    "level": c.level
                }
                for c in self.user_cards
            ],
            "opponent_cards": [
                {
                    "id": c.user_card_id,
                    "name": c.name,
                    "health": c.health,
                    "max_health": c.max_health,
                    "attack": c.attack,
                    "defense": c.defense,
                    "image_url": c.image_url,
                    "position": c.position,
                    "is_alive": c.health > 0,
                    "rarity": c.rarity,
                    "level": c.level
                }
                for c in self.opponent_cards
            ],
            "synergies": {
                "user": self.user_synergies,
                "opponent": self.opponent_synergies
            }
        }