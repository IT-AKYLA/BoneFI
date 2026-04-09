# BoneFi — Solana Token Intelligence Platform

<div align="center">
  <img src="https://img.shields.io/badge/Solana-14f195?style=for-the-badge&logo=solana&logoColor=black"/>
  <img src="https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python"/>
  <img src="https://img.shields.io/badge/FastAPI-0.104-teal?style=for-the-badge&logo=fastapi"/>
  <br>
  <strong>Аналитическая платформа для токенов Solana с фокусом на малую и среднюю капитализацию</strong>
</div>

---

## О платформе

BoneFi — это специализированная аналитическая платформа для глубокого анализа Solana-токенов. Мы фокусируемся на токенах с небольшой и средней капитализацией, где традиционные инструменты часто бессильны из-за недостатка данных или специфики ончейн-активности.

**Основная задача** — максимально автоматизировать сбор и анализ ончейн-данных, чтобы предоставить трейдерам и исследователям объективную картину: кто реально держит токен, есть ли боты, как ведут себя инсайдеры и насколько высока вероятность скама.

Платформа построена на микросервисной архитектуре и состоит из трёх независимых компонентов:
- **Data Management** — сбор и хранение данных 
- **Data Analysis** — аналитика, оценка рисков
- **Client Management** — веб-интерфейс 

---

## Ключевые возможности

### Сбор данных
- Автоматический сбор транзакций через Solana RPC
- Поддержка WARP proxy для обхода ограничений
- Асинхронная обработка до 100к+ транзакций
- Оптимизация данных для аналитики

### Детекция ботов и манипуляций
| Тип | Что обнаруживаем |
|-----|------------------|
| **Бот-кластеры** | Кошельки, созданные массово в одно время |
| **Инсайдеры** | Кошельки, купившие в первые 5 минут |
| **Снайперы** | Кошельки, профинансированные создателем |
| **Координация** | Синхронные действия (3+ за 10 секунд) |
| **Вош-трейдинг** | Искусственная накрутка объёма |
| **Роботические паттерны** | Повторяющиеся суммы, идеальные интервалы |

### Метрики риска
- **MSI (Malicious Supply Index)** — процент supply под вредными ботами
- **Temporal Entropy** — измерение естественности временных паттернов
- **Anti-Fragmentation** — выявление фейковых холдеров
- **Domino Effect** — детекция скоординированных дампов
- **Migration Footprint** — анализ поведения ранних холдеров
- **Herding Index** — обнаружение армий ботов

### Визуализация
- **BubbleMap** — интерактивная карта распределения холдеров 
- **Activity Chart** — комбинированный график транзакций и объёмов
- **Топ-холдеры** — таблицы с классификацией 

---

## Быстрый старт

```bash
# Клонирование
git clone https://github.com/IT-AKYLA/bonefi-analyzer-platform.git
cd bonefi-analyzer-platform

# Виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Установка зависимостей
pip install -r requirements.txt
cd backend/data-analysis && pip install -r requirements.txt
cd ../data-management && pip install -r requirements.txt

# Запуск Redis
docker run -d -p 6379:6379 redis:7-alpine

# Запуск сервисов
cd backend/data-management && python run_api.py   # порт 8001
cd backend/data-analysis && python run_api.py     # порт 8000

# Открыть веб-интерфейс
open frontend/client-management/BoneFI.html