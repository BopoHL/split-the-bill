"""Reading the model's answers: whatever comes back, nothing malformed is
kept, and a line the model left out is not labeled for it."""
from types import SimpleNamespace

from app.models import DishGroup
from app.services import labeling
from app.services.labeling import KindNames, PlaceQuestion


def test_dish_answers_are_read_by_index_and_cleaned(monkeypatch):
    monkeypatch.setattr(labeling, "_ask", lambda model, prompt, payload: {"lines": [
        {"i": "1", "group": "dessert", "kind": "Ice Cream!", "ru": "Мороженое", "uz": "Muzqaymoq", "en": "Ice cream"},
        {"i": 0, "group": "fee", "kind": "service", "ru": "Сбор"},
        {"i": 2, "group": "snack", "kind": "chips"},
    ]})

    service, ice_cream, chips, missing = labeling.label_dishes(["Сервис", "Пломбир", "Чипсы", "???"], "m")

    assert (service.group, service.kind, service.names) == (DishGroup.FEE, None, None)
    assert (ice_cream.group, ice_cream.kind) == (DishGroup.DESSERT, "ice_cream")
    assert ice_cream.names == KindNames("Мороженое", "Muzqaymoq", "Ice cream")
    assert (chips.group, chips.kind) == (DishGroup.OTHER, None)
    assert missing is None


def test_place_names_are_trimmed_and_blanks_are_none(monkeypatch):
    monkeypatch.setattr(labeling, "_ask", lambda model, prompt, payload: {"places": [
        {"i": "0", "place": "  Caffeine  "},
        {"i": 1, "place": ""},
        {"i": "two", "place": "Evos"},
    ]})

    assert labeling.name_places([PlaceQuestion([], "a"), PlaceQuestion([], "b"), PlaceQuestion([], "c")], "m") == ["Caffeine", None, None]


def test_every_question_says_json_as_openai_asks_of_its_json_mode(monkeypatch):
    """OpenAI refuses `response_format: json_object` unless the messages say
    «json» somewhere — every labeling call failed on that with a 400."""
    asked = []

    class Completions:
        @staticmethod
        def create(**request):
            asked.append(request)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="{}"))])

    monkeypatch.setattr(labeling, "get_openai_client", lambda: SimpleNamespace(chat=SimpleNamespace(completions=Completions)))

    labeling.label_dishes(["Плов"], "m")
    labeling.name_places([PlaceQuestion([], "Evos")], "m")

    assert len(asked) == 2
    for request in asked:
        assert request["response_format"] == {"type": "json_object"}
        assert any("json" in message["content"].lower() for message in request["messages"])
