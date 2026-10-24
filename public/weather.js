const WEATHER_ENDPOINT = 'https://api.open-meteo.com/v1/forecast?latitude=51.9244&longitude=4.4777&current=temperature_2m,weather_code,cloud_cover,rain,snowfall,wind_speed_10m&timezone=Europe%2FAmsterdam&timeformat=unixtime';

export const rotterdamTime = date => new Intl.DateTimeFormat('en-GB', { timeZone: 'Europe/Amsterdam', hour: '2-digit', minute: '2-digit' }).format(date);

export function weatherDescription(code) {
  if (code === 0) return 'Clear sky';
  if (code === 1) return 'Mostly clear';
  if (code === 2) return 'Partly cloudy';
  if (code === 3) return 'Overcast';
  if ([45, 48].includes(code)) return 'Fog';
  if ([51, 53, 55, 56, 57].includes(code)) return 'Drizzle';
  if ([61, 63, 65, 66, 67].includes(code)) return 'Rain';
  if ([71, 73, 75, 77].includes(code)) return 'Snow';
  if ([80, 81, 82].includes(code)) return 'Rain showers';
  if ([85, 86].includes(code)) return 'Snow showers';
  if ([95, 96, 99].includes(code)) return 'Thunderstorms';
  return 'Weather unavailable';
}

export function watchWeather(onUpdate) {
  let disposed = false;
  let request;
  async function refresh() {
    request?.abort();
    request = new AbortController();
    const timeout = setTimeout(() => request.abort(), 15000);
    try {
      const response = await fetch(WEATHER_ENDPOINT, { signal: request.signal });
      if (!response.ok) throw new Error(`Weather request returned ${response.status}`);
      const { current } = await response.json();
      if (!Number.isFinite(current?.temperature_2m) || !Number.isFinite(current?.time)) throw new Error('Weather response is incomplete');
      if (!disposed) onUpdate({ available: true, temperature: current.temperature_2m, code: current.weather_code, description: weatherDescription(current.weather_code), cloudCover: current.cloud_cover, rain: current.rain, snow: current.snowfall, wind: current.wind_speed_10m, date: new Date(current.time * 1000) });
    } catch (error) {
      if (!disposed) onUpdate({ available: false, error: error.message });
    } finally { clearTimeout(timeout); }
  }
  refresh();
  const timer = setInterval(refresh, 15 * 60 * 1000);
  return () => { disposed = true; clearInterval(timer); request?.abort(); };
}
