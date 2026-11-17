"""A person's analytics as pictures to share: the report receipt for any
period, and the year's stories. The Mini App gets signed addresses for them
(see picture_links), shows the pictures from those, and hands them to
Telegram — a story to the story editor, the receipt as a photo to send."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlmodel import Session

from app.models import User
from app.schemas.analytics_schemas import AnalyticsPictures, AnalyticsResponse, StoryPicture
from app.services.analytics import AnalyticsService, Period, PeriodKind
from app.services.picture_links import RECEIPT, PictureAddress, address_for
from app.services.report_card import render_report, report_title
from app.utils.local_time import local_zone
from app.services.shared_bill_service import language_of
from app.services.themes import theme_of
from app.services.story_cards import Story, render_story, stories_for
from app.utils.bot_copy import t
from app.utils.report_copy import ReportCopy
from app.utils.telegram import mini_app_link, save_prepared_photo_message

# What chosen_inline_result echoes back for a shared report.
RESULT_PREFIX = "report:"


class AnalyticsPictureService:
    def __init__(self, session: Session):
        self.session = session

    def addresses(self, user: User, period: Period, base_url: str, now: datetime) -> AnalyticsPictures:
        """Where to fetch the period's receipt and, for a year, its stories."""
        theme = theme_of(self.session, user, now.replace(tzinfo=None))
        stories: list[StoryPicture] = []
        story_text = None
        if period.kind == PeriodKind.YEAR:
            found = stories_for(self._analytics(user, period, now))
            stories = [
                StoryPicture(story=story.value, url=address_for(user.id, story.value, period, theme, now).url(base_url))
                for story in found
            ]
            copy = ReportCopy(language_of(user))
            story_text = f"{copy('story_caption', year=period.year)} {mini_app_link()}"
        return AnalyticsPictures(
            receipt=address_for(user.id, RECEIPT, period, theme, now).url(base_url),
            stories=stories,
            story_text=story_text,
        )

    def draw(self, address: PictureAddress, now: datetime) -> bytes:
        """The picture an address names, drawn from the person's bills as they
        are now."""
        user = self.session.get(User, address.user_id)
        if not user:
            raise HTTPException(status_code=404, detail="Picture not found")
        period, language = address.period, language_of(user)
        data = self._analytics(user, period, now)
        if address.picture == RECEIPT:
            name = user.name or user.username or ""
            return render_report(data, period, name, language, now.astimezone(local_zone()).date(), address.theme)
        story = next((story for story in Story if story.value == address.picture), None)
        if period.kind != PeriodKind.YEAR or story not in stories_for(data):
            raise HTTPException(status_code=404, detail="Picture not found")
        return render_story(story, data, period.year, language)

    def prepare_share(self, user: User, period: Period, base_url: str, now: datetime) -> str:
        """Register the period's receipt with Telegram as a photo to send, and
        return its prepared id for WebApp.shareMessage."""
        if not user.telegram_id:
            raise HTTPException(status_code=400, detail="User has no Telegram account")
        language = language_of(user)
        copy = ReportCopy(language)
        try:
            return save_prepared_photo_message(
                user.telegram_id,
                result_id=f"{RESULT_PREFIX}{user.id}",
                photo_url=address_for(user.id, RECEIPT, period, theme_of(self.session, user, now.replace(tzinfo=None)), now).url(base_url),
                caption=copy("share_caption", report=report_title(period, copy)),
                reply_markup={"inline_keyboard": [[{"text": t(language, "btn_open_app"), "url": mini_app_link()}]]},
            )
        except RuntimeError as error:
            raise HTTPException(status_code=502, detail=str(error))

    def _analytics(self, user: User, period: Period, now: datetime) -> AnalyticsResponse:
        return AnalyticsService(self.session).for_user(user, period, now.astimezone(timezone.utc).replace(tzinfo=None))
