/** `n` consecutive weekdays from `start` (UTC) as YYYY-MM-DD strings. */
export function businessDays(n: number, start = '2024-01-01'): string[] {
  const out: string[] = [];
  const day = new Date(`${start}T00:00:00Z`);
  while (out.length < n) {
    const weekday = day.getUTCDay();
    if (weekday !== 0 && weekday !== 6) out.push(day.toISOString().slice(0, 10));
    day.setUTCDate(day.getUTCDate() + 1);
  }
  return out;
}
