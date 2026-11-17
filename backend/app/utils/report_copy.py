"""The words on a person's analytics pictures — the report receipt and the
year's stories — in every language the app speaks."""
from app.utils.bot_copy import resolve_language
from app.utils.currency import format_number

MONTHS = {
    "ru": ("январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"),
    "uz": ("yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
}
SHORT_MONTHS = {
    "ru": ("янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"),
    "uz": ("yan", "fev", "mar", "apr", "may", "iyn", "iyl", "avg", "sen", "okt", "noy", "dek"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}
WEEKDAYS = {
    "ru": ("пн", "вт", "ср", "чт", "пт", "сб", "вс"),
    "uz": ("du", "se", "cho", "pa", "ju", "sha", "ya"),
    "en": ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"),
}

# Uzbek counts things with «ta» between the number and the noun — «3 ta
# hisob» — but not times: «3 marta».
_COUNTERS = {"uz": {"bills": "ta", "people": "ta"}}

# A noun after a number: Russian's one, few and many; Uzbek does not change
# the noun; English's one and other.
_NOUNS = {
    "ru": {"bills": ("счёт", "счёта", "счетов"), "times": ("раз", "раза", "раз"), "people": ("человек", "человека", "человек")},
    "uz": {"bills": ("hisob",), "times": ("marta",), "people": ("kishi",)},
    "en": {"bills": ("bill", "bills"), "times": ("time", "times"), "people": ("person", "people")},
}

_COPY: dict[str, dict[str, str]] = {
    "ru": {
        "report_month": "Отчёт за {month} {year}",
        "report_year": "Отчёт за {year} год",
        "report_all": "Отчёт за всё время",
        "bills": "Счетов",
        "owned": "ваших",
        "joined": "чужих",
        "spent": "Потрачено",
        "average": "Средний счёт",
        "biggest": "Самый дорогой",
        "by_month": "По месяцам",
        "by_year": "По годам",
        "by_weekday": "По дням недели",
        "people": "За столом с вами",
        "fastest": "Быстрее всех платит {name} — {wait}",
        "dishes": "Чаще всего заказывали",
        "champion": "Чемпион: {kind}",
        "champion_often": "чаще — {dish} ×{count}",
        "champion_priciest": "дороже — {dish}, {price}",
        "places": "Любимые места",
        "badges": "Ваши бейджи",
        "total": "Итого",
        "other_currency": "и ещё {count} в другой валюте",
        "thanks": "Спасибо, что делите честно",
        "minutes": "{count} мин",
        "hours": "{count} ч",
        "days": "{count} дн.",
        "thousands": "{count} тыс.",
        "millions": "{count} млн",
        "group_food": "еда",
        "group_drink": "напитки",
        "group_dessert": "десерты",
        "group_alcohol": "алкоголь",
        "group_fee": "обслуживание",
        "group_other": "другое",
        "badge_coffee_lover": "Кофеман",
        "badge_meat_lover": "Мясоед",
        "badge_regular": "Завсегдатай",
        "badge_night_owl": "Сова",
        "badge_treasurer": "Казначей",
        "badge_social": "Заводила",
        "badge_fast_payer": "Молния",
        "story_bills_lead": "В этом году вы разделили",
        "story_spent": "{currency} — ваша часть",
        "story_people": "{people} за столом",
        "story_dish_lead": "Ваше блюдо года",
        "story_dish_priciest": "Самый дорогой — {dish}, {price}.",
        "story_person_lead": "Ваш человек года",
        "story_together": "{bills} вместе",
        "story_invited": "вы приглашали",
        "story_invited_me": "приглашали вас",
        "story_paid_me": "перевели вам",
        "story_more_people": "Ещё за вашим столом: {people}.",
        "story_footer": "Делите счёт честно — в Split·Bill",
        "story_caption": "Мои итоги {year} в Split·Bill",
        "share_caption": "{report} — Split·Bill",
    },
    "uz": {
        "report_month": "{year}-yil {month} hisoboti",
        "report_year": "{year}-yil hisoboti",
        "report_all": "Butun vaqt hisoboti",
        "bills": "Hisoblar",
        "owned": "sizniki",
        "joined": "boshqalarniki",
        "spent": "Sarflandi",
        "average": "O‘rtacha hisob",
        "biggest": "Eng qimmati",
        "by_month": "Oylar bo‘yicha",
        "by_year": "Yillar bo‘yicha",
        "by_weekday": "Hafta kunlari bo‘yicha",
        "people": "Dasturxoningizda",
        "fastest": "Eng tez to‘laydi: {name} — {wait}",
        "dishes": "Eng ko‘p buyurtmalar",
        "champion": "Chempion: {kind}",
        "champion_often": "eng ko‘p — {dish} ×{count}",
        "champion_priciest": "eng qimmat — {dish}, {price}",
        "places": "Sevimli joylar",
        "badges": "Nishonlaringiz",
        "total": "Jami",
        "other_currency": "yana {count} boshqa valyutada",
        "thanks": "Halol bo‘lishganingiz uchun rahmat",
        "minutes": "{count} daq",
        "hours": "{count} soat",
        "days": "{count} kun",
        "thousands": "{count} ming",
        "millions": "{count} mln",
        "group_food": "taomlar",
        "group_drink": "ichimliklar",
        "group_dessert": "desertlar",
        "group_alcohol": "alkogol",
        "group_fee": "xizmat haqi",
        "group_other": "boshqa",
        "badge_coffee_lover": "Qahvaxo‘r",
        "badge_meat_lover": "Go‘shtxo‘r",
        "badge_regular": "Qadrdon",
        "badge_night_owl": "Boyqush",
        "badge_treasurer": "Xazinachi",
        "badge_social": "Davra joni",
        "badge_fast_payer": "Chaqmoq",
        "story_bills_lead": "Bu yil siz bo‘lishdingiz",
        "story_spent": "{currency} — ulushingiz",
        "story_people": "{people} dasturxoningizda",
        "story_dish_lead": "Yilning taomi",
        "story_dish_priciest": "Eng qimmati — {dish}, {price}.",
        "story_person_lead": "Yilning odami",
        "story_together": "birga {bills}",
        "story_invited": "siz chaqirdingiz",
        "story_invited_me": "sizni chaqirdi",
        "story_paid_me": "sizga o‘tkazdi",
        "story_more_people": "Dasturxoningizda yana: {people}.",
        "story_footer": "Hisobni halol bo‘ling — Split·Bill’da",
        "story_caption": "Split·Bill’dagi {year}-yil yakunlarim",
        "share_caption": "{report} — Split·Bill",
    },
    "en": {
        "report_month": "Report for {month} {year}",
        "report_year": "Report for {year}",
        "report_all": "All-time report",
        "bills": "Bills",
        "owned": "yours",
        "joined": "others’",
        "spent": "Spent",
        "average": "Average bill",
        "biggest": "Priciest",
        "by_month": "By month",
        "by_year": "By year",
        "by_weekday": "By weekday",
        "people": "At your table",
        "fastest": "Fastest to pay: {name} — {wait}",
        "dishes": "Ordered most",
        "champion": "Champion: {kind}",
        "champion_often": "most — {dish} ×{count}",
        "champion_priciest": "priciest — {dish}, {price}",
        "places": "Favourite places",
        "badges": "Your badges",
        "total": "Total",
        "other_currency": "and {count} in other currencies",
        "thanks": "Thanks for splitting fair",
        "minutes": "{count} min",
        "hours": "{count} h",
        "days": "{count} d",
        "thousands": "{count}K",
        "millions": "{count}M",
        "group_food": "food",
        "group_drink": "drinks",
        "group_dessert": "desserts",
        "group_alcohol": "alcohol",
        "group_fee": "service",
        "group_other": "other",
        "badge_coffee_lover": "Coffee lover",
        "badge_meat_lover": "Meat eater",
        "badge_regular": "Regular",
        "badge_night_owl": "Night owl",
        "badge_treasurer": "Treasurer",
        "badge_social": "Party star",
        "badge_fast_payer": "Lightning",
        "story_bills_lead": "This year you split",
        "story_spent": "{currency} — your share",
        "story_people": "{people} at your table",
        "story_dish_lead": "Your dish of the year",
        "story_dish_priciest": "The priciest — {dish}, {price}.",
        "story_person_lead": "Your person of the year",
        "story_together": "{bills} together",
        "story_invited": "you invited",
        "story_invited_me": "invited you",
        "story_paid_me": "paid you",
        "story_more_people": "Also at your table: {people}.",
        "story_footer": "Split the bill fair — in Split·Bill",
        "story_caption": "My {year} in Split·Bill",
        "share_caption": "{report} — Split·Bill",
    },
}


class ReportCopy:
    """The pictures' words in one language."""

    def __init__(self, language: str | None):
        self.language = resolve_language(language)

    def __call__(self, key: str, **values) -> str:
        return _COPY[self.language][key].format(**values)

    def noun(self, count: int, noun: str) -> str:
        """The noun as it reads after `count`: «2 счёта», «5 счетов»."""
        forms = _NOUNS[self.language][noun]
        if self.language == "ru":
            tens, units = count % 100, count % 10
            if units == 1 and tens != 11:
                return forms[0]
            if 2 <= units <= 4 and not 12 <= tens <= 14:
                return forms[1]
            return forms[2]
        if self.language == "en":
            return forms[0] if count == 1 else forms[1]
        return forms[0]

    def counted(self, count: int, noun: str) -> str:
        counter = _COUNTERS.get(self.language, {}).get(noun)
        return " ".join(part for part in (str(count), counter, self.noun(count, noun)) if part)

    def month(self, month: int) -> str:
        return MONTHS[self.language][month - 1]

    def short_month(self, month: int) -> str:
        return SHORT_MONTHS[self.language][month - 1]

    def weekdays(self) -> tuple[str, ...]:
        return WEEKDAYS[self.language]

    def wait(self, minutes: int) -> str:
        """«12 мин», «2 ч», «1,5 дн.» — the way the app says how long a payment took."""
        if minutes < 60:
            return self("minutes", count=max(1, minutes))
        if minutes < 24 * 60:
            return self("hours", count=_one_decimal(minutes / 60, self.language))
        return self("days", count=_one_decimal(minutes / (24 * 60), self.language))


    def compact(self, amount: float) -> str:
        """A big sum said short, for a story: «7,4 млн», «703 тыс.»."""
        if amount >= 1_000_000:
            return self("millions", count=_one_decimal(amount / 1_000_000, self.language))
        if amount >= 10_000:
            return self("thousands", count=round(amount / 1000))
        return format_number(round(amount) * 100)


def _one_decimal(value: float, language: str) -> str:
    text = f"{round(value, 1):g}"
    return text if language == "en" else text.replace(".", ",")
