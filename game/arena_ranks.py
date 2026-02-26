# game/arena_ranks.py

from typing import Dict, Tuple, Optional

# Ранги арены
ARENA_RANKS = [
    {"name": "Бронза V", "min_rating": 0, "max_rating": 199, "color": "🟤", "emoji": "🪙"},
    {"name": "Бронза IV", "min_rating": 200, "max_rating": 399, "color": "🟤", "emoji": "🪙"},
    {"name": "Бронза III", "min_rating": 400, "max_rating": 599, "color": "🟤", "emoji": "🪙"},
    {"name": "Бронза II", "min_rating": 600, "max_rating": 799, "color": "🟤", "emoji": "🪙"},
    {"name": "Бронза I", "min_rating": 800, "max_rating": 999, "color": "🟤", "emoji": "🪙"},

    {"name": "Серебро V", "min_rating": 1000, "max_rating": 1199, "color": "⚪", "emoji": "🥈"},
    {"name": "Серебро IV", "min_rating": 1200, "max_rating": 1399, "color": "⚪", "emoji": "🥈"},
    {"name": "Серебро III", "min_rating": 1400, "max_rating": 1599, "color": "⚪", "emoji": "🥈"},
    {"name": "Серебро II", "min_rating": 1600, "max_rating": 1799, "color": "⚪", "emoji": "🥈"},
    {"name": "Серебро I", "min_rating": 1800, "max_rating": 1999, "color": "⚪", "emoji": "🥈"},

    {"name": "Золото V", "min_rating": 2000, "max_rating": 2199, "color": "🟡", "emoji": "🥇"},
    {"name": "Золото IV", "min_rating": 2200, "max_rating": 2399, "color": "🟡", "emoji": "🥇"},
    {"name": "Золото III", "min_rating": 2400, "max_rating": 2599, "color": "🟡", "emoji": "🥇"},
    {"name": "Золото II", "min_rating": 2600, "max_rating": 2799, "color": "🟡", "emoji": "🥇"},
    {"name": "Золото I", "min_rating": 2800, "max_rating": 2999, "color": "🟡", "emoji": "🥇"},

    {"name": "Платина V", "min_rating": 3000, "max_rating": 3199, "color": "🔵", "emoji": "💎"},
    {"name": "Платина IV", "min_rating": 3200, "max_rating": 3399, "color": "🔵", "emoji": "💎"},
    {"name": "Платина III", "min_rating": 3400, "max_rating": 3599, "color": "🔵", "emoji": "💎"},
    {"name": "Платина II", "min_rating": 3600, "max_rating": 3799, "color": "🔵", "emoji": "💎"},
    {"name": "Платина I", "min_rating": 3800, "max_rating": 3999, "color": "🔵", "emoji": "💎"},

    {"name": "Алмаз V", "min_rating": 4000, "max_rating": 4199, "color": "💠", "emoji": "💎"},
    {"name": "Алмаз IV", "min_rating": 4200, "max_rating": 4399, "color": "💠", "emoji": "💎"},
    {"name": "Алмаз III", "min_rating": 4400, "max_rating": 4599, "color": "💠", "emoji": "💎"},
    {"name": "Алмаз II", "min_rating": 4600, "max_rating": 4799, "color": "💠", "emoji": "💎"},
    {"name": "Алмаз I", "min_rating": 4800, "max_rating": 4999, "color": "💠", "emoji": "💎"},

    {"name": "Мастер", "min_rating": 5000, "max_rating": 5499, "color": "🔴", "emoji": "👑"},
    {"name": "Грандмастер", "min_rating": 5500, "max_rating": 5999, "color": "🔴", "emoji": "👑"},
    {"name": "Легенда", "min_rating": 6000, "max_rating": 6999, "color": "🟣", "emoji": "👑"},
    {"name": "Мифический", "min_rating": 7000, "max_rating": 8499, "color": "🟣", "emoji": "👑"},
    {"name": "Божественный", "min_rating": 8500, "max_rating": 9999, "color": "✨", "emoji": "👑"},
    {"name": "✧ Бессмертный ✧", "min_rating": 10000, "max_rating": 99999, "color": "🌟", "emoji": "🏆"},
]


def get_rank(rating: int) -> Dict:
    """Получить ранг по рейтингу"""
    for rank in ARENA_RANKS:
        if rank["min_rating"] <= rating <= rank["max_rating"]:
            return rank
    return ARENA_RANKS[-1]  # Если рейтинг выше максимального


def calculate_rating_change(player_rating: int, opponent_rating: int, is_win: bool) -> int:
    """
    Рассчитывает изменение рейтинга в зависимости от разницы рангов

    Формула: база ± (разница_рейтинга / 50) с ограничениями
    """
    base_win = 20
    base_lose = -15

    rating_diff = player_rating - opponent_rating

    if is_win:
        # Победа над более сильным = больше рейтинга
        # Победа над более слабым = меньше рейтинга
        if rating_diff < 0:  # Противник сильнее
            bonus = min(15, abs(rating_diff) // 30)
            change = base_win + bonus
        else:  # Противник слабее
            penalty = min(10, rating_diff // 40)
            change = max(10, base_win - penalty)
    else:
        # Поражение от более слабого = больше потерь
        # Поражение от более сильного = меньше потерь
        if rating_diff > 0:  # Мы были сильнее, но проиграли
            penalty = min(15, rating_diff // 30)
            change = base_lose - penalty
        else:  # Проиграли более сильному
            bonus = min(10, abs(rating_diff) // 40)
            change = base_lose + bonus

    # Для тестовой колоды фиксированные значения
    if opponent_rating == 1000:  # Базовая тестовая колода
        return base_win if is_win else base_lose

    return int(change)


def get_rank_display(rating: int) -> str:
    """Получить отображение ранга для интерфейса"""
    rank = get_rank(rating)
    return f"{rank['emoji']} {rank['name']}"


def get_next_rank_progress(rating: int) -> Tuple[int, int, float]:
    """Получить прогресс до следующего ранга"""
    current_rank = get_rank(rating)

    # Ищем следующий ранг
    next_rank = None
    for rank in ARENA_RANKS:
        if rank["min_rating"] > current_rank["min_rating"]:
            next_rank = rank
            break

    if next_rank:
        needed = next_rank["min_rating"] - rating
        total = next_rank["min_rating"] - current_rank["min_rating"]
        progress = (rating - current_rank["min_rating"]) / (next_rank["min_rating"] - current_rank["min_rating"]) * 100
        return needed, total, progress

    return 0, 0, 100  # Максимальный ранг