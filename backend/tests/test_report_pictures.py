"""A person's analytics drawn to share: the report receipt for any period, the
year's stories, and the words on them in each language."""
import io
from datetime import date

from PIL import Image
from sqlmodel import Session

from app.models import User
from app.schemas.analytics_schemas import Badge
from app.services.analytics import AnalyticsService, Period, PeriodKind
from app.services.report_card import WIDTH, render_report
from app.services.story_cards import Story, render_story, stories_for
from app.utils.report_copy import ReportCopy
from tests.analytics_world import NOW

YEAR = Period(PeriodKind.YEAR, 2026)
SEPTEMBER = Period(PeriodKind.MONTH, 2026, 9)


def _size(jpeg: bytes) -> tuple[int, int]:
    picture = Image.open(io.BytesIO(jpeg))
    assert picture.format == "JPEG"
    return picture.size


def _analytics(session: Session, world, period: Period):
    return AnalyticsService(session).for_user(world["me"], period, NOW)


def test_the_receipt_is_a_long_jpeg_for_any_period(session: Session, world):
    for period in (SEPTEMBER, YEAR, Period(PeriodKind.ALL)):
        data = _analytics(session, world, period)
        for theme in ("light", "dark"):
            width, height = _size(render_report(data, period, "Leonid", "ru", date(2026, 10, 3), theme))
            assert width == WIDTH
            assert height > 2 * width


def test_someone_with_no_bills_still_gets_a_receipt(session: Session):
    newcomer = User(telegram_id=99, name="Новичок")
    session.add(newcomer)
    session.commit()
    data = AnalyticsService(session).for_user(newcomer, Period(PeriodKind.ALL), NOW)

    assert _size(render_report(data, Period(PeriodKind.ALL), "Новичок", "ru", date(2026, 10, 3)))[0] == WIDTH
    assert stories_for(data) == []


def test_badges_lengthen_the_receipt(session: Session, world):
    data = _analytics(session, world, YEAR)
    plain = _size(render_report(data, YEAR, "Leonid", "en", date(2026, 10, 3)))[1]
    data.badges = [Badge(key=key, value=12) for key in ("coffee_lover", "treasurer", "night_owl", "social", "fast_payer")]

    assert _size(render_report(data, YEAR, "Leonid", "en", date(2026, 10, 3)))[1] > plain


def test_a_year_tells_the_stories_it_has_enough_for(session: Session, world):
    data = _analytics(session, world, YEAR)

    assert stories_for(data) == [Story.BILLS, Story.DISH, Story.PERSON]
    for story in stories_for(data):
        assert _size(render_story(story, data, 2026, "uz")) == (1080, 1920)

    data.food.top, data.people.companions = [], []
    assert stories_for(data) == [Story.BILLS]


def test_the_words_count_the_way_each_language_does():
    ru, uz, en = ReportCopy("ru"), ReportCopy("uz"), ReportCopy("en")

    assert [ru.counted(n, "bills") for n in (1, 3, 5, 11, 21)] == ["1 счёт", "3 счёта", "5 счетов", "11 счетов", "21 счёт"]
    assert (uz.counted(3, "bills"), uz.counted(3, "times")) == ("3 ta hisob", "3 marta")
    assert (en.counted(1, "times"), en.counted(2, "people")) == ("1 time", "2 people")
    assert (ru.wait(12), ru.wait(90), en.wait(2160)) == ("12 мин", "1,5 ч", "1.5 d")
    assert (ru.compact(7_444_000), uz.compact(703_333), en.compact(5_600)) == ("7,4 млн", "703 ming", "5 600")
