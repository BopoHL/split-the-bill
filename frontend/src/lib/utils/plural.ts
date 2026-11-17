/** Localized «people» unit for the headcount stepper (e.g. "4 человека"). */
export function peopleUnit(count: number, language?: string): string {
  const n = Math.abs(count);
  if (language === 'ru') {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return 'человек';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'человека';
    return 'человек';
  }
  if (language === 'uz') return 'kishi';
  // en
  return n === 1 ? 'person' : 'people';
}

/** Localized «participant» unit (e.g. "4 участника") for the «split among all» count. */
export function participantUnit(count: number, language?: string): string {
  const n = Math.abs(count);
  if (language === 'ru') {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return 'участник';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'участника';
    return 'участников';
  }
  if (language === 'uz') return 'ishtirokchi';
  // en
  return n === 1 ? 'participant' : 'participants';
}

/** Localized «dish» unit (e.g. "3 блюда"). */
export function dishUnit(count: number, language?: string): string {
  const n = Math.abs(count);
  if (language === 'ru') {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return 'блюдо';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'блюда';
    return 'блюд';
  }
  if (language === 'uz') return 'ta taom';
  // en
  return n === 1 ? 'dish' : 'dishes';
}

/** Localized «bill» unit (e.g. "4 счёта"). */
export function billUnit(count: number, language?: string): string {
  const n = Math.abs(count);
  if (language === 'ru') {
    const mod10 = n % 10;
    const mod100 = n % 100;
    if (mod10 === 1 && mod100 !== 11) return 'счёт';
    if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return 'счёта';
    return 'счетов';
  }
  if (language === 'uz') return 'hisob';
  return n === 1 ? 'bill' : 'bills';
}
