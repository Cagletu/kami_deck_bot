# game/quiz_data.py - файл с вопросами
import random
import json
import os
from typing import List, Dict, Optional

# Структура вопроса
# {
#     "id": 1,
#     "question": "В каком аниме главного героя зовут Сатору Годжо?",
#     "options": ["Наруто", "Магическая битва", "Атака титанов", "Клинок, рассекающий демонов"],
#     "correct": 1,  # индекс правильного ответа (0-3)
#     "anime": "Магическая битва",
#     "difficulty": "easy",  # easy, medium, hard
#     "image_url": "https://example.com/image.jpg"  # опционально
# }

# База вопросов (можно расширять)
QUESTIONS = [
    {
        "id": 1,
        "question": "В каком аниме главного героя зовут Сатору Годжо?",
        "options": ["Наруто", "Магическая битва", "Атака титанов", "Клинок, рассекающий демонов"],
        "correct": 1,
        "anime": "Магическая битва",
        "difficulty": "easy"
    },
    {
        "id": 2,
        "question": "Как зовут главного героя аниме 'Тетрадь смерти'?",
        "options": ["Лайт Ягами", "Рюдзи", "Кира", "Л"],
        "correct": 0,
        "anime": "Тетрадь смерти",
        "difficulty": "easy"
    },
    {
        "id": 3,
        "question": "Из какого аниме этот персонаж: Какаши Хатаке?",
        "options": ["Наруто", "Блич", "Ван Пис", "Моя геройская академия"],
        "correct": 0,
        "anime": "Наруто",
        "difficulty": "easy"
    },
    {
        "id": 4,
        "question": "Какое аниме повествует о пиратах, ищущих легендарное сокровище?",
        "options": ["Наруто", "Блич", "Ван Пис", "Драконий жемчуг"],
        "correct": 2,
        "anime": "Ван Пис",
        "difficulty": "easy"
    },
    {
        "id": 5,
        "question": "Как называется аниме о парне, который может превращаться в титана?",
        "options": ["Атака титанов", "Токийский гуль", "Паразит", "Демон-убийца"],
        "correct": 0,
        "anime": "Атака титанов",
        "difficulty": "easy"
    },
    {
        "id": 6,
        "question": "Кто автор манги 'Стальной алхимик'?",
        "options": ["Хирому Аракава", "Эйитиро Ода", "Масаси Кисимото", "Тиаки Конно"],
        "correct": 0,
        "anime": "Стальной алхимик",
        "difficulty": "medium"
    },
    {
        "id": 7,
        "question": "В каком году вышло аниме 'Ковбой Бибоп'?",
        "options": ["1995", "1998", "2001", "2004"],
        "correct": 1,
        "anime": "Ковбой Бибоп",
        "difficulty": "hard"
    },
    {
        "id": 8,
        "question": "Как зовут бога смерти в 'Тетради смерти'?",
        "options": ["Рюк", "Рем", "Сидо", "Арамония"],
        "correct": 0,
        "anime": "Тетрадь смерти",
        "difficulty": "easy"
    },
    {
        "id": 9,
        "question": "Из какого аниме персонаж по имени Кеншин Химура?",
        "options": ["Rurouni Kenshin", "Samurai Champloo", "Gintama", "Бродяга Кэнсин"],
        "correct": 3,
        "anime": "Бродяга Кэнсин",
        "difficulty": "medium"
    },
    {
        "id": 10,
        "question": "Как называется аниме о парне, который после смерти перерождается в мире мечей и магии?",
        "options": ["Re:Zero", "Sword Art Online", "Этот замечательный мир!", "Повелитель"],
        "correct": 1,
        "anime": "Sword Art Online",
        "difficulty": "easy"
    },
    {
        "id": 11,
        "question": "Какую технику использует Наруто в битве с Пейном?",
        "options": ["Расенган", "Чидори", "Режим мудреца", "Демонический луч"],
        "correct": 2,
        "anime": "Наруто",
        "difficulty": "medium"
    },
    {
        "id": 12,
        "question": "В каком аниме фигурирует фраза 'Я нанял этого человека'?",
        "options": ["Наруто", "Ван Пис", "Тетрадь смерти", "Клинок, рассекающий демонов"],
        "correct": 1,
        "anime": "Ван Пис",
        "difficulty": "hard"
    },
    {
        "id": 13,
        "question": "Какой титул носит Л в 'Тетради смерти'?",
        "options": ["Величайший детектив мира", "L", "Рюдзаки", "Все ответы верны"],
        "correct": 3,
        "anime": "Тетрадь смерти",
        "difficulty": "medium"
    },
    {
        "id": 14,
        "question": "Из какого аниме персонаж Ичиго Куросаки?",
        "options": ["Наруто", "Блич", "Ван Пис", "Моя геройская академия"],
        "correct": 1,
        "anime": "Блич",
        "difficulty": "easy"
    },
    {
        "id": 15,
        "question": "Как зовут главного героя 'Клинка, рассекающего демонов'?",
        "options": ["Танджиро Камадо", "Зеницу Агацума", "Иносуке Хашибира", "Гию Томиока"],
        "correct": 0,
        "anime": "Клинок, рассекающий демонов",
        "difficulty": "easy"
    },
    {
        "id": 16,
        "question": "В каком аниме есть персонаж по имени Лайт Ягами?",
        "options": ["Наруто", "Тетрадь смерти", "Атака титанов", "Токийский гуль"],
        "correct": 1,
        "anime": "Тетрадь смерти",
        "difficulty": "easy"
    },
    {
        "id": 17,
        "question": "Какой фрукт съел Монки Д. Луффи?",
        "options": ["Гому Гому но Ми", "Мера Мера но Ми", "Хито Хито но Ми", "Суке Суке но Ми"],
        "correct": 0,
        "anime": "Ван Пис",
        "difficulty": "easy"
    },
    {
        "id": 18,
        "question": "Из какого аниме персонаж Себастьян Михаэлис?",
        "options": ["Темный дворецкий", "Хеллсинг", "D.Gray-man", "Trinity Blood"],
        "correct": 0,
        "anime": "Темный дворецкий",
        "difficulty": "medium"
    },
    {
        "id": 19,
        "question": "Как называется аниме о людях, которые могут превращаться в шинигами?",
        "options": ["Блич", "Тетрадь смерти", "Хеллсинг", "Шаман Кинг"],
        "correct": 0,
        "anime": "Блич",
        "difficulty": "medium"
    },
    {
        "id": 20,
        "question": "Кто такой Аллен Уокер?",
        "options": ["Экзорцист из D.Gray-man", "Охотник из Хеллсинга", "Шинигами из Блича", "Демон из Клинка"],
        "correct": 0,
        "anime": "D.Gray-man",
        "difficulty": "hard"
    },
    {
        "id": 21,
        "question": "Как зовут главного героя 'Моей геройской академии'?",
        "options": ["Изуку Мидория", "Кацуки Бакуго", "Сесто Тодороки", "Олл Майт"],
        "correct": 0,
        "anime": "Моя геройская академия",
        "difficulty": "easy"
    },
    {
        "id": 22,
        "question": "Из какого аниме персонаж Кен Канеки?",
        "options": ["Токийский гуль", "Паразит", "Демон-убийца", "Атака титанов"],
        "correct": 0,
        "anime": "Токийский гуль",
        "difficulty": "easy"
    },
    {
        "id": 23,
        "question": "Как называется аниме, где главный герой застрял в временной петле?",
        "options": ["Re:Zero", "Steins;Gate", "Врата Штейна", "Оба варианта A и B"],
        "correct": 3,
        "anime": "Re:Zero / Steins;Gate",
        "difficulty": "medium"
    },
    {
        "id": 24,
        "question": "В каком аниме появляется персонаж по имени Лэлуш Ламперуж?",
        "options": ["Код Гиас", "Гуррен-Лаганн", "Евангелион", "Darker than Black"],
        "correct": 0,
        "anime": "Код Гиас",
        "difficulty": "medium"
    },
    {
        "id": 25,
        "question": "Какой вид спорта является основой аниме 'Куроко не играет в баскетбол'?",
        "options": ["Баскетбол", "Волейбол", "Футбол", "Теннис"],
        "correct": 0,
        "anime": "Куроко не играет в баскетбол",
        "difficulty": "easy"
    },
    {
        "id": 26,
        "question": "Из какого аниме фраза 'Я — гений'?",
        "options": ["Куроко не играет в баскетбол", "Хайкю!", "Большой куш", "Гигантский удар"],
        "correct": 0,
        "anime": "Куроко не играет в баскетбол",
        "difficulty": "hard"
    },
    {
        "id": 27,
        "question": "В каком аниме есть персонаж по имени Широ?",
        "options": ["No Game No Life", "Log Horizon", "Sword Art Online", "Overlord"],
        "correct": 0,
        "anime": "No Game No Life",
        "difficulty": "medium"
    },
    {
        "id": 28,
        "question": "Как зовут автора манги 'Наруто'?",
        "options": ["Масаси Кисимото", "Эйитиро Ода", "Тиэко Като", "Хирому Аракава"],
        "correct": 0,
        "anime": "Наруто",
        "difficulty": "easy"
    },
    {
        "id": 29,
        "question": "Из какого аниме персонаж Саито Хираага?",
        "options": ["Zero no Tsukaima", "Shakugan no Shana", "Infinite Stratos", "High School DxD"],
        "correct": 0,
        "anime": "Zero no Tsukaima",
        "difficulty": "hard"
    },
    {
        "id": 30,
        "question": "Какой цвет волос у главного героя 'Атаки титанов'?",
        "options": ["Коричневый", "Черный", "Блондин", "Рыжий"],
        "correct": 1,
        "anime": "Атака титанов",
        "difficulty": "easy"
    }
]

class QuizManager:
    """Менеджер для работы с вопросами викторины"""

    def __init__(self):
        self.questions = QUESTIONS
        self.questions_by_difficulty = {
            "easy": [q for q in self.questions if q["difficulty"] == "easy"],
            "medium": [q for q in self.questions if q["difficulty"] == "medium"],
            "hard": [q for q in self.questions if q["difficulty"] == "hard"]
        }

    def get_random_question(self, difficulty: str = None) -> Dict:
        """Получить случайный вопрос"""
        if difficulty and difficulty in self.questions_by_difficulty:
            questions = self.questions_by_difficulty[difficulty]
            if questions:
                return random.choice(questions)

        # Если сложность не указана или нет вопросов, берем любой
        return random.choice(self.questions)

    def get_question_by_id(self, qid: int) -> Optional[Dict]:
        """Получить вопрос по ID"""
        for q in self.questions:
            if q["id"] == qid:
                return q
        return None

    def get_random_questions(self, count: int = 5, difficulty: str = None) -> List[Dict]:
        """Получить несколько случайных вопросов"""
        questions_pool = self.questions
        if difficulty and difficulty in self.questions_by_difficulty:
            questions_pool = self.questions_by_difficulty[difficulty]

        if len(questions_pool) <= count:
            return questions_pool.copy()

        return random.sample(questions_pool, count)


quiz_manager = QuizManager()


# Награды за викторину
QUIZ_REWARDS = {
    "easy": {
        "coins": 10,
        "dust": 50,
        "xp": 5
    },
    "medium": {
        "coins": 25,
        "dust": 100,
        "xp": 10
    },
    "hard": {
        "coins": 50,
        "dust": 150,
        "xp": 20
    },
    "perfect": {  # Бонус за все правильные ответы
        "coins": 25,
        "dust": 100,
        "xp": 15
    }
}