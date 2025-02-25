"""Dick command handlers"""
import random
from io import BytesIO
from typing import Any, Dict, Tuple

import matplotlib.pyplot as plt
import numpy as np
from pyrogram import Client, filters
from pyrogram.types import Message

from src.plugins.help import command_handler

# Message constants
NSFW_DISABLED = "❌ NSFW команды отключены в этом чате"
GENERAL_ERROR = "❌ Произошла ошибка! Попробуйте позже."

# Size categories
DICK_SIZE_CATEGORY = "Ниже среднего"
DICK_SIZE_SLIGHTLY_BELOW = "Чуть ниже среднего"
DICK_SIZE_AVERAGE = "Средний"
DICK_SIZE_ABOVE = "Выше среднего"
DICK_SIZE_SIGNIFICANTLY_ABOVE = "Значительно выше среднего"

# Satisfaction levels
DICK_SATISFACTION_POOR = "Сложно удовлетворить"
DICK_SATISFACTION_BELOW = "Ниже среднего"
DICK_SATISFACTION_AVERAGE = "Средний уровень удовлетворения"
DICK_SATISFACTION_ABOVE = "Выше среднего, хорошие шансы"
DICK_SATISFACTION_EXCELLENT = "Отличные шансы на удовлетворение"

# Constants
AVG_LENGTH_ERECT = 15
STD_LENGTH_ERECT = 1.66
AVG_GIRTH_ERECT = 12
STD_GIRTH_ERECT = 1.10
AVG_LENGTH_FLACCID = 9.5
STD_LENGTH_FLACCID = 1.57
AVG_GIRTH_FLACCID = 9.5
STD_GIRTH_FLACCID = 0.90


def calculate_dong_attributes(username: str) -> Dict[str, Any]:
    def generate_normal(avg: float, std: float, min_val: float, max_val: float) -> float:
        return max(min_val, min(max_val, random.gauss(avg, std)))

    length_erect = generate_normal(AVG_LENGTH_ERECT, STD_LENGTH_ERECT, 12, 25)
    girth_erect = generate_normal(AVG_GIRTH_ERECT, STD_GIRTH_ERECT, 8, 17)
    length_flaccid = generate_normal(AVG_LENGTH_FLACCID, STD_LENGTH_FLACCID, 5, 15)
    girth_flaccid = generate_normal(AVG_GIRTH_FLACCID, STD_GIRTH_FLACCID, 6, 13)

    volume_erect = np.pi * (girth_erect / (2 * np.pi)) ** 2 * length_erect
    volume_flaccid = np.pi * (girth_flaccid / (2 * np.pi)) ** 2 * length_flaccid

    size_categories = [
        (13, DICK_SIZE_CATEGORY),
        (14.9, DICK_SIZE_SLIGHTLY_BELOW),
        (17.1, DICK_SIZE_AVERAGE),
        (19, DICK_SIZE_ABOVE),
        (float("inf"), DICK_SIZE_SIGNIFICANTLY_ABOVE),
    ]
    size_category = next(category for threshold, category in size_categories if length_erect < threshold)

    rigidity = random.uniform(0, 100)
    stamina = random.uniform(1, 60)
    sensitivity = random.uniform(1, 10)

    satisfaction_rating, satisfaction_comment = calculate_satisfaction_rating(
        length_erect, girth_erect, rigidity, stamina, sensitivity
    )

    return {
        "username": username,
        "length_erect": length_erect,
        "girth_erect": girth_erect,
        "volume_erect": volume_erect,
        "length_flaccid": length_flaccid,
        "girth_flaccid": girth_flaccid,
        "volume_flaccid": volume_flaccid,
        "rigidity": rigidity,
        "curvature": random.uniform(-30, 30),
        "velocity": random.uniform(0, 30),
        "size_category": size_category,
        "stamina": stamina,
        "refractory_period": random.uniform(5, 120),
        "sensitivity": sensitivity,
        "satisfaction_rating": satisfaction_rating,
        "satisfaction_comment": satisfaction_comment,
    }


def calculate_satisfaction_rating(
        length: float, girth: float, rigidity: float, stamina: float, sensitivity: float
) -> Tuple[float, str]:
    length_score = min(max((length - 13) / 5, 0), 2)
    girth_score = min(max((girth - 10) / 3, 0), 2)
    rigidity_score = rigidity / 50
    stamina_score = min(stamina / 15, 2)
    sensitivity_score = 2 - abs(5 - sensitivity) / 2.5

    total_score = length_score + girth_score + rigidity_score + stamina_score + sensitivity_score
    rating = total_score / 10 * 100

    if rating < 20:
        comment = DICK_SATISFACTION_POOR
    elif rating < 40:
        comment = DICK_SATISFACTION_BELOW
    elif rating < 61:
        comment = DICK_SATISFACTION_AVERAGE
    elif rating < 80:
        comment = DICK_SATISFACTION_ABOVE
    else:
        comment = DICK_SATISFACTION_EXCELLENT

    return rating, comment


def plot_attributes(attributes: Dict[str, Any]) -> BytesIO:
    fig = plt.figure(figsize=(16, 16))
    fig.suptitle(f"Атрибуты пениса {attributes['username']}", fontsize=16)

    # Circular Radar plot
    ax_radar = fig.add_subplot(221, projection="polar")
    labels = ["Длина", "Обхват", "Жёсткость", "Выносливость", "Чувствительность", "Скорость", "Удовлетворение"]
    stats = [
        attributes["length_erect"],
        attributes["girth_erect"],
        attributes["rigidity"],
        attributes["stamina"],
        attributes["sensitivity"],
        attributes["velocity"],
        attributes["satisfaction_rating"],
    ]
    max_values = [25, 17, 100, 60, 10, 30, 100]
    stats = [stat / max_val * 10 for stat, max_val in zip(stats, max_values)]
    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False)
    stats = np.concatenate((stats, [stats[0]]))
    angles = np.concatenate((angles, [angles[0]]))

    ax_radar.plot(angles, stats, "o-", linewidth=2)
    ax_radar.fill(angles, stats, alpha=0.25)
    ax_radar.set_xticks(angles[:-1])
    ax_radar.set_xticklabels(labels)
    ax_radar.set_ylim(0, 10)
    ax_radar.set_title("Радар атрибутов")

    # Customize the radar plot
    ax_radar.set_theta_offset(np.pi / 2)
    ax_radar.set_theta_direction(-1)
    ax_radar.set_thetagrids(np.degrees(angles[:-1]), labels)
    for label, angle in zip(ax_radar.get_xticklabels(), angles):
        if angle in (0, np.pi):
            label.set_horizontalalignment("center")
        elif 0 < angle < np.pi:
            label.set_horizontalalignment("left")
        else:
            label.set_horizontalalignment("right")

    # Add circular gridlines
    ax_radar.set_yticks(range(1, 11))
    ax_radar.set_yticklabels([])
    ax_radar.set_rlabel_position(180 / len(labels))
    ax_radar.tick_params(colors="gray", axis="y", which="major", pad=10)
    for y in range(1, 11):
        ax_radar.text(np.deg2rad(180 / len(labels)), y, str(y), ha="center", va="center")

    # Histogram of length distribution
    ax_hist = fig.add_subplot(222)
    lengths = np.random.normal(AVG_LENGTH_ERECT, STD_LENGTH_ERECT, 1000)
    ax_hist.hist(lengths, bins=30, alpha=0.7, color="skyblue", edgecolor="black")
    ax_hist.axvline(attributes["length_erect"], color="red", linestyle="dashed", linewidth=2)
    ax_hist.set_xlabel("Длина (см)")
    ax_hist.set_ylabel("Частота")
    ax_hist.set_title("Распределение длины")

    # Scatter plot of length vs girth
    ax_scatter = fig.add_subplot(223)
    lengths = np.random.normal(AVG_LENGTH_ERECT, STD_LENGTH_ERECT, 1000)
    girths = np.random.normal(AVG_GIRTH_ERECT, STD_GIRTH_ERECT, 1000)
    ax_scatter.scatter(lengths, girths, alpha=0.5)
    ax_scatter.scatter(attributes["length_erect"], attributes["girth_erect"], color="red", s=100, marker="*")
    ax_scatter.set_xlabel("Длина (см)")
    ax_scatter.set_ylabel("Обхват (см)")
    ax_scatter.set_title("Длина vs Обхват")

    # Bar plot of satisfaction factors
    ax_bar = fig.add_subplot(224)
    factors = ["Длина", "Обхват", "Жёсткость", "Выносливость", "Чувствительность"]
    values = [
        min(max((attributes["length_erect"] - 13) / 5, 0), 2),
        min(max((attributes["girth_erect"] - 10) / 3, 0), 2),
        attributes["rigidity"] / 50,
        min(attributes["stamina"] / 15, 2),
        2 - abs(5 - attributes["sensitivity"]) / 2.5,
    ]
    ax_bar.bar(factors, values)
    ax_bar.set_ylim(0, 2)
    ax_bar.set_ylabel("Вклад в удовлетворение")
    ax_bar.set_title("Факторы удовлетворения")

    plt.tight_layout()

    # Create a BytesIO object to store the image
    image_buffer = BytesIO()
    fig.savefig(image_buffer, format="png")
    image_buffer.seek(0)
    plt.close(fig)

    return image_buffer


def create_report(attributes: Dict[str, Any]) -> str:
    def format_measurement(value: float) -> str:
        return f'{value:.2f} см ({value / 2.54:.2f}")'

    def get_rigidity_level(rigidity: float) -> str:
        return "🥔 Мягкий" if rigidity < 30 else "🥕 Средний" if rigidity < 70 else "🍆 Стальной"

    def get_curvature_description(curvature: float) -> str:
        return (
            "⬆️ Прямой"
            if abs(curvature) < 10
            else "↗️ Небольшой изгиб"
            if abs(curvature) < 20
            else "➰ Значительный изгиб"
        )

    def get_velocity_description(velocity: float) -> str:
        return "🐌 Слабая" if velocity < 10 else "🚀 Сильная" if velocity < 20 else "☄️ Убьёт"

    def get_stamina_description(stamina: float) -> str:
        return "⚡ Скорострел" if stamina < 10 else "🏃‍♂️ Марафонец" if stamina > 30 else "⏱️ Средний"

    def get_refractory_description(refractory_period: float) -> str:
        return (
            "🔄 Готов когда-угодно!"
            if refractory_period < 15
            else "😴 Нужен перерыв"
            if refractory_period > 60
            else "🔂 Можешь несколько раз"
        )

    def get_sensitivity_description(sensitivity: float) -> str:
        return (
            "🗿 Чувствую, как камень"
            if sensitivity < 3
            else "🎭 Сверхчувствительный"
            if sensitivity > 8
            else "😌 Комфортное"
        )

    report = f"""🍆 **Пенис {attributes['username']}** 🍆

📏 **Размеры**
  ├─ В эрекции:
  │  ├─ Длина: {format_measurement(attributes['length_erect'])}
  │  ├─ Обхват: {format_measurement(attributes['girth_erect'])}
  │  └─ Объём: {attributes['volume_erect']:.2f} см³
  │
  └─ В покое:
     ├─ Длина: {format_measurement(attributes['length_flaccid'])}
     ├─ Обхват: {format_measurement(attributes['girth_flaccid'])}
     └─ Объём: {attributes['volume_flaccid']:.2f} см³

🦸‍♂️ **Суперсилы**
  ├─ 💪 Твёрдость: {get_rigidity_level(attributes['rigidity'])} ({attributes['rigidity']:.2f}%)
  ├─ ↪️ Кривизна: {get_curvature_description(attributes['curvature'])} ({attributes['curvature']:.2f}°)
  ├─ 🚀 Скорость: {get_velocity_description(attributes['velocity'])} ({attributes['velocity']:.2f} км/ч)
  ├─ ⏱️ Выносливость: {get_stamina_description(attributes['stamina'])} ({attributes['stamina']:.2f} мин)
  ├─ 🔄 Восстановление: {get_refractory_description(attributes['refractory_period'])} ({attributes['refractory_period']:.2f} мин)
  └─ 🎭 Чувствительность: {get_sensitivity_description(attributes['sensitivity'])} ({attributes['sensitivity']:.2f}/10)

📊 **Статистика**
  ├─ 📏 Категория размера: {attributes['size_category']}
  └─ 😍 Рейтинг удовлетворения: {attributes['satisfaction_rating']:.2f}%
     └─ 💬 {attributes['satisfaction_comment']}
"""

    return report


@Client.on_message(filters.command(["dong", "penis", "dick"]), group=1)
@command_handler(
    commands=["dong", "penis", "dick"],
    description="Рассчитывает размер пениса пользователя",
    example="/dong или /dong @username",
    group="NSFW"
)
async def dong_command(client: Client, message: Message):
    """Рассчитывает (100% аккуратно) размер вашего члена"""
    try:
        username = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else (
                message.from_user.username or message.from_user.first_name
        )
        attributes = calculate_dong_attributes(username)
        image_buffer = plot_attributes(attributes)
        caption = create_report(attributes)

        await message.reply_photo(photo=image_buffer, caption=caption, quote=True)
    except Exception as e:
        await message.reply_text(text=GENERAL_ERROR, quote=True)
