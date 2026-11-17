window.COPY = {
  ru: {
    open: '🧾 Открыть',
    seat: '👥 Гость 3 – занять',
    chat: 'Друзья',
    sender: 'Тимур',
    headline: 'Делим счёт с друзьями за пару минут',
    steps: ['Сканируете чек', 'Отправляете ссылку друзьям', 'Каждый отмечает своё', 'Видно, кто уже оплатил'],
    guide: [
      ['Сколько человек', 'Куда переводить'],
      ['Фото чека', 'Позиции распознаны'],
      ['Пригласить участников', 'Сообщение для друзей'],
      ['Каждый выбирает своё', 'Доли посчитаны'],
      ['Перевод и «Я оплатил»', 'Видно, кто ещё должен'],
    ],
  },
  uz: {
    open: '🧾 Ochish',
    seat: '👥 3-mehmon – olish',
    chat: 'Do‘stlar',
    sender: 'Temur',
    headline: 'Hisobni do‘stlar bilan bir necha daqiqada bo‘lamiz',
    steps: ['Chekni skanerlaysiz', 'Do‘stlarga havola yuborasiz', 'Har kim o‘zinikini belgilaydi', 'Kim to‘laganini ko‘rasiz'],
    guide: [
      ['Necha kishi', 'Pul qayerga'],
      ['Chek rasmi', 'Pozitsiyalar tanildi'],
      ['Ishtirokchilarni taklif qilish', 'Do‘stlar uchun xabar'],
      ['Har kim o‘zinikini tanlaydi', 'Ulushlar hisoblandi'],
      ['O‘tkazma va «To‘ladim»', 'Kim qarzdorligi ko‘rinadi'],
    ],
  },
  en: {
    open: '🧾 Open',
    seat: '👥 Guest 3 – take',
    chat: 'Friends',
    sender: 'Tim',
    headline: 'Split the bill with friends in a couple of minutes',
    steps: ['Scan the receipt', 'Send the link to friends', 'Everyone marks their own', 'See who has paid'],
    guide: [
      ['How many people', 'Where the money goes'],
      ['A photo of the receipt', 'Items read for you'],
      ['Invite people', 'A message for friends'],
      ['Everyone picks their own', 'Shares worked out'],
      ['Transfer and «I’ve paid»', 'See who still owes'],
    ],
  },
};

// Screens shot as a dialog alone rather than the whole phone behind it.
window.DIALOG_SHOTS = ['wizard-people', 'wizard-card', 'wizard-source', 'guest-pick'];

window.GUIDE_SHOTS = [
  ['wizard-people', 'wizard-card'],
  ['wizard-source', 'receipt'],
  ['owner', 'chat'],
  ['guest-pick', 'card'],
  ['guest', 'home'],
];
