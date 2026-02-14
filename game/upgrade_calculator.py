from database.models.card import Card
from game.constants import (
    POWER_GROWTH,
    HEALTH_GROWTH,
    ATTACK_GROWTH,
    DEFENSE_GROWTH,
    RARITY_BONUS,
    RARITY_GROWTH_BONUS,
    TEN_LEVEL_BONUS,
    DUST_PER_RARITY,
    UPGRADE_COST_PER_LEVEL
)


def calculate_stats_for_level(card: Card, level: int) -> dict:
    """Рассчитать характеристики карты для указанного уровня"""

    # Базовые характеристики
    base_power = card.base_power or 100
    base_health = card.base_health or 100
    base_attack = card.base_attack or 10
    base_defense = card.base_defense or 10

    # Множитель за уровень (экспоненциальный рост)
    power = int(base_power * (POWER_GROWTH ** (level - 1)))
    health = int(base_health * (HEALTH_GROWTH ** (level - 1)))
    attack = int(base_attack * (ATTACK_GROWTH ** (level - 1)))
    defense = int(base_defense * (DEFENSE_GROWTH ** (level - 1)))

    # Скрытый бонус роста по редкости
    rarity_growth = RARITY_GROWTH_BONUS.get(card.rarity, 1.0)
    power *= (rarity_growth ** (level - 1))
    health *= (rarity_growth ** (level - 1))
    attack *= (rarity_growth ** (level - 1))
    defense *= (rarity_growth ** (level - 1))

    # Бонус каждые 10 уровней (одинаковый для всех)
    ten_level_steps = (level - 1) // 10
    if ten_level_steps > 0:
        bonus_mult = TEN_LEVEL_BONUS ** ten_level_steps
        power *= bonus_mult
        health *= bonus_mult
        attack *= bonus_mult
        defense *= bonus_mult
    
    # Бонус за редкость
    rarity_mult = RARITY_BONUS.get(card.rarity, 1.0)
    power = int(power * rarity_mult)
    health = int(health * rarity_mult)
    attack = int(attack * rarity_mult)
    defense = int(defense * rarity_mult)

    return {
        'power': int(power),
        'health': int(health),
        'attack': int(attack),
        'defense': int(defense)
    }


def get_upgrade_cost(card: Card, current_level: int) -> int:
    """Получить стоимость улучшения карты"""
    rarity_cost = DUST_PER_RARITY.get(card.rarity, 15)
    cost = rarity_cost * (current_level + 1) * UPGRADE_COST_PER_LEVEL

    # Первые 10 уровней дешевле (приятный UX)
    if current_level < 10:
        cost = int(cost * 0.5)
    
    return cost
    