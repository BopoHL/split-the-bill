"""What the bot shows to explain itself: the welcome picture and the guide.

The pictures are served from the frontend's public/bot/ and drawn from the
HTML in tools/bot-media/. Telegram remembers a picture by its address, so a
redraw has to bump BOT_MEDIA_VERSION or chats keep the old one.
"""
import os
from dataclasses import dataclass
from html import escape

BOT_MEDIA_VERSION = os.getenv("BOT_MEDIA_VERSION", "1")


@dataclass(frozen=True)
class GuideStep:
    title: str
    text: str


@dataclass(frozen=True)
class Guide:
    title: str
    intro: str
    steps: tuple[GuideStep, ...]
    outro: str


_GUIDES = {
    "ru": Guide(
        title="Как пользоваться Split Bill",
        intro="Счёт делится за пару минут: вы сканируете чек, друзья сами отмечают своё, приложение считает доли.",
        steps=(
            GuideStep(
                "Создайте счёт",
                "Откройте приложение и нажмите «+». Укажите, сколько человек за столом и куда переводить деньги.",
            ),
            GuideStep(
                "Отсканируйте чек",
                "Выберите «AI-скан» и сфотографируйте чек — позиции и суммы распознаются сами. Можно и по QR фискального чека, и вручную.",
            ),
            GuideStep(
                "Отправьте ссылку друзьям",
                "Нажмите «Пригласить участников» и отправьте сообщение в общий чат — каждый займёт своё место в счёте.",
            ),
            GuideStep(
                "Каждый отмечает своё",
                "Каждый нажимает «Выбрать позиции» и отмечает, что заказывал; общие позиции делятся поровну. Доли считаются сами.",
            ),
            GuideStep(
                "Соберите переводы",
                "Друзья переводят по реквизитам из счёта и нажимают «Я оплатил(а)», а вы на главной видите, кто ещё должен.",
            ),
        ),
        outro="Создать счёт можно и прямо здесь, в чате, — командой /new.",
    ),
    "uz": Guide(
        title="Split Bill’dan qanday foydalanish",
        intro="Hisob bir necha daqiqada bo‘linadi: siz chekni skanerlaysiz, do‘stlar o‘zinikini belgilaydi, ilova ulushlarni hisoblaydi.",
        steps=(
            GuideStep(
                "Hisob yarating",
                "Ilovani oching va «+» tugmasini bosing. Stolda necha kishi borligini va pul qayerga o‘tkazilishini kiriting.",
            ),
            GuideStep(
                "Chekni skanerlang",
                "«AI-skan»ni tanlang va chekni suratga oling — pozitsiyalar va summalar o‘zi aniqlanadi. Fiskal chek QR kodi yoki qo‘lda kiritish ham bor.",
            ),
            GuideStep(
                "Do‘stlarga havola yuboring",
                "«Ishtirokchilarni taklif qilish»ni bosing va xabarni umumiy chatga yuboring — har kim hisobda o‘z joyini egallaydi.",
            ),
            GuideStep(
                "Har kim o‘zinikini belgilaydi",
                "Har kim «Pozitsiyalarni tanlash»ni bosib, nima buyurtma qilganini belgilaydi; umumiy pozitsiyalar teng bo‘linadi. Ulushlar o‘zi hisoblanadi.",
            ),
            GuideStep(
                "To‘lovlarni yig‘ing",
                "Do‘stlar hisobdagi rekvizitlarga o‘tkazadi va «To‘ladim»ni bosadi, siz esa bosh sahifada kim hali qarzdorligini ko‘rasiz.",
            ),
        ),
        outro="Hisobni shu yerda, chatda ham yaratish mumkin — /new buyrug‘i bilan.",
    ),
    "en": Guide(
        title="How to use Split Bill",
        intro="A bill is split in a couple of minutes: you scan the receipt, friends mark their own items, the app works out the shares.",
        steps=(
            GuideStep(
                "Create a bill",
                "Open the app and tap «+». Say how many people are at the table and where the money should go.",
            ),
            GuideStep(
                "Scan the receipt",
                "Pick «AI scan» and take a photo of the receipt — the items and amounts are read for you. A fiscal receipt’s QR code or typing them in works too.",
            ),
            GuideStep(
                "Send the link to friends",
                "Tap «Invite participants» and send the message to your group chat — everyone takes their seat on the bill.",
            ),
            GuideStep(
                "Everyone marks their own",
                "Everyone taps «Choose items» and marks what they ordered; shared items are split evenly. The shares add themselves up.",
            ),
            GuideStep(
                "Collect the money",
                "Friends send the money to the details on the bill and tap «I paid», and your home screen shows who still owes.",
            ),
        ),
        outro="You can also create a bill right here in the chat — with /new.",
    ),
}


def media_url(name: str) -> str | None:
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    return f"{base}/bot/{name}?v={BOT_MEDIA_VERSION}" if base else None


def welcome_picture(language: str) -> str | None:
    return media_url(f"welcome-{language}.png")


def guide_rich(language: str) -> str | None:
    """The guide as a rich message: each step with its screenshot. None without
    a public address, since Telegram fetches the pictures itself."""
    if media_url("") is None:
        return None
    guide = _GUIDES[language]
    parts = [f"<h2>{escape(guide.title)}</h2>", f"<p>{escape(guide.intro)}</p>"]
    for number, step in enumerate(guide.steps, start=1):
        parts += [
            f"<h3>{number}. {escape(step.title)}</h3>",
            f"<p>{escape(step.text)}</p>",
            f'<img src="{escape(media_url(f"guide-{language}-{number}.png"))}"/>',
        ]
    parts.append(f"<p>{escape(guide.outro)}</p>")
    return "".join(parts)


def guide_plain(language: str) -> str:
    guide = _GUIDES[language]
    steps = [f"<b>{number}. {escape(step.title)}</b>\n{escape(step.text)}" for number, step in enumerate(guide.steps, start=1)]
    return "\n\n".join([f"<b>{escape(guide.title)}</b>", escape(guide.intro), *steps, escape(guide.outro)])
